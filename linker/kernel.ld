ENTRY(_start)
MEMORY {
 RAM (rw) : ORIGIN = 0x100, LENGTH = 0x7f00
 DROM (r) : ORIGIN = 0x20000, LENGTH = 0x10000
 ROM (rx) : ORIGIN = 0x40000, LENGTH = 0x20000
}
SECTIONS {
 .text : { KEEP(*(.text.start)) *(.text*) } > ROM
 .rodata : { *(.rodata*) *(.srodata*) } > DROM
 .data : { *(.data*) *(.sdata*) } > RAM
 __data_start = ADDR(.data); __data_end = ADDR(.data) + SIZEOF(.data);
 .bss (NOLOAD) : { __bss_start = .; *(.bss*) *(.sbss*) *(COMMON) __bss_end = .; } > RAM
 __stack_top = 0x8000;
 ASSERT(__bss_end < 0x6000, "no room for kernel stack")
}
