ENTRY(_start)
/* RAM map (see RAM_BUDGET.txt):
     0x0000-0x0097   core, RESIDENT FOREVER (also while /bin/doomd runs): kernel vars,
                     input mailbox, 48 B takeover stack, disk mailbox header + the first
                     QOS_DISK_TAKEOVER_WINDOW bytes of its window
     overlay         everything else the kernel owns in normal operation: the rest of the
                     disk window, framebuffer, RAMFS, fds, procs, kernel/app stacks.
                     /bin/doomd destroys it (warm reboot on exit)
   Everything from __core_end up to 0x8000 is handed to doomd. */
MEMORY {
 RAM (rw) : ORIGIN = 0x0, LENGTH = 0x8000
 DROM (r) : ORIGIN = 0x20000, LENGTH = 0x1000
 ROM (rx) : ORIGIN = 0x40000, LENGTH = 0x1000
}
TSTACK = 48;
DISK_HDR = 20;
DISK_TAKEOVER_WINDOW = 64;
SECTIONS {
 .text : { KEEP(*(.text.start)) *(.text*) } > ROM
 .rodata : { *(.rodata*) *(.srodata*) } > DROM
 .data : { *(.data*) *(.sdata*) } > RAM
 __data_start = ADDR(.data); __data_end = ADDR(.data) + SIZEOF(.data);
 .core (NOLOAD) : ALIGN(16) {
  __bss_start = .; __core_start = .;
  __tstack_limit = .; . += TSTACK; __tstack_top = .;
  *(.bss.core.a_vars) *(.bss.core.b_in)
  . = ALIGN(4); __disk_start = .;
  *(.bss.core.e_disk)
 } > RAM
 __core_end = (__disk_start + DISK_HDR + DISK_TAKEOVER_WINDOW + 3) & ~3;
 .bss (NOLOAD) : ALIGN(16) { __ov_start = .; *(.bss*) *(.sbss*) *(COMMON) . = ALIGN(4); __ov_end = .; __bss_end = .; } > RAM
 ASSERT(__core_end <= 0x98, "kernel core exceeds doomd app RAM base 0x98 (QOS_DOOMD_RAM_BASE)")
 ASSERT(__ov_start >= __disk_start + 20 + 256, "overlay overlaps the full disk window")
 ASSERT(__bss_end <= 0x1800, "kernel encroaches on application RAM")
 ASSERT(SIZEOF(.data) == 0, "kernel .data not supported (warm reboot would not restore it)")
}
