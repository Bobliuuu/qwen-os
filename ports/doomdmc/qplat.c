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
#include "sounds.h"
#include "doomstat.h"
#include "g_game.h"
#include "d_player.h"
#include "p_local.h"

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

void nor_hw(uint32_t phys, void *dst, uint32_t n)
{
    uint8_t *out = dst;
    while (n) {
        uint32_t c = n > QOS_DISK_WINDOW ? QOS_DISK_WINDOW : n;
        if (qapi->syscall(QOS_SYS_DISK_REQUEST, phys, (uintptr_t)out, c))
            plat_panic("disk req");
        uint32_t r = 0;
        for (unsigned j = 0; j < 64; j++) {
            r = qapi->syscall(QOS_SYS_DISK_POLL, 0, 0, 0);
            if (r) break;
        }
        if (r != c) {
            qapi->syscall(QOS_SYS_DISK_CANCEL, 0, 0, 0);
            plat_panic("disk read");
        }
        phys += c; out += c; n -= c;
    }
}
int nor_init(void) { return 0; }
uint32_t nor_jedec(void) { return NOR_JEDEC_W25Q32; }
uint8_t nor_status(uint8_t cmd) { (void)cmd; return 0; }
void nor_read(uint32_t phys, void *dst, uint32_t n)
{
    nor_stats.sync++; nor_stats.bytes += n;
    nor_hw(phys, dst, n);
}
int nor_read_async(uint32_t phys, void *dst, uint32_t n, int prio)
{
    (void)prio;
    nor_stats.async++; nor_stats.bytes += n;
    nor_hw(phys, dst, n);
    return (int)++nor_ticket;
}
bool nor_done(int t) { (void)t; return true; }
void nor_wait(int t) { (void)t; }
void nor_wait_all(void) {}
int nor_col_start(uint32_t phys, void *dst, uint32_t n)
{
    if (!n || n > 256) return -1;
    nor_stats.async++; nor_stats.bytes += n;
    nor_hw(phys, dst, n);
    return 0;
}
void nor_col_wait(void) {}
// Writes: the block device takes plain stores (QOS_SYS_DISK_WRITE, 256 B per request); NOR semantics
// live here: an erase stores 0xFF, a program ANDs into the old bytes (read back first).
static void nor_store(uint32_t phys, const uint8_t *src, uint32_t n)
{
    while (n) {
        uint32_t c = n > QOS_DISK_WINDOW ? QOS_DISK_WINDOW : n;
        if (qapi->syscall(QOS_SYS_DISK_WRITE, phys, (uintptr_t)src, c))
            plat_panic("disk wreq");
        uint32_t r = 0;
        for (unsigned j = 0; j < 64 && !r; j++) r = qapi->syscall(QOS_SYS_DISK_POLL, 0, 0, 0);
        if (r != c) { qapi->syscall(QOS_SYS_DISK_CANCEL, 0, 0, 0); plat_panic("disk write"); }
        phys += c; src += c; n -= c;
    }
}
int nor_erase(uint32_t phys, unsigned cmd)
{
    uint32_t n = cmd == NOR_ERASE_4K ? 4096 : cmd == NOR_ERASE_64K ? 65536 : 0;
    static const uint8_t ff[256] = {[0 ... 255] = 0xFF};
    if (!n) return -1;
    phys &= ~(n - 1);
    for (uint32_t o = 0; o < n; o += 256) nor_store(phys + o, ff, 256);
    return 0;
}
int nor_program(uint32_t phys, const void *src, uint32_t n)
{
    const uint8_t *s = src;
    uint8_t old[256], buf[256];
    while (n) {
        uint32_t c = n > 256 ? 256 : n;
        nor_hw(phys, old, c);
        for (uint32_t i = 0; i < c; i++) buf[i] = old[i] & s[i];
        nor_store(phys, buf, c);
        phys += c; s += c; n -= c;
    }
    return 0;
}
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
static uint32_t pad_until[PAD_NAXES + 16];
static unsigned pad_bits;
static int16_t pad_ax[PAD_NAXES];
static void pad_hold(unsigned bit) { pad_bits |= bit; for (int i = 0; i < 16; i++) if (bit >> i & 1) pad_until[i] = vclock + HOLD_MS; }
uint32_t q_keys, q_dump_req;
static uint32_t q_hold; /* scripted buttons (mode 2): held every tic until changed */
void q_btn_hold(unsigned mask) { q_hold = mask; }

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
        case 'e': pad_hold(PAD_USE); break;
        case 'z': pad_hold(PAD_RUN); break;
        case 'q': pad_ax[PAD_LX] = -600; pad_until[16] = vclock + HOLD_MS; break;
        case 'r': pad_ax[PAD_LX] = 600;  pad_until[17] = vclock + HOLD_MS; break;
        case 27: case 'm': pad_hold(PAD_MENU); break;
        case 13: case '\n': pad_hold(PAD_ENTER); break;
        case 'y': pad_hold(PAD_ENTER); break;
        case 'n': pad_hold(PAD_MENU); break;
        case '.': pad_hold(PAD_NEXTW); break;
        case ',': pad_hold(PAD_PREVW); break;
        case 9: pad_hold(PAD_MAP); break;
#ifndef Q_NODEBUGKEYS
        // test-only keys (the cheat sequences are stripped from this engine build)
        case 'x': if (gamestate == GS_LEVEL) G_ExitLevel(); break;
        case 'X': if (gamestate == GS_LEVEL) G_SecretExitLevel(); break;
        case 'g': players[consoleplayer].cheats ^= CF_GODMODE; break;
        case 'i': {
            player_t *pl = &players[consoleplayer];
            for (int i = 0; i < NUMWEAPONS; i++) pl->weaponowned[i] = true;
            for (int i = 0; i < NUMAMMO; i++) pl->ammo[i] = pl->maxammo[i];
            for (int i = 0; i < NUMCARDS; i++) pl->cards[i] = true;
            pl->armorpoints = 200; pl->armortype = 2; pl->health = pl->mo ? (pl->mo->health = 100) : 100;
            break; }
        case 't': case 'T': if (gamestate == GS_LEVEL && gameepisode == 1 && gamemap == 1) {  // E1M1 corridor east of the green armor door
            mobj_t *mo = players[consoleplayer].mo;
            if (k == 't') { P_TeleportMove(mo, 608 << 16, 730 << 16); mo->angle = 0xC0000000u; }   // facing a health bonus
            else { P_TeleportMove(mo, 596 << 16, 712 << 16); mo->angle = 0x80000000u; }            // facing the door
            mo->momx = mo->momy = 0; }
            break;
        case '`': {
            player_t *pl = &players[consoleplayer];
            q_puts("\nSTATE gs="); q_putu(gamestate); q_puts(" e="); q_putu(gameepisode); q_puts(" m="); q_putu(gamemap);
            q_puts(" hp="); q_putu(pl->health > 0 ? pl->health : 0); q_puts(" ar="); q_putu(pl->armorpoints);
            q_puts(" bul="); q_putu(pl->ammo[0]); q_puts(" kills="); q_putu(pl->killcount);
            q_puts(" items="); q_putu(pl->itemcount); q_puts(" wpn="); q_putu(pl->readyweapon);
            if (pl->mo) { q_puts(" x="); q_puthex(pl->mo->x); q_puts(" y="); q_puthex(pl->mo->y); q_puts(" ang="); q_puthex(pl->mo->angle); }
            q_putc('\n');
            break; }
#endif
        case 'p': q_dump_req = 1; R_PaletteChanged(); break; /* arm a full serial dump: resend the whole status band too */
        }
    }
    for (int b = 0; b < BTN_COUNT; b++)
        if (q_hold & BTN_BIT(b)) btn_set(b, 1);
        else if ((btn_state & BTN_BIT(b)) && (int32_t)(vclock - btn_until[b]) >= 0)
            btn_set(b, 0);
    for (int i = 0; i < 16; i++)
        if ((pad_bits >> i & 1) && (int32_t)(vclock - pad_until[i]) >= 0) pad_bits &= ~(1u << i);
    if (pad_ax[PAD_LX] < 0 && (int32_t)(vclock - pad_until[16]) >= 0) pad_ax[PAD_LX] = 0;
    if (pad_ax[PAD_LX] > 0 && (int32_t)(vclock - pad_until[17]) >= 0) pad_ax[PAD_LX] = 0;
    pad_set(pad_ax, pad_bits);
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
