ENTRY(_start)
/* RAM map (see RAM_BUDGET.txt):
     0x0000-0x00ff  reserved (unused, null guard)
     core            mailboxes, framebuffer, small kernel state, kernel stack:
                     RESIDENT FOREVER, also while /bin/doomd runs
     overlay         RAMFS, fds, procs, shell/app stacks: kernel-only state that
                     /bin/doomd destroys (warm reboot on exit)
   Everything from __ov_start up to 0x8000 is handed to doomd. */
MEMORY {
 RAM (rw) : ORIGIN = 0x100, LENGTH = 0x7f00
 DROM (r) : ORIGIN = 0x20000, LENGTH = 0x1000
 ROM (rx) : ORIGIN = 0x40000, LENGTH = 0x1000
}
KSTACK = 128;
SECTIONS {
 .text : { KEEP(*(.text.start)) *(.text*) } > ROM
 .rodata : { *(.rodata*) *(.srodata*) } > DROM
 .data : { *(.data*) *(.sdata*) } > RAM
 __data_start = ADDR(.data); __data_end = ADDR(.data) + SIZEOF(.data);
 .core (NOLOAD) : ALIGN(16) {
  __bss_start = .; __core_start = .;
  *(.bss.core.a_in) *(.bss.core.b_disk) *(.bss.core.c_fb) *(.bss.core.d_vars)
  . = ALIGN(16); __kstack_limit = .; . += KSTACK; __kstack_top = .;
  __core_end = .;
 } > RAM
 .bss (NOLOAD) : ALIGN(16) { __ov_start = .; *(.bss*) *(.sbss*) *(COMMON) . = ALIGN(4); __ov_end = .; __bss_end = .; } > RAM
 ASSERT(__core_end <= 0x5c0, "kernel core exceeds doomd app RAM base 0x5c0")
 ASSERT(__bss_end <= 0x1800, "kernel encroaches on application RAM")
 ASSERT(SIZEOF(.data) == 0, "kernel .data not supported (warm reboot would not restore it)")
}
