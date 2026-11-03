ENTRY(app_main)
MEMORY {
 ROM (rx): ORIGIN = 0x7c000, LENGTH = 0x4000
 RAM (rw): ORIGIN = 0x4000, LENGTH = 0x1000
 DROM (r): ORIGIN = 0x3e000, LENGTH = 0x2000
}
SECTIONS {
 .text : { *(.text*) } > ROM
 .data : { *(.data*) *(.sdata*) } > RAM
 .bss (NOLOAD) : { *(.bss*) *(.sbss*) *(COMMON) } > RAM
 .rodata : { *(.rodata*) *(.srodata*) } > DROM
 /DISCARD/ : { *(.comment*) *(.note*) *(.eh_frame*) }
}
