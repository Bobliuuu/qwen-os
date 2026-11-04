// SPDX-License-Identifier: GPL-2.0-or-later
// QwenOS "LCD pump": DMC100 streams 8-bit palette-indexed columns of the 320x240 picture
// into pump_submit(). Here each pixel stream goes to (a) the 32x24 kernel framebuffer
// (nearest-sample of every 10x10 block, FB_SET syscalls) and (b) when armed with the 'p'
// key, a framed serial dump over PUTC so the full 320x240 frame can be reconstructed:
//   0x01 'P' palette-number        PLAYPAL palette index in use (host maps it to colours)
//   0x01 'W' x0 x1 y0 y1 flags (u16le each)   opens a window
//   0x01 'D' nbytes(u16le) then nbytes pixels, column-major (each column h bytes, doubled
//            columns repeated when flags&1)   one pump_submit
//   0x01 'E' frame(u16le)        end of frame
#include <stdint.h>
#include "lcd.h"
#include "platform.h"
#include "qos.h"
#include "qplat.h"

int q_pal; /* palette lives on the NOR; only its number is tracked */
__asm__(".globl pump_lut\n.set pump_lut, q_pal"); /* i_dmc.c passes it, q_pal_set ignores it */
void q_pal_set(int p, void *lut) { (void)lut; q_pal = p; }
volatile struct pump_stats pump_stats;

static int wx0, wx1, wy0, wy1, wflags, wcur;
static int wph, wcx;           /* wcur % 10, wcur / 10 (tracked incrementally) */
static int wph0, wcx0;         /* the same for wx0 */
static int fb_n, fb_s0;        /* FB sample rows in this window: count, offset of the first sample in a column */
static volatile uint8_t *fb_base; /* &framebuffer[first sample row][0] */
static int dumping;
static int pending;
uint32_t q_frames;

/* lowres builds: column stride of the strip buffer handed to pump_submit when it is not the window
 * height (letterbox view, r_frame.c), 0 = the window height */
int q_pump_stride;
#ifdef Q_DUMP_COMPACT
/* the serial dump sends every source column once; the window flags carry bit 8 and the host decoder
 * repeats each column 1, 2 (PUMP_DOUBLE) or 4 (PUMP_QUAD) times */
#define DUMP_FLAGS_X 0x100
#else
#define DUMP_FLAGS_X 0
#endif

static void put16(unsigned v) { q_putc(v & 255); q_putc((v >> 8) & 255); }

void pump_begin(int x0, int x1, int y0, int y1, int flags)
{
    wx0 = x0; wx1 = x1; wy0 = y0; wy1 = y1; wflags = flags; wcur = x0;
    wph0 = x0 % 10; wcx0 = x0 / 10; wph = wph0; wcx = wcx0;
    {   /* FB rows whose sample row (cy*10+5) lies in this window */
        int cy0 = (y0 + 4) / 10;
        int n = 0;
        if (y1 >= 5) { int cy1 = (y1 - 5) / 10; if (cy1 >= (int)QOS_FB_H) cy1 = (int)QOS_FB_H - 1; n = cy1 - cy0 + 1; }
        if (n < 0 || cy0 >= (int)QOS_FB_H) n = 0;
        fb_n = n; fb_s0 = cy0 * 10 + 5 - y0; fb_base = Q_FB + cy0 * QOS_FB_W;
    }
    if (q_dump_req) { dumping = 1; q_dump_req = 0; }
#ifdef Q_DUMP_ALL
    dumping = 1; /* verification build: stream every pump window (see tools/fh.py) */
#endif
    if (dumping) {
        q_putc(1); q_putc('P'); q_putc(q_pal);
        q_putc(1); q_putc('W');
        put16((unsigned)x0); put16((unsigned)x1); put16((unsigned)y0); put16((unsigned)y1);
        put16((unsigned)flags | DUMP_FLAGS_X);
    }
}

// Each pixel stream goes to the 32x24 framebuffer (nearest sample of every 10x10 block), stored
// straight into the resident framebuffer (takeover owns RAM; no FB_SET syscall).
static inline __attribute__((always_inline)) void fb_col(const uint8_t *col)
{
    volatile uint8_t *d = fb_base + wcx;
    const uint8_t *s = col + fb_s0;
    for (int i = fb_n; i; i--) { *d = *s; d += QOS_FB_W; s += 10; }
}
static inline __attribute__((always_inline)) void adv(void)
{
    if (++wcur > wx1) { wcur = wx0; wph = wph0; wcx = wcx0; }
    else if (++wph == 10) { wph = 0; wcx++; }
}

void pump_submit(const uint8_t *cols, int ncols)
{
    int h = wy1 - wy0 + 1;
    int rep = (wflags & PUMP_QUAD) ? 4 : (wflags & PUMP_DOUBLE) ? 2 : 1;
    int stride = q_pump_stride ? q_pump_stride : h;   /* lowres letterbox: strip column stride */
    if (dumping) {
#ifdef Q_DUMP_COMPACT
        int hs = (wflags & PUMP_ROW2) ? (h + 1) / 2 : h, ys = (wflags & PUMP_ROW2) ? 2 : 1;
        q_putc(1); q_putc('D'); put16((unsigned)(ncols * hs));
#else
        q_putc(1); q_putc('D'); put16((unsigned)(ncols * rep * h));
#endif
        for (int c = 0; c < ncols; c++) {
            const uint8_t *col = cols + c * stride;
            for (int r = 0; r < rep; r++) {
                if (wph == 5) fb_col(col);
                adv();
#ifndef Q_DUMP_COMPACT
                for (int y = 0; y < h; y++) q_putc(col[y]);
#endif
            }
#ifdef Q_DUMP_COMPACT
            for (int y = 0; y < h; y += ys) q_putc(col[y]);
#endif
        }
    } else if (rep == 1) {
        const uint8_t *col = cols;
        for (int c = ncols; c; c--, col += stride) {
            if (wph == 5) fb_col(col);
            adv();
        }
    } else if (rep == 2) {
        const uint8_t *col = cols;
        for (int c = ncols; c; c--, col += stride) {
            if (wph == 5) fb_col(col);
            adv();
            if (wph == 5) fb_col(col);
            adv();
        }
    } else {
        const uint8_t *col = cols;
        for (int c = ncols; c; c--, col += stride)
            for (int r = 0; r < rep; r++) {
                if (wph == 5) fb_col(col);
                adv();
            }
    }
    pump_stats.fills += (uint32_t)ncols;
}
void pump_sync(int max) { (void)max; }
int pump_pending(void) { return pending; }
void pump_end(void) {}

// the frame is done: called by the main loop. The framebuffer is the live display memory (the
// FB_PRESENT syscall only computed a checksum nobody reads while doomd owns the machine), so
// presenting is just the frame marker.
void q_frame_end(void)
{
    q_frames++;
    if (dumping) { q_putc(1); q_putc('E'); put16(q_frames); dumping = 0; }
    q_putc(2);  /* frame marker for the harness */
}

// ---- polled panel interface (menu/status text paths of the meter's UI): unused here ----
void lcd_init(int p) { (void)p; }
int lcd_profile(void) { return 0; }
void lcd_flip(int f) { (void)f; }
int lcd_flipped(void) { return 0; }
void lcd_backlight(int on) { (void)on; }
void lcd_begin(int x0, int y0, int x1, int y1) { (void)x0; (void)y0; (void)x1; (void)y1; }
void lcd_push(uint16_t c) { (void)c; }
void lcd_push_n(const uint16_t *px, uint32_t n) { (void)px; (void)n; }
void lcd_end(void) {}
void lcd_fill(int x0, int y0, int x1, int y1, uint16_t c) { (void)x0; (void)y0; (void)x1; (void)y1; (void)c; }
void lcd_recover(void) {}
