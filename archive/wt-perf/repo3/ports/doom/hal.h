#ifndef QWENOS_DOOM_HAL_H
#define QWENOS_DOOM_HAL_H
#include "qos.h"
/* Minimal portable guest-side device layer for a future genuine DOOM port.
 * The host may implement WAD block storage, but never executes guest logic.
 */
int qos_doom_wad_read(const qos_api *api,uint32_t offset,void *dst,unsigned count);
int qos_doom_present8(const qos_api *api,const uint8_t *pixels);
unsigned qos_doom_key(const qos_api *api);
#endif
