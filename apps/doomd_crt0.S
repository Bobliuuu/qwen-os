/* /bin/doomd C runtime entry. The kernel calls app_main(api) with sp=0x8000.
 * RAM from 0x570 up is ZERO on entry (the kernel clears what the shell/apps dirtied, see
 * qos_takeover_run) but .data is not preloaded: copy it from its data-ROM image, then call
 * doomd_main(api). (.bss needs no clearing.)
 * RV32IM, no compressed instructions. */
.section .text.start,"ax"
.globl app_main
app_main:
 addi sp,sp,-16
 sw ra,12(sp)
 sw a0,8(sp)
 sw gp,4(sp)
.option push
.option norelax
 la gp,__global_pointer$
.option pop
 la t0,__data_load
 la t1,__data_start
 la t2,__data_end
1: bgeu t1,t2,2f
 lw t3,0(t0)
 sw t3,0(t1)
 addi t0,t0,4
 addi t1,t1,4
 j 1b
2: /* no .bss clear: the kernel hands over RAM that is already zero (qos_takeover_run) */
 lw a0,8(sp)
 call doomd_main
 lw gp,4(sp)
 lw ra,12(sp)
 addi sp,sp,16
 ret
