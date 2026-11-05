# Dynamic basic-block trace of the E1M1 demo (host emulator)

Every number in this file comes from the **host C emulator** (`tools/rv32_fast.c` built with `-DBBTRACE`). Nothing here was run on the Qwen model, a GPU or any paid service. The fusion section is an **estimate of how many neural transitions could disappear in the best case; it is not a measured or promised speedup.**

## What was traced

- Image: `build/demo/qwenos-e1m1.elf` (`make demo-elf`: scripted E1M1, FULL preset, 350 game tics), DMC100 `/bin/doomd` on Freedoom E1M1, run to its exit ecall.
- Disk: host-served (the dry-run configuration of `tools/mkdemo.sh`), so this is the 180.5 M instruction run, not the 81 M chunk-ROM clip. The trace therefore includes the cold boot and level load, and the disk-request code paths.
- A **dynamic basic block** is a maximal run of consecutively *executed* instructions that begins at program entry or at the target (taken or fall-through) of a control transfer, and ends at the first `beq/bne/blt/bge/bltu/bgeu`, `jal`, `jalr` or `ecall` (that instruction is the last of the block). Code is immutable ROM, so the start pc fixes the exact instruction sequence; the tracer asserts this. Entering a block in its middle creates a different block (blocks may overlap).
- Pair/triple counts are over the *actual* executed stream (consecutive retired instructions, across taken branches too), not per-pc histograms.
- Raw data: `blocks.tsv`, `mem.tsv`, `pairs.tsv`, `triples.tsv`, `tics.tsv`, `summary.txt` in the trace directory; `tics.tsv` is committed next to this file (`docs/research/bbtrace/tics.tsv`).

## Reproduce

```sh
DMC=<DMC100-Doom tree with engine-patches applied> make demo-elf   # build the image, once
DMC=<same tree> tools/bbtrace_e1m1.sh                                        # trace + write this report
```

Needs the repo build prerequisites (Clang/LLD, the DMC100 engine tree with `engine-patches/`, Freedoom WAD in the E1 NOR image; see README "Get the engine and Freedoom"). The test `tests/test_bbtrace.py` (part of `python3 -m unittest discover -s tests`) proves the tracer is a pure observer.

## Totals

| Quantity | Value |
|---|---|
| Guest instructions executed (steps) | 180,550,104 |
| Instructions inside completed blocks | 180,550,103 |
| Open tail at exit (not in a block; retired instrs of the unfinished last block) | 1 |
| Dynamic blocks executed | 24,346,428 |
| Static (distinct start pc) blocks seen | 4,616 |
| Mean dynamic block length (instr) | 7.416 |
| Loads / stores | 41,341,061 / 21,779,142  (0.229 / 0.121 per instr) |
| Distinct executed instruction pairs / triples | 24,369 / 26,203 |

## Coverage: how much of the run the hottest blocks cover

| Blocks (ranked by dynamic instrs) | Dynamic instrs covered | % of total |
|---|---|---|
| top 1 | 32,664,701 | 18.09% |
| top 5 | 47,608,737 | 26.37% |
| top 10 | 57,767,539 | 32.00% |
| top 20 | 71,466,673 | 39.58% |
| top 50 | 97,444,986 | 53.97% |
| top 100 | 118,600,180 | 65.69% |
| top 200 | 139,093,159 | 77.04% |
| top 500 | 162,408,352 | 89.95% |
| top 1000 | 174,793,389 | 96.81% |
| top 2000 | 179,942,455 | 99.66% |

Same coverage by enclosing symbol (block start pc), top 15:

| Symbol | Dynamic instrs | % of total |
|---|---|---|
| R_ColumnLoop | 33,793,967 | 18.72% |
| R_ReplayWall | 22,034,899 | 12.20% |
| rec_get | 13,966,042 | 7.74% |
| rc_fill | 8,142,201 | 4.51% |
| R_MapPlane | 7,784,140 | 4.31% |
| R_SpanLoop | 7,219,310 | 4.00% |
| nor_read | 7,033,879 | 3.90% |
| R_QueueColumn | 5,608,717 | 3.11% |
| R_DrawQueued | 4,196,511 | 2.32% |
| rec_u16 | 3,318,862 | 1.84% |
| rec_get_miss | 3,135,991 | 1.74% |
| nor_hw | 2,984,486 | 1.65% |
| FixedDiv | 2,325,541 | 1.29% |
| nor_col_start | 2,236,738 | 1.24% |
| V_DrawPatchCols | 2,229,690 | 1.23% |

## Hottest blocks

| # | Start pc | Symbol | Len | Exec count | % of dyn instrs | Ends with | Ld/St | Top successor (share) |
|---|---|---|---|---|---|---|---|---|
| 1 | `0x60a2c` | `R_ColumnLoop+0x30` | 59 | 553,639 | 18.09% | cond branch | 16/8 | 0x60a2c 94% (2 tgts) |
| 2 | `0x60bfc` | `R_SpanLoop+0x38` | 83 | 61,208 | 2.81% | cond branch | 16/8 | 0x60d48 100% (1 tgts) |
| 3 | `0x5728c` | `R_MapPlane+0xc0` | 48 | 82,810 | 2.20% | jal | 7/0 | 0x60bc4 100% (1 tgts) |
| 4 | `0x5cb94` | `rec_get+0x24` | 10 | 298,893 | 1.66% | cond branch | 2/0 | 0x5cbc8 82% (2 tgts) |
| 5 | `0x5d3e0` | `rc_fill` | 26 | 111,537 | 1.61% | cond branch | 3/7 | 0x5d448 100% (1 tgts) |
| 6 | `0x5d4b0` | `rc_fill+0xd0` | 24 | 111,537 | 1.48% | jalr | 9/2 | 0x5ccd4 82% (4 tgts) |
| 7 | `0x582c0` | `R_ReplayWall+0xba4` | 32 | 76,102 | 1.35% | cond branch | 4/0 | 0x58340 61% (2 tgts) |
| 8 | `0x6155c` | `dmc_tantoangle` | 35 | 54,938 | 1.06% | jalr | 4/0 | 0x5653c 43% (8+ tgts) |
| 9 | `0x68b6c` | `nor_read+0xb8` | 14 | 111,593 | 0.87% | cond branch | 4/4 | 0x68b74 100% (1 tgts) |
| 10 | `0x5d454` | `rc_fill+0x74` | 14 | 111,537 | 0.86% | cond branch | 3/0 | 0x5d48c 100% (1 tgts) |
| 11 | `0x69eac` | `FixedMul` | 6 | 255,733 | 0.85% | jalr | 0/0 | 0x59484 2% (8+ tgts) |
| 12 | `0x5cb80` | `rec_get+0x10` | 5 | 300,760 | 0.83% | cond branch | 0/0 | 0x5cb94 99% (2 tgts) |
| 13 | `0x4cb30` | `P_GetSeg+0x28` | 34 | 41,508 | 0.78% | jalr | 10/10 | 0x51c44 54% (4 tgts) |
| 14 | `0x5cc68` | `rec_get+0xf8` | 9 | 155,231 | 0.77% | jalr | 4/4 | 0x4c448 8% (8+ tgts) |
| 15 | `0x58150` | `R_ReplayWall+0xa34` | 16 | 84,717 | 0.75% | cond branch | 7/4 | 0x58190 85% (2 tgts) |
| 16 | `0x68b74` | `nor_read+0xc0` | 12 | 111,885 | 0.74% | cond branch | 4/4 | 0x68ba4 100% (2 tgts) |
| 17 | `0x55790` | `R_DrawQueued+0x1c0` | 43 | 31,001 | 0.74% | jal | 23/0 | 0x609fc 100% (1 tgts) |
| 18 | `0x5724c` | `R_MapPlane+0x80` | 16 | 82,810 | 0.73% | cond branch | 5/0 | 0x5728c 100% (1 tgts) |
| 19 | `0x681d8` | `memset+0x28` | 4 | 313,189 | 0.69% | cond branch | 0/1 | 0x681d8 94% (2 tgts) |
| 20 | `0x5cbec` | `rec_get+0x7c` | 6 | 207,289 | 0.69% | cond branch | 1/0 | 0x5cc20 51% (2 tgts) |
| 21 | `0x5cc04` | `rec_get+0x94` | 12 | 100,620 | 0.67% | cond branch | 1/1 | 0x5cc34 100% (1 tgts) |
| 22 | `0x5cb70` | `rec_get` | 4 | 300,760 | 0.67% | cond branch | 2/0 | 0x5cb80 100% (1 tgts) |
| 23 | `0x57210` | `R_MapPlane+0x44` | 14 | 82,810 | 0.64% | cond branch | 2/0 | 0x5724c 100% (1 tgts) |
| 24 | `0x60bc4` | `R_SpanLoop` | 14 | 82,810 | 0.64% | jalr | 1/0 | 0x60bfc 74% (8 tgts) |
| 25 | `0x69ef4` | `FixedDiv+0x30` | 38 | 29,798 | 0.63% | jal | 0/0 | 0x69f9c 100% (1 tgts) |

Exact instruction sequences of the ten hottest blocks:

**#1** `0x60a2c` `R_ColumnLoop+0x30`, 59 instr, executed 553,639 times (18.09% of dynamic instrs)

```
0x60a2c  srl a7,a2,a4
0x60a30  add a7,a5,a7
0x60a34  lbu a7,0(a7)
0x60a38  add a7,a6,a7
0x60a3c  lbu a7,0(a7)
0x60a40  sb a7,0(a0)
0x60a44  add a2,a2,a3
0x60a48  srl a7,a2,a4
0x60a4c  add a7,a5,a7
0x60a50  lbu a7,0(a7)
0x60a54  add a7,a6,a7
0x60a58  lbu a7,0(a7)
0x60a5c  sb a7,1(a0)
0x60a60  add a2,a2,a3
0x60a64  srl a7,a2,a4
0x60a68  add a7,a5,a7
0x60a6c  lbu a7,0(a7)
0x60a70  add a7,a6,a7
0x60a74  lbu a7,0(a7)
0x60a78  sb a7,2(a0)
0x60a7c  add a2,a2,a3
0x60a80  srl a7,a2,a4
0x60a84  add a7,a5,a7
0x60a88  lbu a7,0(a7)
0x60a8c  add a7,a6,a7
0x60a90  lbu a7,0(a7)
0x60a94  sb a7,3(a0)
0x60a98  add a2,a2,a3
0x60a9c  srl a7,a2,a4
0x60aa0  add a7,a5,a7
0x60aa4  lbu a7,0(a7)
0x60aa8  add a7,a6,a7
0x60aac  lbu a7,0(a7)
0x60ab0  sb a7,4(a0)
0x60ab4  add a2,a2,a3
0x60ab8  srl a7,a2,a4
0x60abc  add a7,a5,a7
0x60ac0  lbu a7,0(a7)
0x60ac4  add a7,a6,a7
0x60ac8  lbu a7,0(a7)
0x60acc  sb a7,5(a0)
0x60ad0  add a2,a2,a3
0x60ad4  srl a7,a2,a4
0x60ad8  add a7,a5,a7
0x60adc  lbu a7,0(a7)
0x60ae0  add a7,a6,a7
0x60ae4  lbu a7,0(a7)
0x60ae8  sb a7,6(a0)
0x60aec  add a2,a2,a3
0x60af0  srl a7,a2,a4
0x60af4  add a7,a5,a7
0x60af8  lbu a7,0(a7)
0x60afc  add a7,a6,a7
0x60b00  lbu a7,0(a7)
0x60b04  sb a7,7(a0)
0x60b08  add a2,a2,a3
0x60b0c  addi a1,a1,-1
0x60b10  addi a0,a0,8
0x60b14  bne a1,zero,0x60a2c
```

**#2** `0x60bfc` `R_SpanLoop+0x38`, 83 instr, executed 61,208 times (2.81% of dynamic instrs)

```
0x60bfc  srli a6,a2,6
0x60c00  andi a6,a6,992
0x60c04  srli a7,a2,27
0x60c08  or a6,a6,a7
0x60c0c  add a6,a4,a6
0x60c10  lbu a6,0(a6)
0x60c14  add a6,a5,a6
0x60c18  lbu a6,0(a6)
0x60c1c  sb a6,0(a0)
0x60c20  add a2,a2,a3
0x60c24  srli a6,a2,6
0x60c28  andi a6,a6,992
0x60c2c  srli a7,a2,27
0x60c30  or a6,a6,a7
0x60c34  add a6,a4,a6
0x60c38  lbu a6,0(a6)
0x60c3c  add a6,a5,a6
0x60c40  lbu a6,0(a6)
0x60c44  sb a6,200(a0)
0x60c48  add a2,a2,a3
0x60c4c  srli a6,a2,6
0x60c50  andi a6,a6,992
0x60c54  srli a7,a2,27
0x60c58  or a6,a6,a7
0x60c5c  add a6,a4,a6
0x60c60  lbu a6,0(a6)
0x60c64  add a6,a5,a6
0x60c68  lbu a6,0(a6)
0x60c6c  sb a6,400(a0)
0x60c70  add a2,a2,a3
0x60c74  srli a6,a2,6
0x60c78  andi a6,a6,992
0x60c7c  srli a7,a2,27
0x60c80  or a6,a6,a7
0x60c84  add a6,a4,a6
0x60c88  lbu a6,0(a6)
0x60c8c  add a6,a5,a6
0x60c90  lbu a6,0(a6)
0x60c94  sb a6,600(a0)
0x60c98  add a2,a2,a3
0x60c9c  srli a6,a2,6
0x60ca0  andi a6,a6,992
0x60ca4  srli a7,a2,27
0x60ca8  or a6,a6,a7
0x60cac  add a6,a4,a6
0x60cb0  lbu a6,0(a6)
0x60cb4  add a6,a5,a6
0x60cb8  lbu a6,0(a6)
0x60cbc  sb a6,800(a0)
0x60cc0  add a2,a2,a3
0x60cc4  srli a6,a2,6
0x60cc8  andi a6,a6,992
0x60ccc  srli a7,a2,27
0x60cd0  or a6,a6,a7
0x60cd4  add a6,a4,a6
0x60cd8  lbu a6,0(a6)
0x60cdc  add a6,a5,a6
0x60ce0  lbu a6,0(a6)
0x60ce4  sb a6,1000(a0)
0x60ce8  add a2,a2,a3
0x60cec  srli a6,a2,6
0x60cf0  andi a6,a6,992
0x60cf4  srli a7,a2,27
0x60cf8  or a6,a6,a7
0x60cfc  add a6,a4,a6
0x60d00  lbu a6,0(a6)
0x60d04  add a6,a5,a6
0x60d08  lbu a6,0(a6)
0x60d0c  sb a6,1200(a0)
0x60d10  add a2,a2,a3
0x60d14  srli a6,a2,6
0x60d18  andi a6,a6,992
0x60d1c  srli a7,a2,27
0x60d20  or a6,a6,a7
0x60d24  add a6,a4,a6
0x60d28  lbu a6,0(a6)
0x60d2c  add a6,a5,a6
0x60d30  lbu a6,0(a6)
0x60d34  sb a6,1400(a0)
0x60d38  add a2,a2,a3
0x60d3c  addi a1,a1,-1
0x60d40  addi a0,a0,1600
0x60d44  bne a1,zero,0x60bfc
```

**#3** `0x5728c` `R_MapPlane+0xc0`, 48 instr, executed 82,810 times (2.20% of dynamic instrs)

```
0x5728c  lw a2,-212(gp)
0x57290  mul a7,a2,a3
0x57294  mulh a2,a2,a3
0x57298  srli a7,a7,16
0x5729c  slli a2,a2,16
0x572a0  lw t0,-216(gp)
0x572a4  or a2,a2,a7
0x572a8  lw t1,-220(gp)
0x572ac  mul t2,a2,t0
0x572b0  mulh t0,a2,t0
0x572b4  lw a7,-224(gp)
0x572b8  mul t4,a2,t1
0x572bc  mulh a2,a2,t1
0x572c0  slli t0,t0,16
0x572c4  srli t2,t2,16
0x572c8  lw t3,-228(gp)
0x572cc  mul t5,a3,a7
0x572d0  mulh a7,a3,a7
0x572d4  slli a2,a2,16
0x572d8  srli t4,t4,16
0x572dc  lw t1,-320(gp)
0x572e0  or t0,t2,t0
0x572e4  mul t2,a3,t3
0x572e8  mulh a3,a3,t3
0x572ec  lw t3,-324(gp)
0x572f0  or a2,t4,a2
0x572f4  slli a7,a7,10
0x572f8  srli t4,t5,22
0x572fc  add a2,t3,a2
0x57300  sub t1,zero,t1
0x57304  sub t0,t1,t0
0x57308  slli a3,a3,26
0x5730c  srli t1,t2,6
0x57310  or a7,t4,a7
0x57314  srli a2,a2,6
0x57318  slli t0,t0,10
0x5731c  or a3,t1,a3
0x57320  lui t1,0xffff0
0x57324  slli a7,a7,16
0x57328  slli a2,a2,16
0x5732c  srli t0,t0,16
0x57330  and a3,a3,t1
0x57334  srli a7,a7,16
0x57338  or a2,t0,a2
0x5733c  or a3,a3,a7
0x57340  mul a6,a6,a3
0x57344  add a2,a2,a6
0x57348  jal zero,0x60bc4
```

**#4** `0x5cb94` `rec_get+0x24`, 10 instr, executed 298,893 times (1.66% of dynamic instrs)

```
0x5cb94  lw a4,332(gp)
0x5cb98  slli a5,a0,23
0x5cb9c  srli a5,a5,28
0x5cba0  slli a6,a5,3
0x5cba4  add a6,a4,a6
0x5cba8  addi t0,a6,2047
0x5cbac  lhu a6,1(t0)
0x5cbb0  slli a7,a0,7
0x5cbb4  srli a7,a7,16
0x5cbb8  bne a6,a7,0x5cbc8
```

**#5** `0x5d3e0` `rc_fill`, 26 instr, executed 111,537 times (1.61% of dynamic instrs)

```
0x5d3e0  addi sp,sp,-32
0x5d3e4  sw ra,28(sp)
0x5d3e8  sw s0,24(sp)
0x5d3ec  sw s1,20(sp)
0x5d3f0  sw s2,16(sp)
0x5d3f4  sw s3,12(sp)
0x5d3f8  sw s4,8(sp)
0x5d3fc  lw a1,332(gp)
0x5d400  addi s0,a0,0
0x5d404  andi s1,a0,15
0x5d408  add a0,a1,s1
0x5d40c  addi a0,a0,2047
0x5d410  lbu a0,129(a0)
0x5d414  slli a2,s1,2
0x5d418  srli s2,a0,6
0x5d41c  or s4,a2,s2
0x5d420  slli s3,s4,1
0x5d424  add a0,a1,s3
0x5d428  addi a0,a0,2047
0x5d42c  addi a3,zero,-1
0x5d430  lw a2,888(gp)
0x5d434  sh a3,1(a0)
0x5d438  slli a0,s0,5
0x5d43c  addi a5,a0,32
0x5d440  addi a3,gp,888
0x5d444  bltu a2,a5,0x5d450
```

**#6** `0x5d4b0` `rc_fill+0xd0`, 24 instr, executed 111,537 times (1.48% of dynamic instrs)

```
0x5d4b0  lw a0,332(gp)
0x5d4b4  srli s0,s0,4
0x5d4b8  add s3,a0,s3
0x5d4bc  addi a1,s3,2047
0x5d4c0  add s1,a0,s1
0x5d4c4  addi a2,s1,2047
0x5d4c8  lbu a3,129(a2)
0x5d4cc  sh s0,1(a1)
0x5d4d0  slli s2,s2,8
0x5d4d4  lui a1,0x23
0x5d4d8  addi a1,a1,-868
0x5d4dc  add a1,a1,a3
0x5d4e0  add a1,a1,s2
0x5d4e4  lbu a1,0(a1)
0x5d4e8  add a0,a0,s4
0x5d4ec  sb a1,129(a2)
0x5d4f0  lw ra,28(sp)
0x5d4f4  lw s0,24(sp)
0x5d4f8  lw s1,20(sp)
0x5d4fc  lw s2,16(sp)
0x5d500  lw s3,12(sp)
0x5d504  lw s4,8(sp)
0x5d508  addi sp,sp,32
0x5d50c  jalr zero,0(ra)
```

**#7** `0x582c0` `R_ReplayWall+0xba4`, 32 instr, executed 76,102 times (1.35% of dynamic instrs)

```
0x582c0  addi a3,a0,-256
0x582c4  srli a3,a3,1
0x582c8  andi a4,a3,-4
0x582cc  lui a5,0x27
0x582d0  addi a5,a5,-1516
0x582d4  add a4,a5,a4
0x582d8  lw a5,4(a4)
0x582dc  lw a6,0(a4)
0x582e0  lw a4,8(a4)
0x582e4  andi a7,a0,7
0x582e8  sub t0,a5,a6
0x582ec  slli a5,a5,1
0x582f0  add a4,a6,a4
0x582f4  lui t1,0x27
0x582f8  addi t1,t1,-612
0x582fc  add a3,t1,a3
0x58300  lbu a3,0(a3)
0x58304  sub a4,a4,a5
0x58308  andi a2,a2,4
0x5830c  xori a2,a2,28
0x58310  sll a2,a3,a2
0x58314  srai a2,a2,28
0x58318  mul a3,t0,a7
0x5831c  srai a3,a3,3
0x58320  add a3,a3,a6
0x58324  ori a0,a0,-8
0x58328  mul a0,a0,a7
0x5832c  mul a0,a0,a4
0x58330  srai a0,a0,7
0x58334  add a0,a3,a0
0x58338  add a0,a0,a2
0x5833c  beq a1,zero,0x58344
```

**#8** `0x6155c` `dmc_tantoangle`, 35 instr, executed 54,938 times (1.06% of dynamic instrs)

```
0x6155c  srli a1,a0,3
0x61560  andi a1,a1,-4
0x61564  lui a2,0x27
0x61568  addi a2,a2,544
0x6156c  add a2,a2,a1
0x61570  lw a2,0(a2)
0x61574  andi a3,a0,31
0x61578  mulh a4,a2,a3
0x6157c  lui a5,0x27
0x61580  addi a5,a5,804
0x61584  add a5,a5,a1
0x61588  lw a5,0(a5)
0x6158c  mul a2,a2,a3
0x61590  addi a6,a3,-31
0x61594  mul a3,a6,a3
0x61598  mulh a6,a5,a3
0x6159c  mul a3,a5,a3
0x615a0  add a2,a3,a2
0x615a4  sltu a3,a2,a3
0x615a8  add a4,a6,a4
0x615ac  add a3,a4,a3
0x615b0  lui a4,0x27
0x615b4  addi a4,a4,284
0x615b8  add a1,a4,a1
0x615bc  lw a1,0(a1)
0x615c0  lui a4,0x27
0x615c4  addi a4,a4,1064
0x615c8  add a0,a4,a0
0x615cc  lb a0,0(a0)
0x615d0  slli a3,a3,20
0x615d4  srli a2,a2,12
0x615d8  or a2,a2,a3
0x615dc  add a0,a1,a0
0x615e0  add a0,a0,a2
0x615e4  jalr zero,0(ra)
```

**#9** `0x68b6c` `nor_read+0xb8`, 14 instr, executed 111,593 times (0.87% of dynamic instrs)

```
0x68b6c  addi a3,zero,368
0x68b70  addi a4,zero,3
0x68b74  lw a5,0(a3)
0x68b78  lw a6,4(a3)
0x68b7c  lw a7,8(a3)
0x68b80  lw t0,12(a3)
0x68b84  sw a5,0(a1)
0x68b88  sw a6,4(a1)
0x68b8c  sw a7,8(a1)
0x68b90  sw t0,12(a1)
0x68b94  addi a3,a3,16
0x68b98  addi a0,a0,-4
0x68b9c  addi a1,a1,16
0x68ba0  bltu a4,a0,0x68b74
```

**#10** `0x5d454` `rc_fill+0x74`, 14 instr, executed 111,537 times (0.86% of dynamic instrs)

```
0x5d454  lw a3,4(a3)
0x5d458  sltu a3,a0,a3
0x5d45c  xori a3,a3,1
0x5d460  slli a4,a3,2
0x5d464  slli a3,a3,4
0x5d468  sub a3,a3,a4
0x5d46c  addi a4,gp,864
0x5d470  add a3,a4,a3
0x5d474  lw a5,0(a3)
0x5d478  lw a4,4(a3)
0x5d47c  sub a6,a0,a5
0x5d480  sub a5,a4,a5
0x5d484  slli s4,s4,5
0x5d488  bgeu a6,a5,0x5d4a8
```

## Block length distribution (weighted by dynamic instructions)

| Length | Static blocks | Dyn blocks | % of dyn blocks | Dyn instrs | % of dyn instrs |
|---|---|---|---|---|---|
| 1 | 616 | 2,780,392 | 11.42% | 2,780,392 | 1.54% |
| 2 | 903 | 4,585,955 | 18.84% | 9,171,910 | 5.08% |
| 3 | 785 | 4,166,302 | 17.11% | 12,498,906 | 6.92% |
| 4 | 482 | 2,336,234 | 9.60% | 9,344,936 | 5.18% |
| 5-6 | 625 | 3,242,718 | 13.32% | 18,025,108 | 9.98% |
| 7-8 | 369 | 1,670,760 | 6.86% | 12,562,925 | 6.96% |
| 9-12 | 447 | 2,361,791 | 9.70% | 24,408,745 | 13.52% |
| 13-16 | 208 | 1,349,786 | 5.54% | 18,972,605 | 10.51% |
| 17-32 | 149 | 903,151 | 3.71% | 21,368,951 | 11.84% |
| 33+ | 32 | 949,339 | 3.90% | 51,415,625 | 28.48% |

## Branch-target distributions

How dynamic blocks end:

| Terminator | Dyn blocks | % of blocks |
|---|---|---|
| cond branch | 17,525,704 | 71.98% |
| jal | 4,377,301 | 17.98% |
| jalr | 2,442,065 | 10.03% |
| ecall | 1,358 | 0.01% |

- Blocks that always went to one successor: 41.00% of dynamic blocks.
- Share of block exits that went to that block's single most frequent successor: 86.13% (an upper bound for a "follow the hottest edge" static trace).
- Conditional branches: 17,525,704 executions; the dominant direction per branch site covers 87.43% of them.
- `jalr` exits (returns and indirect calls): 2,442,065; dominant target per site covers 51.87%; sites with more than 8 distinct targets (spill to "other"): 31.

Successor distribution of the five hottest blocks that have more than one successor:

| Block | Ends with | Targets (share of exits) |
|---|---|---|
| `0x60a2c` `R_ColumnLoop+0x30` | cond branch | 0x60a2c 94.2%, 0x60b18 5.8% |
| `0x5cb94` `rec_get+0x24` | cond branch | 0x5cbc8 82.5%, 0x5cbbc 17.5% |
| `0x5d4b0` `rc_fill+0xd0` | jalr | 0x5ccd4 82.1%, 0x5d1a4 8.3%, 0x5d3c0 7.2%, 0x5d7f4 2.3% |
| `0x582c0` `R_ReplayWall+0xba4` | cond branch | 0x58340 60.7%, 0x58344 39.3% |
| `0x6155c` `dmc_tantoangle` | jalr | 0x5653c 43.0%, 0x54efc 6.9%, 0x54f10 6.8%, 0x54d04 3.0%, 0x565a0 3.0%, 0x56550 2.7%, other 31.5% |

## Memory access pattern

Loads 41,341,059 (22.90% of instrs), stores 21,779,138 (12.06%); blocks with at least one memory op: 61.03% of dynamic blocks. Slot = one load/store site in a block; stride = address delta between two consecutive executions of the same site.

| Per-site pattern (weighted by executions) | Accesses | % |
|---|---|---|
| same address | 34,555,935 | 54.75% |
| irregular (no stride >= 50%) | 19,844,783 | 31.44% |
| small stride (<= 64 B) | 5,980,479 | 9.47% |
| unit stride (= access width) | 2,732,786 | 4.33% |
| large stride (> 64 B) | 5,004 | 0.01% |
| single execution | 1,210 | 0.00% |

| Access | Base register | Target area (site min address) | Accesses | % |
|---|---|---|---|---|
| ld | other base | RAM | 26,677,679 | 42.26% |
| st | other base | RAM | 15,589,449 | 24.70% |
| ld | sp-relative | RAM | 7,793,999 | 12.35% |
| ld | other base | data ROM | 6,869,381 | 10.88% |
| st | sp-relative | RAM | 6,189,689 | 9.81% |

Memory sites of the hottest blocks (first 12 sites over the 8 hottest blocks):

| Block | Site pc | Kind | Bytes | Base | Execs | Address range | Top strides (delta:count) |
|---|---|---|---|---|---|---|---|
| `0x60a2c` | `0x60a34` | ld | 1 | a7 | 553,639 | 0xadc-0xc59 | +2:26932, +3:10198, +123:105 |
| `0x60a2c` | `0x60a3c` | ld | 1 | a7 | 553,639 | 0x2413e-0x25a2c | +0:251325, -3:7815, +3:6375 |
| `0x60a2c` | `0x60a40` | st | 1 | a0 | 553,639 | 0x16c0-0x2338 | +8:538600, +184:1248, +183:84 |
| `0x60a2c` | `0x60a50` | ld | 1 | a7 | 553,639 | 0xadc-0xc5a | +2:26808, +3:10164, +123:93 |
| `0x60a2c` | `0x60a58` | ld | 1 | a7 | 553,639 | 0x2413e-0x259aa | +0:251314, -2:20525, +2:8181 |
| `0x60a2c` | `0x60a5c` | st | 1 | a0 | 553,639 | 0x16c1-0x2339 | +8:538600, +184:1248, +183:84 |
| `0x60a2c` | `0x60a6c` | ld | 1 | a7 | 553,639 | 0xadc-0xc5a | +2:26719, +3:10345, +123:74 |
| `0x60a2c` | `0x60a74` | ld | 1 | a7 | 553,639 | 0x2413e-0x259d8 | +0:251449, -2:20521, +2:8308 |
| `0x60a2c` | `0x60a78` | st | 1 | a0 | 553,639 | 0x16c2-0x233a | +8:538600, +184:1248, +183:84 |
| `0x60a2c` | `0x60a88` | ld | 1 | a7 | 553,639 | 0xadc-0xc5b | +2:27043, +3:10126, +123:92 |
| `0x60a2c` | `0x60a90` | ld | 1 | a7 | 553,639 | 0x2413e-0x25a2b | +0:251537, -2:20518, +2:8494 |
| `0x60a2c` | `0x60a94` | st | 1 | a0 | 553,639 | 0x16c3-0x233b | +8:538600, +184:1248, +183:84 |

## Per-tic instruction counts

A tic is one entry of `G_Ticker` (the first 208,118 instructions are boot and level load before it). 349 complete tics.

| Statistic | Instrs per tic | Blocks per tic |
|---|---|---|
| mean | 513,121 | 68,965 |
| median | 185,343 | 31,270 |
| p90 | 1,188,117 | 159,339 |
| max | 2,819,938 | 456,310 |
| sum | 179,079,330 | 24,068,656 |

Ten most expensive tics, and a coarse view of the cost profile:

| Tic | Start instr | Instrs | Blocks | Loads | Stores |
|---|---|---|---|---|---|
| 0 | 208,118 | 2,819,938 | 456,310 | 589,791 | 313,887 |
| 16 | 16,216,561 | 2,367,095 | 317,756 | 518,660 | 257,921 |
| 18 | 18,600,097 | 2,362,937 | 326,663 | 512,506 | 253,367 |
| 13 | 13,906,368 | 2,248,000 | 304,509 | 491,418 | 244,789 |
| 11 | 11,689,061 | 2,197,238 | 297,667 | 476,952 | 237,046 |
| 9 | 9,503,641 | 2,166,607 | 293,978 | 469,826 | 232,724 |
| 4 | 5,186,238 | 2,147,981 | 291,974 | 463,162 | 229,284 |
| 2 | 3,036,775 | 2,131,905 | 289,468 | 459,940 | 227,535 |
| 6 | 7,358,444 | 2,117,262 | 287,189 | 458,867 | 226,687 |
| 23 | 23,029,151 | 2,070,605 | 269,664 | 437,911 | 203,427 |

| Tics | Mean instrs/tic | Min | Max |
|---|---|---|---|
| 0-49 | 917,008 | 8,719 | 2,819,938 |
| 50-99 | 490,153 | 26,042 | 1,410,719 |
| 100-149 | 453,351 | 21,349 | 1,210,001 |
| 150-199 | 404,070 | 28,565 | 1,421,938 |
| 200-249 | 460,375 | 20,980 | 1,168,236 |
| 250-299 | 486,920 | 29,130 | 1,499,238 |
| 300-348 | 377,255 | 16,522 | 1,197,539 |

The full per-tic list is `docs/research/bbtrace/tics.tsv`. The README quotes 485,801 instr/tic as the mean over tics 30-300 of the chip-ROM build; the all-tics mean here covers the cold tics too, so the two are not directly comparable.

## Hot consecutive pairs and triples

Counts are over the executed stream, so a pair whose first instruction is a taken branch is a real cross-block adjacency. Pairs that are statically adjacent (pc2 = pc1 + 4) are marked **seq**; others are marked **jump**.

Coverage of the executed stream by the top-N distinct pairs / triples (by pc):

| N | Pairs: % of consecutive pairs | Triples: % of consecutive triples |
|---|---|---|
| top 10 | 3.18% | 3.18% |
| top 50 | 15.65% | 15.64% |
| top 100 | 24.59% | 24.47% |
| top 500 | 48.06% | 47.47% |
| top 1000 | 63.85% | 63.00% |
| top 5000 | 94.14% | 93.27% |

Top 20 pairs by pc:

| pc1 | Instr 1 | Instr 2 | Adjacency | Count | % of pairs |
|---|---|---|---|---|---|
| `0x60af8` | `lbu a7,0(a7)` | `add a7,a6,a7` | seq | 574,516 | 0.32% |
| `0x60af0` | `srl a7,a2,a4` | `add a7,a5,a7` | seq | 574,516 | 0.32% |
| `0x60afc` | `add a7,a6,a7` | `lbu a7,0(a7)` | seq | 574,516 | 0.32% |
| `0x60b00` | `lbu a7,0(a7)` | `sb a7,7(a0)` | seq | 574,516 | 0.32% |
| `0x60af4` | `add a7,a5,a7` | `lbu a7,0(a7)` | seq | 574,516 | 0.32% |
| `0x60b0c` | `addi a1,a1,-1` | `addi a0,a0,8` | seq | 574,516 | 0.32% |
| `0x60b10` | `addi a0,a0,8` | `bne a1,zero,0x60a2c` | seq | 574,516 | 0.32% |
| `0x60b04` | `sb a7,7(a0)` | `add a2,a2,a3` | seq | 574,516 | 0.32% |
| `0x60b08` | `add a2,a2,a3` | `addi a1,a1,-1` | seq | 574,516 | 0.32% |
| `0x60aec` | `add a2,a2,a3` | `srl a7,a2,a4` | seq | 570,652 | 0.32% |
| `0x60ad4` | `srl a7,a2,a4` | `add a7,a5,a7` | seq | 570,652 | 0.32% |
| `0x60adc` | `lbu a7,0(a7)` | `add a7,a6,a7` | seq | 570,652 | 0.32% |
| `0x60ae4` | `lbu a7,0(a7)` | `sb a7,6(a0)` | seq | 570,652 | 0.32% |
| `0x60ae0` | `add a7,a6,a7` | `lbu a7,0(a7)` | seq | 570,652 | 0.32% |
| `0x60ad8` | `add a7,a5,a7` | `lbu a7,0(a7)` | seq | 570,652 | 0.32% |
| `0x60ae8` | `sb a7,6(a0)` | `add a2,a2,a3` | seq | 570,652 | 0.32% |
| `0x60ac4` | `add a7,a6,a7` | `lbu a7,0(a7)` | seq | 567,725 | 0.31% |
| `0x60abc` | `add a7,a5,a7` | `lbu a7,0(a7)` | seq | 567,725 | 0.31% |
| `0x60ab8` | `srl a7,a2,a4` | `add a7,a5,a7` | seq | 567,725 | 0.31% |
| `0x60acc` | `sb a7,5(a0)` | `add a2,a2,a3` | seq | 567,725 | 0.31% |

Top 15 triples by pc:

| pc1 | Instructions | Count | % of triples |
|---|---|---|---|
| `0x60af0` | `srl a7,a2,a4; add a7,a5,a7; lbu a7,0(a7)` | 574,516 | 0.32% |
| `0x60afc` | `add a7,a6,a7; lbu a7,0(a7); sb a7,7(a0)` | 574,516 | 0.32% |
| `0x60af8` | `lbu a7,0(a7); add a7,a6,a7; lbu a7,0(a7)` | 574,516 | 0.32% |
| `0x60b04` | `sb a7,7(a0); add a2,a2,a3; addi a1,a1,-1` | 574,516 | 0.32% |
| `0x60b00` | `lbu a7,0(a7); sb a7,7(a0); add a2,a2,a3` | 574,516 | 0.32% |
| `0x60af4` | `add a7,a5,a7; lbu a7,0(a7); add a7,a6,a7` | 574,516 | 0.32% |
| `0x60b08` | `add a2,a2,a3; addi a1,a1,-1; addi a0,a0,8` | 574,516 | 0.32% |
| `0x60b0c` | `addi a1,a1,-1; addi a0,a0,8; bne a1,zero,0x60a2c` | 574,516 | 0.32% |
| `0x60aec` | `add a2,a2,a3; srl a7,a2,a4; add a7,a5,a7` | 570,652 | 0.32% |
| `0x60ae4` | `lbu a7,0(a7); sb a7,6(a0); add a2,a2,a3` | 570,652 | 0.32% |
| `0x60adc` | `lbu a7,0(a7); add a7,a6,a7; lbu a7,0(a7)` | 570,652 | 0.32% |
| `0x60ad8` | `add a7,a5,a7; lbu a7,0(a7); add a7,a6,a7` | 570,652 | 0.32% |
| `0x60ae8` | `sb a7,6(a0); add a2,a2,a3; srl a7,a2,a4` | 570,652 | 0.32% |
| `0x60ad4` | `srl a7,a2,a4; add a7,a5,a7; lbu a7,0(a7)` | 570,652 | 0.32% |
| `0x60ae0` | `add a7,a6,a7; lbu a7,0(a7); sb a7,6(a0)` | 570,652 | 0.32% |

Opcode-class patterns (operands ignored), top 15 pairs and top 10 triples:

| Pair | Count | % of pairs |
|---|---|---|
| add ; lbu | 11,151,816 | 6.18% |
| lw ; lw | 10,537,670 | 5.84% |
| sw ; sw | 7,864,904 | 4.36% |
| addi ; addi | 5,701,601 | 3.16% |
| lbu ; add | 5,613,074 | 3.11% |
| lbu ; sb | 5,322,422 | 2.95% |
| sb ; add | 5,083,156 | 2.82% |
| srl ; add | 4,536,577 | 2.51% |
| add ; srl | 3,931,060 | 2.18% |
| lw ; addi | 2,945,956 | 1.63% |
| add ; addi | 2,754,978 | 1.53% |
| slli ; srli | 2,461,195 | 1.36% |
| slli ; add | 2,444,264 | 1.35% |
| addi ; jal | 2,141,746 | 1.19% |
| addi ; beq | 2,056,885 | 1.14% |

| Triple | Count | % of triples |
|---|---|---|
| lw ; lw ; lw | 6,127,644 | 3.39% |
| sw ; sw ; sw | 5,403,321 | 2.99% |
| add ; lbu ; add | 5,279,243 | 2.92% |
| add ; lbu ; sb | 5,215,673 | 2.89% |
| lbu ; add ; lbu | 5,178,146 | 2.87% |
| lbu ; sb ; add | 5,078,447 | 2.81% |
| srl ; add ; lbu | 4,505,574 | 2.50% |
| add ; srl ; add | 3,931,060 | 2.18% |
| sb ; add ; srl | 3,931,058 | 2.18% |
| addi ; sw ; sw | 1,285,812 | 0.71% |

## Estimated reduction in neural transitions from fusion (an estimate, not a speedup)

Model of the estimate. One guest instruction is one neural transition today; the repo measured 1.345 to 1.468 chip tokens per instruction (README / STATUS.md). Suppose some instructions that execute consecutively inside one basic block could be executed as **one** transition. The count of transitions then falls from `N` to `T`. Because the table assumes a fused transition costs the same 1.345-1.468 tokens as an unfused one, token counts scale with `T` and the reduction percentage is identical in both columns.

What this ignores, so read it as an optimistic bound on *transition count* only: the cost of encoding a fused operation in the chip (a fused step may need more tokens, more layers or a larger weight footprint), data dependencies between the fused instructions, the memory-model and fetch constraints of the circuit, per-segment host snapshotting, and any change to the lockstep oracle. Wall-clock speed is not derived anywhere in this file.

Baseline: N = 180,550,104 transitions = 242,839,890 to 265,047,553 chip tokens.

### A. Fuse k consecutive instructions inside every block (generic bound)

Each block of length `L` executes `ceil(L/k)` transitions (instructions grouped from the block start). `k = block` means a whole block is one transition. The tail open block (1 instr) is counted as 1 transition.

| k | Transitions T | Chip tokens (1.345 - 1.468 per transition) | Transitions removed | Reduction |
|---|---|---|---|---|
| 1 (baseline) | 180,550,104 | 242,839,890 - 265,047,553 | 0 | 0.00% |
| 2 | 96,089,548 | 129,240,442 - 141,059,456 | 84,460,556 | 46.78% |
| 3 | 68,437,104 | 92,047,905 - 100,465,669 | 112,113,000 | 62.10% |
| 4 | 54,903,818 | 73,845,635 - 80,598,805 | 125,646,286 | 69.59% |
| 8 | 36,253,969 | 48,761,588 - 53,220,826 | 144,296,135 | 79.92% |
| 16 | 27,898,968 | 37,524,112 - 40,955,685 | 152,651,136 | 84.55% |
| whole block | 24,346,429 | 32,745,947 - 35,740,558 | 156,203,675 | 86.52% |

Only the hottest blocks fused whole (all other code unfused): the transitions removed are `sum(count * (L - 1))` over those blocks.

| Blocks fused whole | % of dyn instrs covered | Transitions T | Reduction |
|---|---|---|---|
| top 1 | 18.09% | 148,439,042 | 17.79% |
| top 5 | 26.37% | 134,049,454 | 25.75% |
| top 10 | 32.00% | 124,356,359 | 31.12% |
| top 20 | 39.58% | 112,241,348 | 37.83% |
| top 50 | 53.97% | 89,111,676 | 50.64% |
| top 100 | 65.69% | 71,274,049 | 60.52% |
| top 200 | 77.04% | 54,758,429 | 69.67% |
| top 500 | 89.95% | 36,699,951 | 79.67% |
| top 1000 | 96.81% | 28,075,553 | 84.45% |

### B. Fuse only specific opcode-class pairs (a small library of fused ops)

Candidate pairs are adjacent instruction pairs *inside* a block, keyed by opcode class (operands ignored), ranked by dynamic count. For a library of the top M classes, each block is scanned left to right and an adjacent pair is fused when its class is in the library (non-overlapping, greedy). Register and immediate constraints of a real fused op are ignored.

| Library size M (classes) | Transitions T | Transitions removed | Reduction |
|---|---|---|---|
| 1 | 169,398,288 | 11,151,816 | 6.18% |
| 2 | 162,314,424 | 18,235,680 | 10.10% |
| 4 | 152,800,454 | 27,749,650 | 15.37% |
| 8 | 147,275,472 | 33,274,632 | 18.43% |
| 16 | 133,322,787 | 47,227,317 | 26.16% |
| 32 | 123,730,961 | 56,819,143 | 31.47% |
| 64 | 113,220,729 | 67,329,375 | 37.29% |
| all 679 | 96,089,548 | 84,460,556 | 46.78% |

Top in-block opcode-class pairs feeding that table:

| Pair | Dynamic count | % of N |
|---|---|---|
| add ; lbu | 11,151,816 | 6.18% |
| lw ; lw | 10,537,670 | 5.84% |
| sw ; sw | 7,864,904 | 4.36% |
| addi ; addi | 5,701,601 | 3.16% |
| lbu ; add | 5,613,074 | 3.11% |
| lbu ; sb | 5,322,422 | 2.95% |
| sb ; add | 5,083,156 | 2.82% |
| srl ; add | 4,536,577 | 2.51% |
| add ; srl | 3,931,060 | 2.18% |
| lw ; addi | 2,945,956 | 1.63% |
| add ; addi | 2,754,978 | 1.53% |
| slli ; srli | 2,461,195 | 1.36% |

### How to read it

- Section A with `k = 2` is the ceiling for any "fuse two adjacent instructions" scheme; section B is what a realistic small set of fused pair ops could approach.
- Whole-block fusion is an upper bound that needs one transition to execute an arbitrary-length, data-dependent sequence, which the current circuit cannot do; it shows where the floor of the count would be if branch and memory behaviour were free.
- No result here says how long a fused run would take.

## Caveats

- Host emulator, one workload (scripted E1M1 with host-served disk, 350 tics). The chunk-ROM variant (199.7 M instr, 4 disk requests) changes the mix of the disk-request code.
- Block boundaries follow retired control transfers only; interrupts do not exist in this machine, and `ecall` ends a block because it is a host-visible event, not because it redirects control.
- Per-site stride uses an exact histogram of the first four distinct strides per site; sites with more distinct strides spill into "other" and are classed by their dominant stride only if it is >= 50 %.
- Reproduction check: the host-served-disk dry run in this trace executes 180,550,104 instructions over 349 tics with 165,054 disk requests, matching the 180.5 M / 165,054 figures in the README. During the same `make demo-elf` the chunk-ROM verification run (`CRXPLAN`) exited early with code 99 after 90,889 instructions in this environment (engine tree copied from a sibling worktree), so the 81 M / 199.7 M chunk-ROM figures were **not** reproduced here and were not traced; this was not investigated.
- Memory-site tracking is capped at 64 sites per block. Blocks at the cap in this run: 1 (`0x5f658` len 99 executed 1x). Accesses in the global load/store counters but missing from the per-site tables (Memory section): 6 of 63,120,203.
