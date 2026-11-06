#ifndef QWENOS_QOS_H
#define QWENOS_QOS_H
#include <stdint.h>
#include <stddef.h>
#define QOS_RAM_BEGIN   0x100u
#define QOS_RAM_END     0x8000u
#define QOS_DROM_BEGIN  0x20000u
#define QOS_DROM_END    0x40000u
#define QOS_ROM_BEGIN   0x40000u
#define QOS_ROM_END     0x80000u
/* Executable ROM map (repacked: small apps at the top, engine gets the middle).
   0x40000-0x40fff kernel (4 KiB)        0x41000-0x77fff /bin/doomd (220 KiB)
   0x78000 shell, 0x79000 paint, 0x7a000 raycast, 0x7b000 asset (4 KiB each),
   0x7c000-0x7ffff WAD viewer (16 KiB). */
#define QOS_DOOMD_ENTRY 0x41000u
#define QOS_SHELL_ENTRY 0x78000u
#define QOS_PAINT_ENTRY 0x79000u
#define QOS_RAY_ENTRY   0x7a000u
#define QOS_ASSET_ENTRY 0x7b000u
#define QOS_DOOM_ENTRY  0x7c000u
/* /bin/doomd takeover: kernel core ends below QOS_DOOMD_RAM_BASE; doomd owns
   QOS_DOOMD_RAM_BASE..QOS_RAM_END (stack top = QOS_RAM_END). */
#define QOS_DOOMD_RAM_BASE 0x5c0u
#define QOS_FB_W 32u
#define QOS_FB_H 24u
#define QOS_MAX_FD 12u
#define QOS_MAX_PROC 2u /* one shell plus one guest; bounded for 32 KiB RAM */
#define QOS_SYS_PUTC 1u
#define QOS_SYS_OPEN 2u
#define QOS_SYS_READ 3u
#define QOS_SYS_CLOSE 4u
#define QOS_SYS_CREATE 5u
#define QOS_SYS_WRITE 6u
#define QOS_SYS_EXEC 7u
#define QOS_SYS_FB_SET 8u
#define QOS_SYS_FB_CLEAR 9u
#define QOS_SYS_STAT 10u
#define QOS_SYS_GETPID 11u
#define QOS_SYS_YIELD 12u
#define QOS_SYS_FB_GET 13u
#define QOS_SYS_PS 14u
#define QOS_SYS_FB_ROW 15u /* y, src pointer, width */
#define QOS_SYS_FB_PRESENT 16u /* returns FNV-1a checksum of frame */
#define QOS_SYS_KEY_POLL 17u /* consumes newest injected key, or 0 */
#define QOS_SYS_DISK_REQUEST 18u /* byte offset, destination RAM pointer, length<=256; 0 accepted */
#define QOS_SYS_DISK_POLL 19u /* 0=pending, len=completed, negative=failure */
#define QOS_SYS_DISK_CANCEL 20u /* abort pending request */
#define QOS_DISK_WINDOW 256u
#define QOS_O_READ 0u
#define QOS_O_WRITE 1u
typedef uint32_t (*qos_syscall_t)(uint32_t n,uintptr_t a,uintptr_t b,uintptr_t c);
typedef struct {uint32_t abi_version; qos_syscall_t syscall;} qos_api;
static inline uint32_t qcall(const qos_api *api,uint32_t n,uintptr_t a,uintptr_t b,uintptr_t c){return api->syscall(n,a,b,c);}
static inline void qputs(const qos_api *api,const char *s){while(*s)qcall(api,QOS_SYS_PUTC,(uint8_t)*s++,0,0);}
#endif
