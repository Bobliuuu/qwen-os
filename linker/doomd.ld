ENTRY(app_main)
/* /bin/doomd: full-RAM takeover application (see RAM_BUDGET.txt, README).
 *
 * RAM  0x0098..0x8000 is yours (32616 B). Kernel core (vars, mailboxes, 48 B takeover
 *      stack; the 32x24 fb is NOT resident, it streams to the console) lives below 0x98.
 *      Stack: kernel enters with sp = 0x8000, growing down; DOOMD_STACK bytes
 *      at the top are reserved for it (incl. room for kernel syscall frames).
 * ROM  0x41000..0x77fff (220 KiB) code only; instruction fetch only, cannot be
 *      read as data.
 * DROM 0x21000..0x3efff (120 KiB) rodata + the initial image of .data.
 * .data is NOT preloaded at runtime (the shell clobbered RAM before takeover):
 * apps/doomd_crt0.S copies __data_load..+size to __data_start and zeroes bss.
 */
DOOMD_STACK = DEFINED(DOOMD_STACK_OVERRIDE) ? DOOMD_STACK_OVERRIDE : 0x600;
RAM_BASE = 0x98;
RAM_END  = 0x8000;
MEMORY {
 ROM  (rx) : ORIGIN = 0x41000, LENGTH = 0x37000
 DROM (r)  : ORIGIN = 0x21000, LENGTH = 0x1e000
 RAM  (rw) : ORIGIN = 0x98,   LENGTH = 0x8000 - 0x98
}
SECTIONS {
 .text : { KEEP(*(.text.start)) *(.text*) } > ROM
 .rodata : { *(.rodata*) *(.srodata*) } > DROM
 .data : ALIGN(4) { __data_start = .; *(.data*) *(.sdata*) . = ALIGN(4); __data_end = .; } > RAM AT> DROM
 __data_load = LOADADDR(.data);
 .bss (NOLOAD) : ALIGN(4) { __bss_start = .; *(.bss*) *(.sbss*) *(COMMON) . = ALIGN(4); __bss_end = .; } > RAM
 __app_ram_start = ORIGIN(RAM);
 __stack_limit = RAM_END - DOOMD_STACK;
 __stack_top = RAM_END;
 ASSERT(__bss_end <= __stack_limit, "doomd data+bss overlaps stack reserve (raise RAM or lower DOOMD_STACK)")
 /DISCARD/ : { *(.comment*) *(.note*) *(.eh_frame*) }
}
