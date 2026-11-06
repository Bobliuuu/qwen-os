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
#define QOS_DOOMD_RAM_BASE 0x570u
/* Resident core addresses (kernel.ld ASSERTs them): trusted takeover code (/bin/doomd) may access the
   mailboxes and framebuffer directly instead of through syscalls. Disk mailbox layout:
   request_seq,offset,length,ready_seq,status (u32 each), bytes[QOS_DISK_WINDOW]. */
#define QOS_KEY_RD 0x140u /* u32: kernel key read count (qos_kv.key_seq_seen); doomd resumes its own ring reader from it */
#define QOS_IN_MB 0x154u
#define QOS_DISK_MB 0x15cu
#define QOS_FB_ADDR 0x270u
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
#define QOS_SYS_KEY_POLL 17u /* consumes the OLDEST queued key (4-deep ring, see qos_input_mailbox), or 0 */
#define QOS_SYS_FB_PTR 23u /* returns the address of the 32x24 byte framebuffer (row-major) for direct pixel writes */
#define QOS_SYS_KEY_WAIT 22u /* like KEY_POLL but parks at qos_key_park until a key is injected: never returns 0 */
#define QOS_SYS_DISK_REQUEST 18u /* byte offset, destination RAM pointer, length<=256; 0 accepted */
#define QOS_SYS_DISK_POLL 19u /* 0=pending, len=completed, negative=failure */
#define QOS_SYS_DISK_CANCEL 20u /* abort pending request */
#define QOS_SYS_DISK_READ 21u /* offset, dest RAM ptr, len<=256: request+wait+copy in one call; returns len, 0 = still pending (continue with DISK_POLL), <0 error */
#define QOS_DISK_WINDOW 256u
/* Input mailbox (8 bytes at QOS_IN_MB = 0x154, symbol qos_input_mailbox):
     +0 u32 seq   number of keys the device has pushed so far (starts at 0, host writes it LAST)
     +4 u8 q[4]   ring: key number n (0-based) lives in q[n&3]
   Push protocol: q[seq&3]=key; seq=seq+1.  The kernel keeps its own read count (core RAM,
   survives /bin/doomd takeover), so keys pushed while no program polls are queued (up to 4);
   if more arrive the oldest are dropped.  Key code 0 is not a key.
   Park protocol (KEY_WAIT): when the guest has nothing to read it calls qos_key_park (a single
   `ret` in kernel ROM) in a loop.  A host/driver that wants to type stops when pc==&qos_key_park,
   pushes a key as above, and resumes at that same pc. */
#define QOS_O_READ 0u
#define QOS_O_WRITE 1u
typedef uint32_t (*qos_syscall_t)(uint32_t n,uintptr_t a,uintptr_t b,uintptr_t c);
typedef struct {uint32_t abi_version; qos_syscall_t syscall;} qos_api;
static inline uint32_t qcall(const qos_api *api,uint32_t n,uintptr_t a,uintptr_t b,uintptr_t c){return api->syscall(n,a,b,c);}
static inline void qputs(const qos_api *api,const char *s){while(*s)qcall(api,QOS_SYS_PUTC,(uint8_t)*s++,0,0);}
#endif
