/* Extra symbols for DMC100's RAM regions on QwenOS (second linker script, after doomd.ld) */
__frame_start = (__bss_end + 15) & ~15;
__ram_end = __stack_limit;
__frame_min = 8368;
__frame_max = 15208;
__core_size = 0;
__dmc_variant = 0;
dmc_tic = __frame_start + 6912;
/* gp window = RAM 0x570..0x156f (hot engine .data/.bss from the doomd RAM base 0x470); render.patch used 0xec0 for base 0x5c0 */
__global_pointer$ = 0xe70;
