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
#include "qplat.h"

void D_Display(void);
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

// Opens the NOR image of the episode in use and (re)builds the engine state that depends on it.
static void pack_init(int first)
{
    int e = img_init();
    q_puts("doomd: img_init -> "); q_putu((uint32_t)-e); q_putc('\n');
    if (e) plat_panic("DOOM.DAT not usable");
    q_puts("doomd: image bytes "); q_putu(img.size); q_putc('\n');
    dmc_mapent_t me;
    img_mapent(0, &me);
    q_ep_set(me.episode, q_ep_probe());
    q_puts("doomd: episode "); q_putu(me.episode); q_putc('\n');

    // start-up of the engine as BOOT_E_ENGINE does it (dmc_boot.c)
    rc_place(DMC_FRAME_BASE + PLAT_FRAME_MIN);
    flat_place(NULL);
    flat_set_slots(0);
    V_Init();
    S_PcsInit(img_read, img.sect[DMC_SECT_SOUNDS].off, img.sect[DMC_SECT_SOUNDS].size);
    if (first) {
        S_Init(sfxVolume * 8);
        D_CheckNetGame();
        HU_Init();
        ST_Init();
        II_Configure(ii_presets[0], 0, 1);
        q_puts("doomd: engine init done\n");
    }
    R_Init();
    P_Init();
    R_ExecuteSetViewSize();
}

int doomd_main(const qos_api *api)
{
    qapi = api;
    // dirty RAM: zero everything between .bss and the stack reserve, paint the stack
    memset(__bss_end, 0, (uint32_t)(uintptr_t)(__stack_limit - __bss_end));
    {
        uint32_t *p = (uint32_t *)(void *)__stack_limit;
        uint32_t *e = (uint32_t *)(void *)((uintptr_t)__builtin_frame_address(0) - 96);
        for (; p < e; p++) *p = 0xA5A5A5A5u;
    }
    q_puts("doomd: DMC100-Doom on QwenOS\n");
    int neps = q_ep_probe();
    q_puts("doomd: episodes on disk "); q_putu((uint32_t)neps); q_putc('\n');
    if (neps == 0) plat_panic("no episode image");
    q_ep_slot(1);
    pack_init(1);
    q_puts("doomd: R_Init/P_Init done\n");

    // play mode (fe_play.c)
    dmc_render = 1;
    singletics = false;
    fe.exit_k = 0;
    M_Init();
    showMessages = 1;
    D_ResetTics();
    R_PaletteChanged();
    D_StartTitle();
    q_puts("doomd: title loop\n");
    for (;;) {
        if (q_ep_pending) {
            // the menu chose another episode: switch to its image between tics, back to the title loop
            q_ep_slot(q_ep_pending);
            q_ep_pending = 0;
            pack_init(0);
            R_PaletteChanged();
            D_StartTitle();
        }
        I_StartFrame();
        TryRunTics();
        S_UpdateSounds(players[consoleplayer].mo);
        D_Display();
        q_frame_end();
        if (fe.action) {
            fe.action = 0;
            paused = sendpause = false;
            fe.slot = 0;
            gameaction = ga_nothing;
        }
    }
    return 0;
}
