ENTRY(app_main)
MEMORY {
 ROM (rx): ORIGIN = 0x60000, LENGTH = 0x8000
 DROM (r): ORIGIN = 0x30000, LENGTH = 0x4000
}
SECTIONS {
 .text : { *(.text*) } > ROM
 .rodata : { *(.rodata*) *(.srodata*) } > DROM
 /DISCARD/ : { *(.comment*) *(.note*) *(.eh_frame*) }
}
