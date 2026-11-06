"""K-token CUDA graph + bulk lockstep verification for the Qwenputer executor path (opt-in: --k-graph K).

HYBRID-vs-in-weight label: unchanged. The chip layers still compute every token (fully in-weight, Triton
executor of the compiled circuit); only HOW the host drives them changes.

Semantics (teacher-forced block, lockstep-exact): at a chip position where the oracle's next K tokens are all
chip tokens, the K inputs are [nxt, e0..e_{K-2}] where e are the oracle's tokens. nxt was just compared to the
oracle (precisely, as before). The K executor bodies run in ONE CUDA graph; the K predicted output codes are
compared on the device with the K oracle tokens' codes (bit-exact), one host sync per block. If the block does
not compare equal bit-for-bit (or any code is all-zero), the block is re-decoded token by token on the host with
the exact original rule (code_token -> token id) and the first real mismatch is reported exactly as the original
driver does. Because a mismatch aborts the run, inputs that differ from the model's own output are never used
past the first divergence. No token is skipped: every one of the model's predictions is compared.
Partial blocks (fewer than K chip tokens left, text tokens) use the unchanged single-token path.
"""
import time
from collections import deque as _dq

import torch

STATS = dict(pipelined=0, blocks=0, block_tokens=0, slow_blocks=0, single_tokens=0)


def install(chatmod, K, pipe=False):
    from chipformer.rv import bridge as BR, core, spec as S
    RvChat, ExecRow = chatmod.RvChat, chatmod.ExecRow
    ncode = core.NFAM + core.NPAY

    def capture_k(self):
        ex, dev = self.ex, self.chat.dev
        keep_ir = self.chat.keep_ir
        saved = [(st["S"].clone(), st["hist"].clone()) for st in self.heads]
        self.slots = []
        for _ in range(2 if pipe else 1):
            stage = torch.zeros(K, ex.D, device=dev)
            kout = torch.zeros(K, len(self.chat.keep_cols), device=dev)

            def bodyK(stage=stage, kout=kout):
                for k in range(K):
                    self.xbuf.copy_(stage[k:k + 1])
                    ex.step(self.xbuf)
                    kout[k].copy_(self.xbuf[0, keep_ir])
            s = torch.cuda.Stream()
            s.wait_stream(torch.cuda.current_stream())
            with torch.cuda.stream(s):
                for _ in range(2):
                    bodyK()
            torch.cuda.current_stream().wait_stream(s)
            g = torch.cuda.CUDAGraph()
            with torch.cuda.graph(g):
                bodyK()
            self.slots.append(dict(stage=stage, kout=kout, graph=g))
        for st, (S_, h) in zip(self.heads, saved):
            st["S"].copy_(S_)
            st["hist"].copy_(h)
        self.graphK = self.slots[0]["graph"]
        self.slot_i = 0
        torch.cuda.synchronize()

    ExecRow.capture_k = capture_k

    @torch.no_grad()
    def launch_block(self, in_ids, exp_stream):
        """Stage + replay one K block into the next slot; returns (ok device scalar, kout). No host sync."""
        row = self.erow
        if getattr(row, "graphK", None) is None:
            row.capture_k()
        sl = row.slots[row.slot_i]
        row.slot_i = (row.slot_i + 1) % len(row.slots)
        sl["stage"].copy_(self._exec_emb(in_ids))
        sl["graph"].replay()
        bits = self._bits_cache
        rows = []
        for e in exp_stream:
            b = bits.get(e)
            if b is None:
                b = bits[e] = torch.tensor(core.token_code(e), device=self.dev, dtype=torch.bool)
            rows.append(b)
        want = torch.stack(rows)
        got = sl["kout"][:, :ncode]
        ok = ((got > 0) == want).all() & (got != 0).any(dim=1).all()
        return ok, sl["kout"]

    def run_block(self, in_ids, exp_stream):
        ok, kout = launch_block(self, in_ids, exp_stream)
        return bool(ok), kout

    RvChat._kgraph_block = run_block
    orig_generate = RvChat.generate

    @torch.no_grad()
    def generate(self, ids, machine, max_new=4000, max_chip=60000, check_head=False, verbose=False,
                 lock=None, on_token=None):
        if lock is None or not self.executor or self.verify:
            return orig_generate(self, ids, machine, max_new, max_chip, check_head, verbose, lock, on_token)
        if not hasattr(self, "_bits_cache"):
            self._bits_cache = {}
        x = torch.tensor([ids], device=self.dev)
        out = self.model(input_ids=x, use_cache=True)
        cache = out.past_key_values
        core.snapshot(self.c, machine)
        self._exec_start(ids)
        logits = out.logits[0, -1]
        pos = len(ids)
        gen, n_text, n_chip_tok = [], 0, 0
        nxt = int(torch.argmax(logits[: self.v0]))
        t0 = time.time()
        mismatch = 0
        t_chip = t_text = 0.0
        expect, lock_error = _dq(), None
        v0 = self.v0
        pend = None
        while n_text < max_new and n_chip_tok < max_chip:
            gen.append(nxt)
            if on_token is not None:
                on_token(nxt)
            st = nxt - v0 if nxt >= v0 else BR.text_token(nxt)
            if expect:
                e = expect.popleft()
                if st != e:
                    lock_error = {"at": len(gen) - 1, "got": S.name(st) if st < S.VOCAB
                                  else self.tok.decode([nxt]),
                                  "want": S.name(e) if e < S.VOCAB
                                  else self.tok.decode([e - S.TEXT_TOKEN]),
                                  "recent": [S.name(t - v0) if t >= v0 else
                                             self.tok.decode([t]) for t in gen[-12:]]}
                    break
            elif st < S.VOCAB:
                lock_error = {"at": len(gen) - 1, "got": S.name(st), "want": "text"}
                break
            else:
                k = len(lock.toks)
                try:
                    lock.qwen([nxt])
                except RuntimeError as e:
                    lock_error = {"at": len(gen) - 1, "got": str(e), "want": "a halt"}
                    break
                expect = _dq(lock.toks[k + 1:])
            if nxt in self.eos:
                break
            ts = time.time()
            chip_in = nxt >= v0
            # ---- K-token block: need K chip tokens in the oracle queue, all < VOCAB
            if chip_in and len(expect) >= K and n_chip_tok + K <= max_chip:
                exp_k = [expect[i] for i in range(K)]
                if all(t < S.VOCAB for t in exp_k):
                    in_ids = [nxt] + [t + v0 for t in exp_k[:K - 1]]
                    if pend is not None and pend[0] == in_ids and pend[1] == exp_k:
                        ok_t, kout = pend[2], pend[3]
                        pend = None
                        STATS["pipelined"] += 1
                    else:
                        assert pend is None
                        ok_t, kout = launch_block(self, in_ids, exp_k)
                    if pipe and len(expect) >= 2 * K and n_chip_tok + 2 * K <= max_chip:
                        exp_n = [expect[i] for i in range(K, 2 * K)]
                        if all(t < S.VOCAB for t in exp_n):
                            in_n = [exp_k[K - 1] + v0] + [t + v0 for t in exp_n[:K - 1]]
                            pn_ok, pn_kout = launch_block(self, in_n, exp_n)
                            pend = (in_n, exp_n, pn_ok, pn_kout)
                    ok = bool(ok_t)
                    STATS["blocks"] += 1
                    STATS["block_tokens"] += K
                    if not ok:
                        STATS["slow_blocks"] += 1
                        codes = kout[:, :ncode].cpu()
                        preds = [self.code_token(codes[i]) for i in range(K)]
                        want_ids = [t + v0 for t in exp_k]
                        bad = next((i for i in range(K) if preds[i] != want_ids[i]), None)
                    else:
                        bad = None
                    if bad is not None:
                        # tokens up to the bad position are the same as the original loop would have fed
                        for i in range(bad):
                            expect.popleft()
                            gen.append(in_ids[i + 1])
                            if on_token is not None:
                                on_token(in_ids[i + 1])
                        n_chip_tok += bad + 1
                        got = preds[bad]
                        want = exp_k[bad]
                        gs = None if got is None else (got - v0 if got >= v0 else BR.text_token(got))
                        gen.append(got if got is not None else -1)
                        lock_error = {"at": len(gen) - 1,
                                      "got": "none" if gs is None else (S.name(gs) if gs < S.VOCAB else self.tok.decode([got])),
                                      "want": S.name(want), "recent": [S.name(t - v0) if t >= v0 else
                                                                       self.tok.decode([t]) for t in gen[-12:-1]]}
                        break
                    # all K predictions equal the oracle; consume K-1 (the last stays queued for the loop-top compare)
                    for i in range(K - 1):
                        expect.popleft()
                        gen.append(in_ids[i + 1])
                        if on_token is not None:
                            on_token(in_ids[i + 1])
                    n_chip_tok += K
                    nxt = in_ids[K - 1] if False else exp_k[K - 1] + v0
                    t_chip += time.time() - ts
                    continue
            # ---- single token (unchanged path)
            keep = self._exec_step(nxt)
            hc = None
            if not chip_in:
                hc = self._exec_hc(nxt, keep)
            if chip_in:
                n_chip_tok += 1
                STATS["single_tokens"] += 1
                nxt = self.code_token(keep[: len(self.code_dims)])
                t_chip += time.time() - ts
                if nxt is None:
                    raise RuntimeError("the circuit gave up a chip position")
            else:
                n_text += 1
                logits = self._qwen_step(hc, cache, pos)
                pos += 1
                ct = self.circuit_token(hc)
                q = int(torch.argmax(logits))
                if ct is not None and check_head and q != ct:
                    mismatch += 1
                nxt = ct if ct is not None else int(torch.argmax(logits[: self.v0]))
                t_text += time.time() - ts
        torch.cuda.synchronize()
        dt = time.time() - t0
        return {"tokens": gen, "text_tokens": n_text, "chip_tokens": n_chip_tok, "seconds": dt,
                "head_mismatch": mismatch, "lock_error": lock_error, "verify_mismatch": None,
                "chip_seconds": round(t_chip, 2), "text_seconds": round(t_text, 2), "kgraph": dict(STATS, K=K)}

    RvChat.generate = generate
