.section .text.start,"ax"
.globl _start
_start:
 la sp,qos_kstack+128
 /* The merged snapshot ELF (tools/merge_elf.py) ships the kernel's .bss as zero-filled
    bytes and the rest of RAM is zero at power-on, so no runtime bss clear (a byte loop
    over 5.5 KB was 22,000 instructions = 30,000 chip tokens). The warm reboot after a
    /bin/doomd takeover zeroes the overlay itself (qos_takeover_run). */
 call qos_main
 li a7,93
 ecall
3: j 3b

/* Abandon the current (shell) stack and continue on the small resident kernel
   stack in the core region. Used by /bin/doomd takeover; never returns. */
.globl qos_takeover_enter
qos_takeover_enter:
 la sp,__tstack_top
 call qos_takeover_run
4: j 4b

/* After the takeover returned and the overlay was zeroed: back onto the normal kernel stack (in the
   overlay) and warm-reboot via qos_resume. */
.globl qos_resume_enter
qos_resume_enter:
 la sp,qos_kstack+128
 call qos_resume
5: j 5b

/* Key-wait park point (see include/qos.h). One instruction; a driver breaks here. */
.globl qos_key_park
qos_key_park:
 ret
