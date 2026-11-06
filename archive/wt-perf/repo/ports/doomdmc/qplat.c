// SPDX-License-Identifier: GPL-2.0-or-later
// QwenOS platform layer for DMC100-Doom (replaces DMC100's AT32 Thumb/USB/FAT/LCD platform):
// virtual clock, key mailbox -> button/pad state, NOR over the 256-byte block device HAL,
// and the C runtime pieces the engine needs. No host logic: storage bytes and keystrokes
// are the only things that cross the QwenOS syscall ABI.
#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "qos.h"
#include "qplat.h"
#include "platform.h"
#include "nor.h"
#include "pad.h"
#include "dmc_dji.h"
#include "dmc_fw.h"
#include "r_strip.h"

const qos_api *qapi;

// ---- console / exit -----------------------------------------------------------------
void q_putc(int c) { qapi->syscall(QOS_SYS_PUTC, (uint8_t)c, 0, 0); }
void q_puts(const char *s) { while (*s) q_putc(*s++); }
void q_putu(uint32_t v)
{
    char t[10]; int n = 0;
    do { t[n++] = (char)('0' + v % 10); v /= 10; } while (v);
    while (n) q_putc(t[--n]);
}
void q_puthex(uint32_t v)
{
    for (int i = 28; i >= 0; i -= 4) q_putc("0123456789abcdef"[(v >> i) & 15]);
}
// stops the reference executor (the kernel's own exit ecall), used for panics only
static void q_halt(uint32_t code)
{
    register uint32_t a0 __asm__("a0") = code, a7 __asm__("a7") = 93;
    __asm__ volatile("ecall" : "+r"(a0) : "r"(a7) : "memory");
    for (;;) {}
}

// ---- time: virtual 35 Hz clock ------------------------------------------------------
// QwenOS has no timer. Time advances 1 ms per plat_delay_ms/plat_idle step (waiting loops),
// so the engine runs exactly the tics its loop asks for.
static uint32_t vclock;
uint32_t plat_ms(void) { return vclock; }
void plat_delay_ms(uint32_t ms) { vclock += ms; }
void plat_idle(void) { vclock += 1; }
uint32_t plat_cycles(void) { return 0; }
void plat_init(void) {}

// ---- NOR over the block device -------------------------------------------------------
volatile struct nor_stats nor_stats;
static uint32_t nor_ticket;

// slow tail of a read the host has not completed within the kernel's wait: old poll protocol
__attribute__((noinline)) static void nor_wait_slow(uint32_t r, uint32_t c)
{
    if ((int32_t)r < 0) plat_panic("disk req");
    for (unsigned j = 0; j < 64 && !r; j++)
        r = qapi->syscall(QOS_SYS_DISK_POLL, 0, 0, 0);
    if (r != c) {
        qapi->syscall(QOS_SYS_DISK_CANCEL, 0, 0, 0);
        plat_panic("disk read");
    }
}
static inline __attribute__((always_inline)) void nor_chunk(uint32_t phys, void *out, uint32_t c)
{
    uint32_t r = qapi->syscall(QOS_SYS_DISK_READ, phys, (uintptr_t)out, c);
    if (r != c) nor_wait_slow(r, c);
}
static void nor_hw(uint32_t phys, void *dst, uint32_t n)
{
    uint8_t *out = dst;
    while (n) {
        uint32_t c = n > QOS_DISK_WINDOW ? QOS_DISK_WINDOW : n;
        nor_chunk(phys, out, c);
        phys += c; out += c; n -= c;
    }
}
int nor_init(void) { return 0; }
uint32_t nor_jedec(void) { return NOR_JEDEC_W25Q32; }
uint8_t nor_status(uint8_t cmd) { (void)cmd; return 0; }
void nor_read(uint32_t phys, void *dst, uint32_t n)
{
    if (n <= QOS_DISK_WINDOW) { nor_chunk(phys, dst, n); return; }
    nor_hw(phys, dst, n);
}
int nor_read_async(uint32_t phys, void *dst, uint32_t n, int prio)
{
    (void)prio;
    nor_hw(phys, dst, n);
    return (int)++nor_ticket;
}
bool nor_done(int t) { (void)t; return true; }
void nor_wait(int t) { (void)t; }
void nor_wait_all(void) {}
int nor_col_start(uint32_t phys, void *dst, uint32_t n)
{
    if (!n || n > 256) return -1;
    nor_chunk(phys, dst, n);
    return 0;
}
void nor_col_wait(void) {}
int nor_erase(uint32_t phys, unsigned cmd) { (void)phys; (void)cmd; return -1; }
int nor_program(uint32_t phys, const void *src, uint32_t n) { (void)phys; (void)src; (void)n; return -1; }
void nor_recover(void) {}
int nor_read16(uint32_t phys, void *dst, uint32_t n) { (void)phys; (void)dst; (void)n; return -1; }
int dmc_sector_write(uint32_t addr, const uint8_t *buf, uint32_t n) { (void)addr; (void)buf; (void)n; return -1; }

// ---- buttons, pad, sound, settings ------------------------------------------------------
static uint32_t btn_state;
static int ev_ring[8];
static unsigned ev_head, ev_n;
uint32_t plat_buttons(void) { return btn_state; }
int plat_event(void)
{
    if (!ev_n) return -1;
    int e = ev_ring[ev_head++ & 7];
    ev_n--;
    return e;
}
static void btn_set(int b, int down)
{
    uint32_t bit = BTN_BIT(b);
    if (!!(btn_state & bit) == !!down) return;
    btn_state ^= bit;
    if (ev_n < 8) ev_ring[(ev_head + ev_n++) & 7] = b | (down ? EV_PRESS : 0);
}

// Keys from the QwenOS key mailbox become presses held for a while (virtual ms). The
// meter's buttons are V-A fwd, HOLD back, MODE turn left, SAVE turn right, LIGHT fire (chord
// resolver, i_input.c); use/menu/enter go through the game pad state.
#define HOLD_MS 120
static uint32_t btn_until[BTN_COUNT];
static uint32_t pad_until;
static unsigned pad_bits;
uint32_t q_keys, q_dump_req;

void dji_start(void) {}
void dji_stop(void) {}
void dji_rx(const uint8_t *p, uint32_t n) { (void)p; (void)n; }
void dji_tic(void)
{
    uint32_t k = qapi->syscall(QOS_SYS_KEY_POLL, 0, 0, 0);
    if (k) {
        q_keys++;
        switch (k) {
        case 'w': btn_set(BTN_VA, 1);   btn_until[BTN_VA] = vclock + HOLD_MS; break;
        case 's': btn_set(BTN_HOLD, 1); btn_until[BTN_HOLD] = vclock + HOLD_MS; break;
        case 'a': btn_set(BTN_MODE, 1); btn_until[BTN_MODE] = vclock + HOLD_MS; break;
        case 'd': btn_set(BTN_SAVE, 1); btn_until[BTN_SAVE] = vclock + HOLD_MS; break;
        case ' ': case 'f': btn_set(BTN_LIGHT, 1); btn_until[BTN_LIGHT] = vclock + HOLD_MS; break;
        case 'e': pad_bits |= PAD_USE; pad_until = vclock + HOLD_MS; break;
        case 27: case 'm': pad_bits |= PAD_MENU; pad_until = vclock + HOLD_MS; break;
        case 13: case '\n': pad_bits |= PAD_ENTER; pad_until = vclock + HOLD_MS; break;
        case 'p': q_dump_req = 1; R_PaletteChanged(); break; /* arm a full serial dump: resend the whole status band too */
        }
    }
    for (int b = 0; b < BTN_COUNT; b++)
        if ((btn_state & BTN_BIT(b)) && (int32_t)(vclock - btn_until[b]) >= 0)
            btn_set(b, 0);
    if (pad_bits && (int32_t)(vclock - pad_until) >= 0) pad_bits = 0;
    if (pad_bits) {
        static const int16_t zero[PAD_NAXES];
        pad_set(zero, pad_bits);
    } else {
        pad_lost();
    }
}

void snd_volume(int vol) { (void)vol; }
void snd_play(const uint8_t *tones, uint32_t n) { (void)tones; (void)n; }
void snd_stop(void) {}
bool snd_busy(void) { return false; }
void snd_tone(uint32_t hz) { (void)hz; }
uint32_t snd_steps(void) { return 0; }
int settings_load(void *dst, uint32_t size, uint16_t version) { (void)dst; (void)size; (void)version; return -1; }
int settings_save(const void *src, uint32_t size, uint16_t version) { (void)src; (void)size; (void)version; return -1; }
dmc_set_t dmc_set;
int dmc_render = 1;
const volatile dmc_test_t dmc_test;

// ---- faults ----------------------------------------------------------------------------
void plat_panic(const char *msg)
{
    q_puts("\nDOOMD PANIC: ");
    q_puts(msg);
    q_putc('\n');
    q_halt(99);
}
void plat_power_off(void)
{
    q_puts("\nDOOMD: power off\n");
    q_halt(0);
}
void plat_fault_get(struct plat_fault *f) { memset(f, 0, sizeof(*f)); f->msg = ""; }
void plat_fault_hook(void (*fn)(void)) { (void)fn; }
void plat_fault_line(const char *label, uint32_t value) { (void)label; (void)value; }
extern uint8_t __stack_limit[];
uint32_t plat_stack_used(void)
{
    uint32_t *p = (uint32_t *)(void *)__stack_limit;
    while (*p == 0xA5A5A5A5u) p++;
    return QOS_RAM_END - (uint32_t)(uintptr_t)p;
}


// ---- verification-pass hooks of dmc_demo.c (not part of this port) -----------------------
void dmc_level_begin(void) {}
void dmc_level_end(void) {}
void dmc_demo_read(uint32_t off, void *dst, uint32_t n) { (void)off; (void)dst; (void)n; plat_panic("demo file"); }
int dmc_demo_open(const char *name, uint32_t *size) { (void)name; (void)size; return -1; }
