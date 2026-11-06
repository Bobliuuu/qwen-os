#pragma once
#include <stdint.h>
#include "qos.h"
extern const qos_api *qapi;
/* /bin/doomd owns RAM and runs on the trusted takeover path: console bytes go straight to the host
   ecall (same ecall the kernel's PUTC issues), the mailboxes and framebuffer are accessed directly. */
static inline __attribute__((always_inline)) void q_putc(int c)
{
    register uint32_t a0 __asm__("a0") = (uint8_t)c, a7 __asm__("a7") = 1;
    __asm__ volatile("ecall" : "+r"(a0) : "r"(a7) : "memory");
}
typedef struct { uint32_t request_seq, offset, length, ready_seq, status; uint8_t bytes[QOS_DISK_WINDOW]; } q_diskmb_t;
#define Q_DISKMB ((volatile q_diskmb_t *)QOS_DISK_MB)
#define Q_INMB ((volatile uint32_t *)QOS_IN_MB) /* [0]=seq [1]=key */
#define Q_FB ((volatile uint8_t *)QOS_FB_ADDR)
void q_puts(const char *s);
void q_putu(uint32_t v);
void q_puthex(uint32_t v);
extern uint32_t q_dump_req, q_keys;
void q_input_init(void);
