/* Extra symbols for DMC100's RAM regions on QwenOS (second linker script, after doomd.ld) */
__frame_start = (__bss_end + 15) & ~15;
__ram_end = __stack_limit;
__frame_min = 8368;
__frame_max = 15208;
__core_size = 0;
__dmc_variant = 0;
dmc_tic = __frame_start + 6912;
