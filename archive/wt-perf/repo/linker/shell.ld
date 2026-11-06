ENTRY(app_main)
MEMORY {
 ROM (rx): ORIGIN = 0x78000, LENGTH = 0x1000
 DROM (r): ORIGIN = 0x3f000, LENGTH = 0x400
}
SECTIONS {
 .text : { *(.text*) } > ROM
 .rodata : { *(.rodata*) *(.srodata*) } > DROM
 /DISCARD/ : { *(.comment*) *(.note*) *(.eh_frame*) }
}
