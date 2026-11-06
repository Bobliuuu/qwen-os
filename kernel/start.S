.section .text.start,"ax"
.globl _start
_start:
 la sp,qos_kstack+128
 /* Upstream Qwenputer ELF snapshot preloads .data into guest RAM.
    Do not recopy from a nonexistent runtime load address. */
 la t1,__bss_start
 la t2,__bss_end
1: beq t1,t2,2f
 sb zero,0(t1)
 addi t1,t1,1
 j 1b
2: call qos_main
 li a7,93
 ecall
3: j 3b

/* Abandon the current (shell) stack and continue on the tiny resident takeover
   stack in the core region. Used by /bin/doomd takeover; never returns. */
.globl qos_takeover_enter
qos_takeover_enter:
 la sp,__tstack_top
 call qos_takeover_run
4: j 4b

/* After the takeover returned and the overlay was zeroed: back onto the normal kernel stack
   (in the overlay) and warm-reboot via qos_resume. */
.globl qos_resume_enter
qos_resume_enter:
 la sp,qos_kstack+128
 call qos_resume
5: j 5b
