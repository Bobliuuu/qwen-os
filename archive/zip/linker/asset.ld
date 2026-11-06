ENTRY(app_main)
MEMORY {
 ROM (rx): ORIGIN = 0x78000, LENGTH = 0x4000
 DROM (r): ORIGIN = 0x3c000, LENGTH = 0x2000
}
SECTIONS {
 .text : { *(.text*) } > ROM
 .rodata : { *(.rodata*) *(.srodata*) } > DROM
 /DISCARD/ : { *(.comment*) *(.note*) *(.eh_frame*) }
}
