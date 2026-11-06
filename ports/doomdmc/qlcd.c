// SPDX-License-Identifier: GPL-2.0-or-later
// QwenOS "LCD pump": DMC100 streams 8-bit palette-indexed columns of the 320x240 picture
// into pump_submit(). Here each pixel stream goes to (a) the 32x24 kernel framebuffer
// (nearest-sample of every 10x10 block, FB_COL syscalls = console packets, no resident fb) and (b) when armed with the 'p'
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
static int dumping;
static int pending;
uint32_t q_frames;

static void put16(unsigned v) { q_putc(v & 255); q_putc((v >> 8) & 255); }

void pump_begin(int x0, int x1, int y0, int y1, int flags)
{
    wx0 = x0; wx1 = x1; wy0 = y0; wy1 = y1; wflags = flags; wcur = x0;
    if (q_dump_req) { dumping = 1; q_dump_req = 0; }
    if (dumping) {
        q_putc(1); q_putc('P'); q_putc(q_pal);
        q_putc(1); q_putc('W');
        put16((unsigned)x0); put16((unsigned)x1); put16((unsigned)y0); put16((unsigned)y1);
        put16((unsigned)flags);
    }
}

void pump_submit(const uint8_t *cols, int ncols)
{
    int h = wy1 - wy0 + 1;
    int rep = (wflags & PUMP_DOUBLE) ? 2 : 1;
    int wc0 = wcur;
    if (dumping) {
        q_putc(1); q_putc('D'); put16((unsigned)(ncols * rep * h));
        for (int c = 0; c < ncols; c++)
            for (int r = 0; r < rep; r++)
                for (int y = 0; y < h; y++) q_putc(cols[c * h + y]);
    }
    // FB samples go out after the D payload (their console packets must not interleave with it)
    for (int c = 0; c < ncols; c++) {
        const uint8_t *col = cols + c * h;
        for (int r = 0; r < rep; r++) {
            int x = wcur;
            if (++wcur > wx1) wcur = wx0;
            if (x % 10 == 5) {
                // FB column samples whose row (cy*10+5) lies in this window, one FB_COL call
                // (the kernel streams them out as a console packet; no resident fb)
                uint8_t fbc[QOS_FB_H];
                int cy0 = (wy0 + 4) / 10, n = 0;
                for (int cy = cy0; cy < (int)QOS_FB_H && cy * 10 + 5 <= wy1; cy++)
                    if (cy * 10 + 5 >= wy0)
                        fbc[n++] = col[cy * 10 + 5 - wy0];
                if (n)
                    qapi->syscall(QOS_SYS_FB_COL, (unsigned)(x / 10) | ((unsigned)cy0 << 8), (uintptr_t)fbc, (unsigned)n);
            }
        }
    }
    (void)wc0;
    pump_stats.fills += (uint32_t)ncols;
}
void pump_sync(int max) { (void)max; }
int pump_pending(void) { return pending; }
void pump_end(void) {}

// the frame is done: called by the main loop
void q_frame_end(void)
{
    q_frames++;
    if (dumping) { q_putc(1); q_putc('E'); put16(q_frames); dumping = 0; }
    qapi->syscall(QOS_SYS_FB_PRESENT, 0, 0, 0);
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
