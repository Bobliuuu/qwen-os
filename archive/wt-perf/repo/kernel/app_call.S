/* Call a separately linked ROM program on its own RAM stack.
 * a0: entry, a1: qos_api *, a2: stack top. Returns program's a0.
 * The parent stack (including nested shell calls) is restored on return.
 * Qwenputer RV32IM only; applications are NOT hardware isolated.
 */
.section .text
.globl qos_app_call
.type qos_app_call,@function
qos_app_call:
    addi sp,sp,-16
    sw ra,12(sp)
    sw s0,8(sp)
    mv s0,sp
    mv t0,a0
    mv a0,a1
    mv sp,a2
    andi sp,sp,-16
    jalr ra,t0,0
    mv sp,s0
    lw ra,12(sp)
    lw s0,8(sp)
    addi sp,sp,16
    ret
