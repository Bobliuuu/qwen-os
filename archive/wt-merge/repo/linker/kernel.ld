ENTRY(_start)
/* RAM map (see ports/doomdmc/RAM_BUDGET.txt):
     0x0000-0x00ff   null guard: stays ZERO and untouched forever (the engine reads through NULL pointers at small
                     offsets; with live data there the DEMO1 game state diverged at tic 57, see MERGE_NOTES.md)
     0x0100-0x056f   core, RESIDENT FOREVER (also while /bin/doomd runs), fixed addresses (ASSERTs below):
        0x100  takeover stack (64 B; the normal kernel stack is qos_kstack in the overlay)
        0x140  kernel state (20 B; first word = key read count, QOS_KEY_RD)
        0x154  input mailbox   (8 B: u32 seq, u8 q[4] key ring)           QOS_IN_MB
        0x15c  disk mailbox    (20 B header + 256 B window)               QOS_DISK_MB
        0x270  32x24 framebuffer (768 B)                                  QOS_FB_ADDR
        0x570  end of core = QOS_DOOMD_RAM_BASE
     overlay         RAMFS, fds, procs, shell/app stacks and the normal kernel stack: kernel-only state that
                     /bin/doomd destroys (warm reboot on exit)
   Everything from __core_end up to 0x8000 is handed to doomd. */
MEMORY {
 RAM (rw) : ORIGIN = 0x0, LENGTH = 0x8000
 DROM (r) : ORIGIN = 0x20000, LENGTH = 0x1000
 ROM (rx) : ORIGIN = 0x40000, LENGTH = 0x1000
}
TSTACK = 64;
SECTIONS {
 .text : { KEEP(*(.text.start)) *(.text*) } > ROM
 .rodata : { *(.rodata*) *(.srodata*) } > DROM
 .data : { *(.data*) *(.sdata*) } > RAM
 __data_start = ADDR(.data); __data_end = ADDR(.data) + SIZEOF(.data);
 .core (NOLOAD) : ALIGN(16) {
  . = 0x100; __bss_start = .; __core_start = .;
  __tstack_limit = .; . += TSTACK; __tstack_top = .;
  *(.bss.core.a_vars) *(.bss.core.b_in) *(.bss.core.c_disk) *(.bss.core.d_fb)
  . = ALIGN(16);
  __core_end = .;
 } > RAM
 .bss (NOLOAD) : ALIGN(16) { __ov_start = .; *(.bss.kstack) *(.bss*) *(.sbss*) *(COMMON) . = ALIGN(4); __ov_end = .; __bss_end = .; } > RAM
 ASSERT(qos_kv == 0x140, "QOS_KEY_RD moved")
 ASSERT(qos_input_mailbox == 0x154, "QOS_IN_MB moved")
 ASSERT(qos_disk_mailbox == 0x15c, "QOS_DISK_MB moved")
 ASSERT(qos_framebuffer == 0x270, "QOS_FB_ADDR moved")
 ASSERT(__core_end <= 0x570, "kernel core exceeds doomd app RAM base 0x570 (QOS_DOOMD_RAM_BASE)")
 ASSERT(__bss_end <= 0x1800, "kernel encroaches on application RAM")
 ASSERT(SIZEOF(.data) == 0, "kernel .data not supported (warm reboot would not restore it)")
}
