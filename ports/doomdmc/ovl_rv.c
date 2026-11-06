// SPDX-License-Identifier: GPL-2.0-or-later
// QwenOS port of DMC100-Doom: overlay "loader" for a ROM-linked build. DMC100's overlays
// are plain functions here (their entry tables are the host-native ones, PLAT_HOST), so
// "loading" an overlay costs nothing and nothing is copied into RAM.
#include <stddef.h>
#include "ovl.h"
#include "platform.h"

const uint16_t ovl_win[OVL_IDS] = {
#define X(name, win) [OVL_##name] = win,
    OVL_LIST(X)
#undef X
};
uint16_t ovl_loads;
uint8_t dmc_build_id[20];

#define X(name, win)                                            \
    extern const ovl_fn ovl_tab_##name[] __attribute__((weak)); \
    extern const uint16_t ovl_cnt_##name __attribute__((weak));
OVL_LIST(X)
#undef X

static const ovl_fn *tab(int id)
{
    switch (id) {
#define X(name, win) case OVL_##name: return ovl_tab_##name;
        OVL_LIST(X)
#undef X
    }
    return 0;
}

int ovl_load(int id) { return tab(id) ? OVL_OK : OVL_ENOENT; }
ovl_fn ovl_entry(int id, int idx)
{
    const ovl_fn *t = tab(id);
    if (!t)
        plat_panic("overlay missing");
    return t[idx];
}
int ovl_resident(void) { return 0; }
void ovl_invalidate(void) {}
void ovl_set_fail_hook(ovl_fail_fn *fn) { (void)fn; }
