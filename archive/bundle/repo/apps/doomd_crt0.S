/* /bin/doomd C runtime entry. The kernel calls app_main(api) with sp=0x8000.
 * RAM is dirty (shell/RAMFS state) and .data is not preloaded: copy it from
 * its data-ROM image and zero .bss, then call doomd_main(api).
 * RV32IM, no compressed instructions. */
.section .text.start,"ax"
.globl app_main
app_main:
 addi sp,sp,-16
 sw ra,12(sp)
 sw a0,8(sp)
 la t0,__data_load
 la t1,__data_start
 la t2,__data_end
1: bgeu t1,t2,2f
 lw t3,0(t0)
 sw t3,0(t1)
 addi t0,t0,4
 addi t1,t1,4
 j 1b
2: la t1,__bss_start
 la t2,__bss_end
3: bgeu t1,t2,4f
 sw zero,0(t1)
 addi t1,t1,4
 j 3b
4: lw a0,8(sp)
 call doomd_main
 lw ra,12(sp)
 addi sp,sp,16
 ret
