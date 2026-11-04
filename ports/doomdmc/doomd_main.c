// SPDX-License-Identifier: GPL-2.0-or-later
// /bin/doomd entry: boots DMC100-Doom (genuine DOOM engine, doomgeneric lineage) from the
// block-device NOR image. Replaces DMC100's dmc_main.c/dmc_boot.c/fe_play.c.
#include <stdint.h>
#include <string.h>

#include "doomdef.h"
#include "doomstat.h"
#include "d_loop.h"
#include "d_main.h"
#include "g_game.h"
#include "hu_stuff.h"
#include "i_video.h"
#include "m_menu.h"
#include "p_setup.h"
#include "r_main.h"
#include "s_sound.h"
#include "st_stuff.h"
#include "v_video.h"

#include "cache.h"
#include "dmc_fw.h"
#include "fe.h"
#include "fetch.h"
#include "i_input.h"
#include "img.h"
#include "ovl.h"
#include "r_strip.h"
#include "s_pcspk.h"
#include "platform.h"
#include "qplat.h"
#include "rec.h"

void D_Display(void);
void bake_init(void);
extern int demosequence;
extern boolean sendpause;
void q_frame_end(void);
extern uint8_t __bss_end[], __stack_limit[], __frame_start[], __ram_end[], __data_start[];

static void report_ram(void)
{
    q_puts("doomd: RAM data+bss end ");   q_puthex((uint32_t)(uintptr_t)__bss_end);
    q_puts(" frame ");                    q_puthex((uint32_t)(uintptr_t)__frame_start);
    q_puts(" ram_end ");                  q_puthex((uint32_t)(uintptr_t)__ram_end);
    q_puts(" stack used ");               q_putu(plat_stack_used());
    q_putc('\n');
}

/* Run modes (compile time, ports/doomdmc/mkmode.sh):
 *   0 attract loop from the title screen (default, what `make` builds)
 *   1 DEMO1 straight away: no title / credit pages, vanilla demo drives the player, exits at its end
 *   2 E1M1 player start, scripted input (q_script below) instead of a demo
 *   3 E1M1 player start, NO script: the player is driven only by keys from the QwenOS keyboard
 *     mailbox (what the live shell launches: `run /bin/doomd`; w/a/s/d move+turn, f/space fire, e use)
 * DOOMD_FRAMES=n  (compile time, default 0 = run forever): leave after n GAME frames, printing
 *   "DOOMD_FRAMES_DONE" (modes 1 and 2). DOOMD_DUMP=1 additionally dumps the last frame over PUTC.
 * Markers on the console: "DOOMD_LEVEL_START", "DOOMD_FRAME n", "DOOMD_FRAMES_DONE". */
#ifndef DOOMD_MODE
#define DOOMD_MODE 0
#endif
#ifndef DOOMD_FRAMES
#define DOOMD_FRAMES 0
#endif
#ifndef DOOMD_DUMP
#define DOOMD_DUMP 0
#endif
/* Lowres / frame-skip knobs (compile time, ports/doomdmc/lowres.sh):
 *   Q_RN / Q_RD   render a game tic t only when floor(t*RN/RD) != floor((t-1)*RN/RD): RN rendered frames
 *                 per RD game tics, evenly spread (15/35: gaps 2,2,3,2,2,3,...). Un-rendered tics run the
 *                 full game logic but skip D_Display (view, HUD, band, pump) and S_UpdateSounds.
 *   DOOMD_TICS=n  mode 2: leave after game tic n (marker DOOMD_TICS_DONE) with the long scripted run
 *   Q_STRIPW=w    strip width (columns per strip) instead of the map plan's   Q_SOLID=1 solid floors */
#ifndef Q_RN
#define Q_RN 1
#endif
#ifndef Q_RD
#define Q_RD 1
#endif
#ifndef DOOMD_TICS
#define DOOMD_TICS 0
#endif

/* mode 2 script: {first tic, last tic, buttons} hold the meter's buttons (V-A fwd, HOLD back,
 * MODE turn left, SAVE turn right, LIGHT fire) for those game tics */
void q_btn_hold(unsigned mask);
struct q_step { uint16_t t0, t1; uint8_t btn; };
static const struct q_step q_script[] = {
    {  4,  40, BTN_BIT(BTN_VA) },     /* forward */
    { 41,  50, BTN_BIT(BTN_SAVE) },   /* turn right */
    { 51,  70, BTN_BIT(BTN_VA) },     /* forward */
    { 71,  80, BTN_BIT(BTN_LIGHT) },  /* fire */
#if DOOMD_TICS
    { 81, 125, BTN_BIT(BTN_VA) },     /* long run (350 tics): on, turn, on, fire, turn, on */
    {126, 140, BTN_BIT(BTN_SAVE) },
    {141, 200, BTN_BIT(BTN_VA) },
    {201, 210, BTN_BIT(BTN_LIGHT) },
    {211, 225, BTN_BIT(BTN_MODE) },
    {226, 300, BTN_BIT(BTN_VA) },
    {301, 315, BTN_BIT(BTN_SAVE) },
    {316, 350, BTN_BIT(BTN_VA) },
#endif
};

int doomd_main(const qos_api *api)
{
    qapi = api;
    q_input_init();
    // RAM is already zero (kernel contract, qos_takeover_run); only paint the stack (diagnostics)
    {
        uint32_t *p = (uint32_t *)(void *)__stack_limit;
        uint32_t *e = (uint32_t *)(void *)((uintptr_t)__builtin_frame_address(0) - 96);
        for (; p < e; p++) *p = 0xA5A5A5A5u;
    }
    q_puts("doomd: DMC100-Doom on QwenOS\n");
    int e = img_init();
    q_puts("doomd: img_init -> "); q_putu((uint32_t)-e); q_putc('\n');
    if (e) plat_panic("DOOM.DAT not usable");
    q_puts("doomd: image bytes "); q_putu(img.size); q_putc('\n');

    bake_init();
    // start-up of the engine as BOOT_E_ENGINE does it (dmc_boot.c)
    rc_place(DMC_FRAME_BASE + PLAT_FRAME_MIN);
    flat_place(NULL);
    flat_set_slots(0);
    V_Init();
    S_PcsInit(img_read, img.sect[DMC_SECT_SOUNDS].off, img.sect[DMC_SECT_SOUNDS].size);
    S_Init(sfxVolume * 8);
    D_CheckNetGame();
    HU_Init();
    ST_Init();
    II_Configure(ii_presets[0], 0, 1);
    q_puts("doomd: engine init done\n");
    R_Init();
    P_Init();
    R_ExecuteSetViewSize();
#ifdef Q_STRIPW
    R_SetStripWidth(Q_STRIPW);
#endif
#ifdef Q_SOLID
    R_SetSolidFloors(1);
    R_SetFlatSlots(0);
#endif
    q_puts("doomd: R_Init/P_Init done\n");

    // play mode (fe_play.c)
    dmc_render = 1;
    singletics = false;
    fe.exit_k = 0;
    M_Init();
    showMessages = 1;
    D_ResetTics();
    R_PaletteChanged();
#if DOOMD_MODE == 0
    D_StartTitle();
    q_puts("doomd: title loop\n");
#elif DOOMD_MODE == 1
    // attract sequence without the pages: demosequence 0 -> DEMO1 on the first tic
    gameaction = ga_nothing;
    demosequence = 0;
    D_AdvanceDemo();
    q_puts("DOOMD_LEVEL_START demo1\n");
#else
    // E1M1 player start, skill 3 (hurt me plenty): the first tic loads the level
    G_DeferedInitNew(sk_medium, 1, 1);
    q_puts("DOOMD_LEVEL_START e1m1\n");
#endif
    int gframes = 0, was_menu = 0;
    for (;;) {
#if DOOMD_MODE == 2
        {
            uint8_t b = 0;
            for (unsigned i = 0; i < sizeof q_script / sizeof q_script[0]; i++)
                if (gametic >= q_script[i].t0 && gametic <= q_script[i].t1) b |= q_script[i].btn;
            q_btn_hold(b);
        }
#endif
        I_StartFrame();
        int t0 = gametic;
        TryRunTics();
        // Virtual time makes every other TryRunTics call return without a tic (it waits out the
        // tic's 28 ms in 1 ms sleeps). Redrawing the unchanged level costs ~4M instructions, so
        // only frames that follow a tic (or any menu / non-level screen) are drawn.
#ifndef Q_NOSKIP
        if (gamestate == GS_LEVEL && !menuactive && !was_menu &&
            (gametic == t0 || !players[consoleplayer].mo))
            continue;
#endif
#if Q_RN != Q_RD
        // frame skipping: the tic ran (game logic is untouched), the picture is not drawn
        if (gamestate == GS_LEVEL && !menuactive && !was_menu && players[consoleplayer].mo && gametic > 1 &&
            (gametic * Q_RN) / Q_RD == ((gametic - 1) * Q_RN) / Q_RD) {
#if DOOMD_TICS && DOOMD_MODE
            if (gametic >= DOOMD_TICS) { q_puts("DOOMD_TICS_DONE\n"); return 0; }
#endif
            continue;
        }
#endif
        was_menu = menuactive;
        S_UpdateSounds(players[consoleplayer].mo);
#if DOOMD_FRAMES && DOOMD_MODE
        if (gamestate == GS_LEVEL && DOOMD_DUMP && gframes == DOOMD_FRAMES - 1) { q_dump_req = 1; R_PaletteChanged(); }
#endif
        D_Display();
        q_frame_end();
#if DOOMD_MODE
        if (gamestate == GS_LEVEL && players[consoleplayer].mo && gametic > 0) {
            gframes++;
#ifdef DOOMD_PLAN_PRINT
            if (gframes == 1) {
                q_puts("plan "); q_putu(M.plan.plan); q_puts(" w "); q_putu(M.plan.w); q_puts(" k "); q_putu(M.plan.k);
                q_puts(" pages "); q_putu(M.plan.pages); q_puts(" need "); q_putu(M.plan.need_play);
                q_puts(" reserve "); q_putu(M.plan.reserve); q_puts(" arena "); q_putu(M.plan.arena_bytes);
                q_puts(" monsters "); q_putu(M.plan.monsters); q_putc('\n');
                report_ram();
            }
#endif
#if !DOOMD_TICS
            q_puts("DOOMD_FRAME "); q_putu((uint32_t)gframes); q_puts(" tic "); q_putu((uint32_t)gametic); q_putc('\n');
#else
            if (gametic >= DOOMD_TICS) { q_puts("DOOMD_TICS_DONE frames "); q_putu((uint32_t)gframes); q_putc('\n'); return 0; }
#endif
#if DOOMD_FRAMES
            if (gframes >= DOOMD_FRAMES) {
                q_puts("DOOMD_FRAMES_DONE\n");
                return 0;
            }
#endif
        } else if (DOOMD_MODE == 1 && gframes) {
            q_puts("DOOMD_DEMO_DONE\n");
            return 0;
        }
#endif
        if (fe.action) {
            fe.action = 0;
            paused = sendpause = false;
            fe.slot = 0;
            gameaction = ga_nothing;
        }
    }
    return 0;
}
