ENTRY(app_main)
MEMORY {
 ROM (rx): ORIGIN = 0x7a000, LENGTH = 0x1000
 DROM (r): ORIGIN = 0x3f500, LENGTH = 0x100
}
SECTIONS {
 .text : { *(.text*) } > ROM
 .rodata : { *(.rodata*) *(.srodata*) } > DROM
 /DISCARD/ : { *(.comment*) *(.note*) *(.eh_frame*) }
}
