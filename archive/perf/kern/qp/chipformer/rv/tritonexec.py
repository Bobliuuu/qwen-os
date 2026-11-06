"""Executor v2: the circuit's step as fused Triton kernels, one per sublayer, under one CUDA graph.

Same semantics as fastexec.Executor (the IR's arithmetic in fp32, every value exact), with the
weights kept as sparse rows (CSR, padded per sublayer to a power-of-2 width KP so a row is one
2D gather instead of a loop of dependent loads):

  MLP    a program per block of units: a and b are sparse dot products with the residual, then
         coef * a * relu(b) goes (atomically) into the output buffer
  heads  a program per value head: q / k / v / z are sparse dot products over the residual and
         its lag history (the conv taps folded into the weights); then decay (only the rows the
         head's keys reach), the one-row write (key = argmax), the read of the query's rows only
         (at most QHOT of them, found by argmax), the ballast norm, the gate and the output
         columns into the output buffer
  apply  residual += output buffer; after a head sublayer its lag history moves on

    Executor2(c, batch).step(x) -> x after the whole circuit (in place)
"""

import numpy as np
import torch
import triton
import triton.language as tl

from chipformer.dsl.graph import ONE
from chipformer.q35.ir import FFN, HD, Head


def _csr(rows):
    """CSR arrays (row_ptr, idx, w) of a list of {col: weight}."""
    rp, ix, w = [0], [], []
    for r in rows:
        for k, v in r.items():
            if v:
                ix.append(k)
                w.append(v)
        rp.append(len(ix))
    if not ix:
        ix, w = [0], [0.0]
    return np.array(rp, np.int32), np.array(ix, np.int32), np.array(w, np.float32)


def _kp(rp) -> int:
    """The padded row width: the next power of 2 of the longest row (at least 2)."""
    return max(2, 1 << int(max(np.diff(rp).max(initial=0), 1) - 1).bit_length())


@triton.jit
def _ffn_kernel(x_ptr, y_ptr, D, U, rpa, ixa, wa, rpb, ixb, wb, coef, outd,
                BLOCK: tl.constexpr, KA: tl.constexpr, KB: tl.constexpr):
    pid = tl.program_id(0)
    bat = tl.program_id(1)
    u = pid * BLOCK + tl.arange(0, BLOCK)
    m = u < U
    xb = x_ptr + bat * D
    a0 = tl.load(rpa + u, mask=m, other=0)
    na = tl.load(rpa + u + 1, mask=m, other=0) - a0
    ka = tl.arange(0, KA)
    ma = m[:, None] & (ka[None, :] < na[:, None])
    ia = tl.load(ixa + a0[:, None] + ka[None, :], mask=ma, other=0)
    av = tl.sum(tl.load(wa + a0[:, None] + ka[None, :], mask=ma, other=0.0)
                * tl.load(xb + ia, mask=ma, other=0.0), axis=1)
    b0 = tl.load(rpb + u, mask=m, other=0)
    nb = tl.load(rpb + u + 1, mask=m, other=0) - b0
    kb = tl.arange(0, KB)
    mb = m[:, None] & (kb[None, :] < nb[:, None])
    ib = tl.load(ixb + b0[:, None] + kb[None, :], mask=mb, other=0)
    bv = tl.sum(tl.load(wb + b0[:, None] + kb[None, :], mask=mb, other=0.0)
                * tl.load(xb + ib, mask=mb, other=0.0), axis=1)
    val = tl.load(coef + u, mask=m, other=0.0) * av * tl.maximum(bv, 0.0)
    od = tl.load(outd + u, mask=m, other=0)
    tl.atomic_add(y_ptr + bat * D + od, val, mask=m)


@triton.jit
def _lag_load(xb, hb, i, m, D):
    """The lagged residual: index lag * D + d (lag 0: x, lags 1..3: the history)."""
    lo = i < D
    return tl.where(lo, tl.load(xb + i, mask=m & lo, other=0.0),
                    tl.load(hb + i - D, mask=m & (i >= D), other=0.0))


@triton.jit
def _rows(xb, hb, D, rp, ix, w, base, ch, KP: tl.constexpr):
    """relu of 128 sparse rows (row base + ch) over the lagged residual."""
    r0 = tl.load(rp + base + ch)
    n = tl.load(rp + base + ch + 1) - r0
    kk = tl.arange(0, KP)
    mk = kk[None, :] < n[:, None]
    i = tl.load(ix + r0[:, None] + kk[None, :], mask=mk, other=0)
    acc = tl.sum(tl.load(w + r0[:, None] + kk[None, :], mask=mk, other=0.0)
                 * _lag_load(xb, hb, i, mk, D), axis=1)
    return tl.maximum(acc, 0.0)


@triton.jit
def _scalar(xb, hb, D, rp, ix, w, vh):
    lane = tl.arange(0, 32)
    s0 = tl.load(rp + vh)
    n = tl.load(rp + vh + 1) - s0
    mk = lane < n
    i = tl.load(ix + s0 + lane, mask=mk, other=0)
    return tl.sum(tl.load(w + s0 + lane, mask=mk, other=0.0) * _lag_load(xb, hb, i, mk, D), axis=0)


@triton.jit
def _head_kernel(x_ptr, h_ptr, S_ptr, y_ptr, D, V,
                 qrp, qix, qw, krp, kix, kw, vrp, vix, vw, zrp, zix, zw,
                 arp, aix, aw, brp, bix, bw, bconst, odim, ow, khead, nrows,
                 KQ: tl.constexpr, KK: tl.constexpr, KV: tl.constexpr, KZ: tl.constexpr,
                 QHOT: tl.constexpr):
    vh = tl.program_id(0)
    bat = tl.program_id(1)
    ch = tl.arange(0, 128)
    xb = x_ptr + bat * D
    hb = h_ptr + bat * 3 * D
    h = tl.load(khead + vh)
    k = _rows(xb, hb, D, krp, kix, kw, h * 128, ch, KK)
    v = _rows(xb, hb, D, vrp, vix, vw, vh * 128, ch, KV)
    z = _rows(xb, hb, D, zrp, zix, zw, vh * 128, ch, KZ)
    q = _rows(xb, hb, D, qrp, qix, qw, h * 128, ch, KQ)
    bv = _scalar(xb, hb, D, brp, bix, bw, vh) + tl.load(bconst + vh)
    Sb = S_ptr + (bat * V + vh) * 16384
    nr = tl.load(nrows + vh)  # > 0: the head decays, in its first nr rows
    if nr > 0:
        av = _scalar(xb, hb, D, arp, aix, aw, vh)
        fac = tl.where(av == 0.0, 1.0, tl.where(av == 110.0, 0.5, 0.0))
        if fac != 1.0:
            for r in range(nr):
                tl.store(Sb + r * 128 + ch, tl.load(Sb + r * 128 + ch) * fac)
    kmax = tl.max(k, axis=0)
    krow = tl.argmax(k, axis=0)
    if (kmax > 0.0) & (bv == 1.0):
        tl.store(Sb + krow * 128 + ch, v)
    tl.debug_barrier()
    # the read: the sum of the rows whose query is set (multi-hot queries have equal values)
    o = tl.zeros([128], dtype=tl.float32)
    for _ in range(QHOT):
        qm = tl.max(q, axis=0)
        qi = tl.argmax(q, axis=0)
        if qm > 0.0:
            o += tl.load(Sb + qi * 128 + ch)
        q = tl.where(ch == qi, 0.0, q)
    ref = tl.sum(tl.where(ch < 2, o * o, 0.0), axis=0)
    norm = tl.math.sqrt_rn(ref / 128.0)
    out = tl.where(ref > 0.0, tl.math.div_rn(o, tl.where(ref > 0.0, norm, 1.0)), 0.0)
    wv = tl.load(ow + vh * 128 + ch)
    dd = tl.load(odim + vh * 128 + ch)
    tl.atomic_add(y_ptr + bat * D + dd, out * z * wv, mask=wv != 0.0)


@triton.jit
def _gather_kernel(x_ptr, h_ptr, G_ptr, D, V,
                   qrp, qix, qw, krp, kix, kw, vrp, vix, vw, zrp, zix, zw, khead,
                   KQ: tl.constexpr, KK: tl.constexpr, KV: tl.constexpr, KZ: tl.constexpr,
                   CH: tl.constexpr):
    """k, v, z, q of every value head, one program per (head, kind, CH rows), into G[bat, vh, 4, 128]."""
    vh = tl.program_id(0)
    which = tl.program_id(1) // (128 // CH)
    bat = tl.program_id(2)
    ch = (tl.program_id(1) % (128 // CH)) * CH + tl.arange(0, CH)
    xb = x_ptr + bat * D
    hb = h_ptr + bat * 3 * D
    h = tl.load(khead + vh)
    if which == 0:
        r = _rows(xb, hb, D, krp, kix, kw, h * 128, ch, KK)
    elif which == 1:
        r = _rows(xb, hb, D, vrp, vix, vw, vh * 128, ch, KV)
    elif which == 2:
        r = _rows(xb, hb, D, zrp, zix, zw, vh * 128, ch, KZ)
    else:
        r = _rows(xb, hb, D, qrp, qix, qw, h * 128, ch, KQ)
    tl.store(G_ptr + ((bat * V + vh) * 4 + which) * 128 + ch, r)


@triton.jit
def _head2_kernel(x_ptr, h_ptr, S_ptr, y_ptr, G_ptr, D, V,
                  arp, aix, aw, brp, bix, bw, bconst, odim, ow, nrows,
                  QHOT: tl.constexpr):
    vh = tl.program_id(0)
    bat = tl.program_id(1)
    ch = tl.arange(0, 128)
    xb = x_ptr + bat * D
    hb = h_ptr + bat * 3 * D
    Gb = G_ptr + (bat * V + vh) * 512
    k = tl.load(Gb + ch)
    v = tl.load(Gb + 128 + ch)
    z = tl.load(Gb + 256 + ch)
    q = tl.load(Gb + 384 + ch)
    bv = _scalar(xb, hb, D, brp, bix, bw, vh) + tl.load(bconst + vh)
    Sb = S_ptr + (bat * V + vh) * 16384
    nr = tl.load(nrows + vh)
    if nr > 0:
        av = _scalar(xb, hb, D, arp, aix, aw, vh)
        fac = tl.where(av == 0.0, 1.0, tl.where(av == 110.0, 0.5, 0.0))
        if fac != 1.0:
            for r in range(nr):
                tl.store(Sb + r * 128 + ch, tl.load(Sb + r * 128 + ch) * fac)
    kmax = tl.max(k, axis=0)
    krow = tl.argmax(k, axis=0)
    if (kmax > 0.0) & (bv == 1.0):
        tl.store(Sb + krow * 128 + ch, v)
    tl.debug_barrier()
    o = tl.zeros([128], dtype=tl.float32)
    for _ in range(QHOT):
        qm = tl.max(q, axis=0)
        qi = tl.argmax(q, axis=0)
        if qm > 0.0:
            o += tl.load(Sb + qi * 128 + ch)
        q = tl.where(ch == qi, 0.0, q)
    ref = tl.sum(tl.where(ch < 2, o * o, 0.0), axis=0)
    norm = tl.math.sqrt_rn(ref / 128.0)
    out = tl.where(ref > 0.0, tl.math.div_rn(o, tl.where(ref > 0.0, norm, 1.0)), 0.0)
    wv = tl.load(ow + vh * 128 + ch)
    dd = tl.load(odim + vh * 128 + ch)
    tl.atomic_add(y_ptr + bat * D + dd, out * z * wv, mask=wv != 0.0)


@triton.jit
def _apply_kernel(x_ptr, y_ptr, h_ptr, D, HIST: tl.constexpr, BLOCK: tl.constexpr):
    """x += y, y = 0; with HIST, the lag history (h: [3, D] per row, h[0] = lag 1) moves on
    first, the input x becoming lag 1."""
    pid = tl.program_id(0)
    bat = tl.program_id(1)
    i = pid * BLOCK + tl.arange(0, BLOCK)
    m = i < D
    xo = x_ptr + bat * D + i
    x = tl.load(xo, mask=m, other=0.0)
    if HIST:
        hb = h_ptr + bat * 3 * D + i
        h1 = tl.load(hb + D, mask=m, other=0.0)
        h0 = tl.load(hb, mask=m, other=0.0)
        tl.store(hb + 2 * D, h1, mask=m)
        tl.store(hb + D, h0, mask=m)
        tl.store(hb, x, mask=m)
    yo = y_ptr + bat * D + i
    tl.store(xo, x + tl.load(yo, mask=m, other=0.0), mask=m)
    tl.store(yo, tl.zeros([BLOCK], dtype=tl.float32), mask=m)


# ---------------------------------------------------------------------------------------------
# fused-apply variant: no standalone apply kernel. Kernel j reads x as xin + yin (the same fp32
# add the apply kernel did), atomically accumulates its output into yout, and a few extra
# "commit" programs write xout = xin + yin, zero the y buffer that kernel j+1 will accumulate
# into, and (after a head sublayer) move the lag history on. x ping-pongs over two buffers, y
# rotates over three.
# ---------------------------------------------------------------------------------------------

@triton.jit
def _lag_loadf(xb, yb, hb, i, m, D):
    lo = i < D
    xv = tl.load(xb + i, mask=m & lo, other=0.0) + tl.load(yb + i, mask=m & lo, other=0.0)
    return tl.where(lo, xv, tl.load(hb + i - D, mask=m & (i >= D), other=0.0))


@triton.jit
def _rowsf(xb, yb, hb, D, rp, ix, w, base, ch, KP: tl.constexpr):
    r0 = tl.load(rp + base + ch)
    n = tl.load(rp + base + ch + 1) - r0
    kk = tl.arange(0, KP)
    mk = kk[None, :] < n[:, None]
    i = tl.load(ix + r0[:, None] + kk[None, :], mask=mk, other=0)
    acc = tl.sum(tl.load(w + r0[:, None] + kk[None, :], mask=mk, other=0.0)
                 * _lag_loadf(xb, yb, hb, i, mk, D), axis=1)
    return tl.maximum(acc, 0.0)


@triton.jit
def _scalarf(xb, yb, hb, D, rp, ix, w, vh):
    lane = tl.arange(0, 32)
    s0 = tl.load(rp + vh)
    n = tl.load(rp + vh + 1) - s0
    mk = lane < n
    i = tl.load(ix + s0 + lane, mask=mk, other=0)
    return tl.sum(tl.load(w + s0 + lane, mask=mk, other=0.0)
                  * _lag_loadf(xb, yb, hb, i, mk, D), axis=0)


@triton.jit
def _commit(xin, yin, xout, ynext, h_ptr, bat, D, blk, HIST: tl.constexpr, BLOCK: tl.constexpr):
    i = blk * BLOCK + tl.arange(0, BLOCK)
    m = i < D
    xi = tl.load(xin + bat * D + i, mask=m, other=0.0)
    yi = tl.load(yin + bat * D + i, mask=m, other=0.0)
    if HIST:
        hb = h_ptr + bat * 3 * D + i
        h1 = tl.load(hb + D, mask=m, other=0.0)
        h0 = tl.load(hb, mask=m, other=0.0)
        tl.store(hb + 2 * D, h1, mask=m)
        tl.store(hb + D, h0, mask=m)
        tl.store(hb, xi, mask=m)
    tl.store(xout + bat * D + i, xi + yi, mask=m)
    tl.store(ynext + bat * D + i, tl.zeros([BLOCK], dtype=tl.float32), mask=m)


@triton.jit
def _flush_kernel(xin, yin, xout, y1, y2, y3, h_ptr, D, HIST: tl.constexpr, BLOCK: tl.constexpr):
    """End of a run of fused kernels: x = xin + yin (into xout), all y zeroed, history moved."""
    blk = tl.program_id(0)
    bat = tl.program_id(1)
    _commit(xin, yin, xout, y1, h_ptr, bat, D, blk, HIST, BLOCK)
    i = blk * BLOCK + tl.arange(0, BLOCK)
    m = i < D
    z = tl.zeros([BLOCK], dtype=tl.float32)
    tl.store(y2 + bat * D + i, z, mask=m)
    tl.store(y3 + bat * D + i, z, mask=m)


@triton.jit
def _ffn_f(xin, yin, xout, yout, ynext, h_ptr, D, U, nU, rpa, ixa, wa, rpb, ixb, wb, coef, outd,
           BLOCK: tl.constexpr, KA: tl.constexpr, KB: tl.constexpr, HIST: tl.constexpr,
           CB: tl.constexpr):
    pid = tl.program_id(0)
    bat = tl.program_id(1)
    if pid < nU:
        u = pid * BLOCK + tl.arange(0, BLOCK)
        m = u < U
        xb = xin + bat * D
        yb = yin + bat * D
        a0 = tl.load(rpa + u, mask=m, other=0)
        na = tl.load(rpa + u + 1, mask=m, other=0) - a0
        ka = tl.arange(0, KA)
        ma = m[:, None] & (ka[None, :] < na[:, None])
        ia = tl.load(ixa + a0[:, None] + ka[None, :], mask=ma, other=0)
        av = tl.sum(tl.load(wa + a0[:, None] + ka[None, :], mask=ma, other=0.0)
                    * (tl.load(xb + ia, mask=ma, other=0.0) + tl.load(yb + ia, mask=ma, other=0.0)),
                    axis=1)
        b0 = tl.load(rpb + u, mask=m, other=0)
        nb = tl.load(rpb + u + 1, mask=m, other=0) - b0
        kb = tl.arange(0, KB)
        mb = m[:, None] & (kb[None, :] < nb[:, None])
        ib = tl.load(ixb + b0[:, None] + kb[None, :], mask=mb, other=0)
        bv = tl.sum(tl.load(wb + b0[:, None] + kb[None, :], mask=mb, other=0.0)
                    * (tl.load(xb + ib, mask=mb, other=0.0) + tl.load(yb + ib, mask=mb, other=0.0)),
                    axis=1)
        val = tl.load(coef + u, mask=m, other=0.0) * av * tl.maximum(bv, 0.0)
        od = tl.load(outd + u, mask=m, other=0)
        tl.atomic_add(yout + bat * D + od, val, mask=m)
    else:
        _commit(xin, yin, xout, ynext, h_ptr, bat, D, pid - nU, HIST, CB)


@triton.jit
def _gather_f(xin, yin, xout, ynext, G_ptr, h_ptr, D, V,
              qrp, qix, qw, krp, kix, kw, vrp, vix, vw, zrp, zix, zw, khead,
              KQ: tl.constexpr, KK: tl.constexpr, KV: tl.constexpr, KZ: tl.constexpr,
              CH: tl.constexpr, SL: tl.constexpr):
    vh = tl.program_id(0)
    p1 = tl.program_id(1)
    bat = tl.program_id(2)
    if p1 < 4 * (128 // CH):
        which = p1 // (128 // CH)
        ch = (p1 % (128 // CH)) * CH + tl.arange(0, CH)
        xb = xin + bat * D
        yb = yin + bat * D
        hb = h_ptr + bat * 3 * D
        h = tl.load(khead + vh)
        if which == 0:
            r = _rowsf(xb, yb, hb, D, krp, kix, kw, h * 128, ch, KK)
        elif which == 1:
            r = _rowsf(xb, yb, hb, D, vrp, vix, vw, vh * 128, ch, KV)
        elif which == 2:
            r = _rowsf(xb, yb, hb, D, zrp, zix, zw, vh * 128, ch, KZ)
        else:
            r = _rowsf(xb, yb, hb, D, qrp, qix, qw, h * 128, ch, KQ)
        tl.store(G_ptr + ((bat * V + vh) * 4 + which) * 128 + ch, r)
    else:
        _commit(xin, yin, xout, ynext, h_ptr, bat, D, vh, False, SL)


@triton.jit
def _head2_f(xin, yin, yout, h_ptr, S_ptr, G_ptr, D, V,
             arp, aix, aw, brp, bix, bw, bconst, odim, ow, nrows,
             QHOT: tl.constexpr):
    vh = tl.program_id(0)
    bat = tl.program_id(1)
    ch = tl.arange(0, 128)
    xb = xin + bat * D
    yb = yin + bat * D
    hb = h_ptr + bat * 3 * D
    Gb = G_ptr + (bat * V + vh) * 512
    k = tl.load(Gb + ch)
    v = tl.load(Gb + 128 + ch)
    z = tl.load(Gb + 256 + ch)
    q = tl.load(Gb + 384 + ch)
    bv = _scalarf(xb, yb, hb, D, brp, bix, bw, vh) + tl.load(bconst + vh)
    Sb = S_ptr + (bat * V + vh) * 16384
    nr = tl.load(nrows + vh)
    if nr > 0:
        av = _scalarf(xb, yb, hb, D, arp, aix, aw, vh)
        fac = tl.where(av == 0.0, 1.0, tl.where(av == 110.0, 0.5, 0.0))
        if fac != 1.0:
            for r in range(nr):
                tl.store(Sb + r * 128 + ch, tl.load(Sb + r * 128 + ch) * fac)
    kmax = tl.max(k, axis=0)
    krow = tl.argmax(k, axis=0)
    if (kmax > 0.0) & (bv == 1.0):
        tl.store(Sb + krow * 128 + ch, v)
    tl.debug_barrier()
    o = tl.zeros([128], dtype=tl.float32)
    for _ in range(QHOT):
        qm = tl.max(q, axis=0)
        qi = tl.argmax(q, axis=0)
        if qm > 0.0:
            o += tl.load(Sb + qi * 128 + ch)
        q = tl.where(ch == qi, 0.0, q)
    ref = tl.sum(tl.where(ch < 2, o * o, 0.0), axis=0)
    norm = tl.math.sqrt_rn(ref / 128.0)
    out = tl.where(ref > 0.0, tl.math.div_rn(o, tl.where(ref > 0.0, norm, 1.0)), 0.0)
    wv = tl.load(ow + vh * 128 + ch)
    dd = tl.load(odim + vh * 128 + ch)
    tl.atomic_add(yout + bat * D + dd, out * z * wv, mask=wv != 0.0)


class Executor2:
    BLOCK = 64
    HW = None   # head kernel num_warps (None: triton default)
    FW = None   # ffn kernel num_warps
    AW = None   # apply kernel num_warps
    SPLIT = False  # gather k/v/z/q in a separate 4x-parallel kernel
    FUSE = False  # no apply kernels (needs SPLIT)
    CH = 128    # rows per gather program
    GW = None   # gather kernel num_warps
    H2W = None  # head2 kernel num_warps

    def __init__(self, c, batch: int = 1, device="cuda"):
        self.c, self.B, self.dev = c, batch, device
        D = len(c.dims)
        self.D = D
        t = lambda a, dt=torch.int32: torch.tensor(np.asarray(a), dtype=dt, device=device)

        def dev3(arr):
            return [t(arr[0]), t(arr[1]), t(arr[2], torch.float32)]

        self.steps = []
        for lv in sorted({n.level for n in c.nodes}):
            nodes = [n for n in c.nodes if n.level == lv]
            if isinstance(nodes[0], FFN):
                units = [(float(cf), a, b, n.out) for n in nodes for cf, a, b in n.terms]
                ra = _csr([{d: float(v) for d, v in a.terms.items()} for _, a, _, _ in units])
                rb = _csr([{d: float(v) for d, v in b.terms.items()} for _, _, b, _ in units])
                self.steps.append({"kind": "ffn", "U": len(units), "a": dev3(ra), "b": dev3(rb),
                                   "KA": _kp(ra[0]), "KB": _kp(rb[0]),
                                   "coef": t([u[0] for u in units], torch.float32),
                                   "out": t([u[3] for u in units])})
                continue
            heads = [n for n in nodes if isinstance(n, Head)]
            vh = [(h, vd) for h, n in enumerate(heads) for vd in n.vheads()]
            V = len(vh)

            def lagged(ch, D=D):
                return {lag * D + d: float(cf) * tw for lag, tw in enumerate(ch.taps) if tw
                        for d, cf in ch.expr.terms.items()}

            qrows, krows = [], []
            for n in heads:
                for s in range(HD):
                    qrows.append(lagged(n.q[s]) if s in n.q else {})
                    krows.append(lagged(n.k[s]) if s in n.k else {})
            vrows, zrows, arows, brows, bconst, odim, ow, khead, nrows = ([] for _ in range(9))
            for h, vd in vh:
                for col in range(HD):
                    vrows.append(lagged(vd.v[col]) if col in vd.v else {})
                    zrows.append({d: float(cf) for d, cf in vd.z[col].terms.items()}
                                 if col in vd.z else {})
                arows.append({d: float(cf) for d, cf in vd.a.terms.items()})
                if vd.beta is None:
                    brows.append({})
                    bconst.append(1.0)
                else:
                    brows.append({d: float(cf) for d, cf in vd.beta.terms.items()})
                    bconst.append(0.0)
                od, w_ = np.zeros(HD, np.int32), np.zeros(HD, np.float32)
                for col, d, w in vd.out:
                    od[col], w_[col] = d, w
                odim.append(od)
                ow.append(w_)
                khead.append(h)
                # a decaying head: only the rows its keys (or its initial state) reach
                reach = set(heads[h].k) | {r for x in (heads[h].init or []) for r in x}
                nrows.append(max(reach) + 1 if vd.a.terms and reach else 0)
            assert max(len(r) for r in arows + brows) <= 32
            q, k, v, z = (_csr(r) for r in (qrows, krows, vrows, zrows))
            st = {"kind": "head", "V": V, "heads": heads, "q": dev3(q), "k": dev3(k),
                  "v": dev3(v), "z": dev3(z), "a": dev3(_csr(arows)), "b": dev3(_csr(brows)),
                  "KQ": _kp(q[0]), "KK": _kp(k[0]), "KV": _kp(v[0]), "KZ": _kp(z[0]),
                  "QHOT": max(getattr(n, "qhot", 2) for n in heads),
                  "bconst": t(bconst, torch.float32), "odim": t(np.concatenate(odim)),
                  "ow": t(np.concatenate(ow), torch.float32), "khead": t(khead),
                  "nrows": t(nrows), "S": torch.zeros(batch, V, HD, HD, device=device),
                  "hist": torch.zeros(batch, 3, D, device=device)}  # lags 1..3
            self.steps.append(st)
        self.y = torch.zeros(batch, D, device=device)
        self.feat_ids = sorted(c.token_fns)

    def load_init(self, row: int = 0):
        for st in self.steps:
            if st["kind"] != "head":
                continue
            buf = np.zeros(st["S"].shape[1:], np.float32)
            j = 0
            for n in st["heads"]:
                init = n.init or []
                for x in range(len(n.vheads())):
                    for r, vec in (init[x] if x < len(init) else {}).items():
                        buf[j, r] = vec
                    j += 1
            st["S"][row].copy_(torch.from_numpy(buf))

    def reset(self, rows=None):
        for st in self.steps:
            if st["kind"] == "head":
                (st["hist"].zero_() if rows is None else st["hist"][rows].zero_())

    def embed(self, toks):
        out = np.zeros((len(toks), self.D))
        out[:, ONE] = 1.0
        for d in self.feat_ids:
            out[:, d] = [float(self.c.feature_value(d, t)) for t in toks]
        return torch.tensor(out, dtype=torch.float32, device=self.dev)

    @staticmethod
    def _kw(w):
        return {} if w is None else {"num_warps": w}

    def step(self, x):
        """x [B, D] (in place: the embedding in, the residual after every node out)."""
        B, D = x.shape[0], self.D
        if self.FUSE:
            return self._step_fused(x)
        grid_apply = (triton.cdiv(D, 1024), B)
        for st in self.steps:
            if st["kind"] == "ffn":
                _ffn_kernel[(triton.cdiv(st["U"], self.BLOCK), B)](
                    x, self.y, D, st["U"], *st["a"], *st["b"], st["coef"], st["out"],
                    BLOCK=self.BLOCK, KA=st["KA"], KB=st["KB"], **self._kw(self.FW))
                _apply_kernel[grid_apply](x, self.y, x, D, HIST=False, BLOCK=1024, **self._kw(self.AW))
                continue
            if self.SPLIT:
                if "G" not in st:
                    st["G"] = torch.zeros(B, st["V"], 4, 128, device=self.dev)
                _gather_kernel[(st["V"], 4 * (128 // self.CH), B)](
                    x, st["hist"], st["G"], D, st["V"], *st["q"], *st["k"], *st["v"], *st["z"],
                    st["khead"], KQ=st["KQ"], KK=st["KK"], KV=st["KV"], KZ=st["KZ"], CH=self.CH,
                    **self._kw(self.GW))
                _head2_kernel[(st["V"], B)](
                    x, st["hist"], st["S"], self.y, st["G"], D, st["V"], *st["a"], *st["b"],
                    st["bconst"], st["odim"], st["ow"], st["nrows"], QHOT=st["QHOT"],
                    **self._kw(self.H2W))
            else:
                _head_kernel[(st["V"], B)](
                    x, st["hist"], st["S"], self.y, D, st["V"], *st["q"], *st["k"], *st["v"],
                    *st["z"], *st["a"], *st["b"], st["bconst"], st["odim"], st["ow"], st["khead"],
                    st["nrows"], KQ=st["KQ"], KK=st["KK"], KV=st["KV"], KZ=st["KZ"],
                    QHOT=st["QHOT"], **self._kw(self.HW))
            _apply_kernel[grid_apply](x, self.y, st["hist"], D, HIST=True, BLOCK=1024, **self._kw(self.AW))
        return x


    def _step_fused(self, x):
        B, D = x.shape[0], self.D
        if getattr(self, "_fx", None) is None or self._fx.shape[0] != B:
            self._fx = torch.zeros(B, D, device=self.dev)
            self._fy = [torch.zeros(B, D, device=self.dev) for _ in range(3)]
        X, Y = [x, self._fx], self._fy
        j = 0                # kernel index in the current run
        pend = None          # head state whose history move is still owed
        CB = 1024
        NC = triton.cdiv(D, CB)

        def flush():
            nonlocal j, pend
            if j == 0:
                return
            hist = pend["hist"] if pend is not None else x
            _flush_kernel[(NC, B)](X[j % 2], Y[(j - 1) % 3], x, Y[0], Y[1], Y[2],
                                   hist, D, HIST=pend is not None, BLOCK=CB)
            j, pend = 0, None

        for st in self.steps:
            xin, yin, xout = X[j % 2], Y[(j - 1) % 3], X[(j + 1) % 2]
            yout, ynext = Y[j % 3], Y[(j + 1) % 3]
            if st["kind"] == "ffn":
                _ffn_f[(triton.cdiv(st["U"], self.BLOCK) + NC, B)](
                    xin, yin, xout, yout, ynext,
                    pend["hist"] if pend is not None else x, D, st["U"],
                    triton.cdiv(st["U"], self.BLOCK), *st["a"], *st["b"], st["coef"], st["out"],
                    BLOCK=self.BLOCK, KA=st["KA"], KB=st["KB"], HIST=pend is not None, CB=CB,
                    **self._kw(self.FW))
                pend = None
                j += 1
                continue
            if pend is not None:
                flush()
                xin, yin, xout = X[j % 2], Y[(j - 1) % 3], X[(j + 1) % 2]
                yout, ynext = Y[j % 3], Y[(j + 1) % 3]
            if "G" not in st:
                st["G"] = torch.zeros(B, st["V"], 4, 128, device=self.dev)
            SL = 1 << max(0, (triton.cdiv(D, st["V"]) - 1).bit_length())
            _gather_f[(st["V"], 4 * (128 // self.CH) + 1, B)](
                xin, yin, xout, ynext, st["G"], st["hist"], D, st["V"],
                *st["q"], *st["k"], *st["v"], *st["z"], st["khead"],
                KQ=st["KQ"], KK=st["KK"], KV=st["KV"], KZ=st["KZ"], CH=self.CH, SL=SL,
                **self._kw(self.GW))
            _head2_f[(st["V"], B)](
                xin, yin, yout, st["hist"], st["S"], st["G"], D, st["V"], *st["a"], *st["b"],
                st["bconst"], st["odim"], st["ow"], st["nrows"], QHOT=st["QHOT"],
                **self._kw(self.H2W))
            pend = st
            j += 1
        flush()
        return x


def check(c, toks, device="cuda") -> int:
    """Executor2 == ir.evaluate on every dim at every position."""
    from chipformer.q35 import ir

    ex = Executor2(c, 1, device)
    ex.load_init()
    emb = ex.embed(toks)
    want = ir.evaluate(c, toks, check=False)
    for t in range(len(toks)):
        x = emb[t:t + 1].clone()
        got = ex.step(x)[0].double().cpu().numpy()
        bad = np.nonzero(got != want[t])[0]
        assert not len(bad), (t, [(c.dims[d].name, got[d], want[t, d]) for d in bad[:5]])
    return len(toks)
