CC ?= clang
# GNU Make has built-in CC=cc; explicitly override for the cross compiler.
CC := clang
CFLAGS = --target=riscv32-unknown-elf -march=rv32im -mabi=ilp32 -Os -ffreestanding -fno-builtin -fno-stack-protector -fno-pic -msmall-data-limit=0 -Iinclude
LINK = -fuse-ld=lld -nostdlib -Wl,--no-relax -Wl,-z,max-page-size=4
OUT = build/qwenos.elf
all: $(OUT)
build/kernel.elf: kernel/start.S kernel/app_call.S kernel/main.c include/qos.h linker/kernel.ld
	mkdir -p build
	$(CC) $(CFLAGS) $(LINK) -Wl,-T,linker/kernel.ld kernel/start.S kernel/app_call.S kernel/main.c -o $@
build/%.elf: apps/%.c include/qos.h linker/%.ld
	mkdir -p build
	$(CC) $(CFLAGS) $(LINK) -Wl,-T,linker/$*.ld $< -o $@
build/doom.elf: apps/doom.c ports/doom/hal.c ports/doom/hal.h include/qos.h linker/doom.ld
	mkdir -p build
	$(CC) $(CFLAGS) -Iports/doom $(LINK) -Wl,-T,linker/doom.ld apps/doom.c ports/doom/hal.c -o $@
# /bin/doomd takeover app: crt0 + C entry doomd_main (stub; real engine plugs in here)
build/doomd.elf: apps/doomd.c apps/doomd_crt0.S include/qos.h linker/doomd.ld
	mkdir -p build
	$(CC) $(CFLAGS) $(LINK) -Wl,-T,linker/doomd.ld apps/doomd_crt0.S apps/doomd.c -o $@
APPS = build/shell.elf build/paint.elf build/raycast.elf build/asset.elf build/doom.elf build/doomd.elf
$(OUT): build/kernel.elf $(APPS) tools/merge_elf.py
	python3 tools/merge_elf.py $@ build/kernel.elf $(APPS)
# Boot variant: after the normal boot script, take over RAM with /bin/doomd.
build/kernel-doomd.elf: kernel/start.S kernel/app_call.S kernel/main.c include/qos.h linker/kernel.ld
	mkdir -p build
	$(CC) $(CFLAGS) -DQOS_BOOT_DOOMD $(LINK) -Wl,-T,linker/kernel.ld kernel/start.S kernel/app_call.S kernel/main.c -o $@
build/qwenos-doomd.elf: build/kernel-doomd.elf $(APPS) tools/merge_elf.py
	python3 tools/merge_elf.py $@ build/kernel-doomd.elf $(APPS)
# Live (interactive) OS: kernel without boot script/banner + typed-input shell. See README "Live shell".
build/kernel-live.elf: kernel/start.S kernel/app_call.S kernel/main.c include/qos.h linker/kernel.ld
	mkdir -p build
	$(CC) $(CFLAGS) -DQOS_LIVE $(LINK) -Wl,-T,linker/kernel.ld kernel/start.S kernel/app_call.S kernel/main.c -o $@
build/shell-live.elf: apps/shell.c include/qos.h linker/shell.ld
	mkdir -p build
	$(CC) $(CFLAGS) -DSHELL_LIVE $(LINK) -Wl,-T,linker/shell.ld apps/shell.c -o $@
LIVE_APPS = build/shell-live.elf build/paint.elf build/raycast.elf build/asset.elf build/doom.elf build/doomd.elf
build/qwenos-live.elf: build/kernel-live.elf $(LIVE_APPS) tools/merge_elf.py
	python3 tools/merge_elf.py $@ build/kernel-live.elf $(LIVE_APPS)
live: build/qwenos-live.elf
build/qwenos-model-probe.elf: kernel/start.S kernel/app_call.S kernel/main.c include/qos.h linker/kernel.ld
	mkdir -p build
	$(CC) $(CFLAGS) -DQOS_MODEL_BRIDGE $(LINK) -Wl,-T,linker/kernel.ld kernel/start.S kernel/app_call.S kernel/main.c -o $@
# Genuine DOOM engine (DMC100-Doom, GPL) built by ports/doomdmc/build.sh as the /bin/doomd image.
# Needs the DMC100-Doom checkout (DMC=...) with its generated gen/ dir and a NOR image of the pack.
DMC_SRCS = $(wildcard ports/doomdmc/*.c ports/doomdmc/*.ld ports/doomdmc/*.h ports/doomdmc/build.sh)
build/doomdmc.elf: $(DMC_SRCS) apps/doomd_crt0.S linker/doomd.ld include/qos.h ports/doom/hal.c
	mkdir -p build
	ports/doomdmc/build.sh build/doomdmc
	cp build/doomdmc/doomd.elf $@
DOOMDMC_APPS = build/shell.elf build/paint.elf build/raycast.elf build/asset.elf build/doom.elf build/doomdmc.elf
build/qwenos-doomdmc.elf: build/kernel-doomd.elf $(DOOMDMC_APPS) tools/merge_elf.py
	python3 tools/merge_elf.py $@ build/kernel-doomd.elf $(DOOMDMC_APPS)
doomdmc: build/qwenos-doomdmc.elf
model-probe: build/qwenos-model-probe.elf
	python3 tools/model_probe_ref.py build/qwenos-model-probe.elf
doom-frame: all
	python3 tools/export_doom_frame.py --elf $(OUT)
asset: all
	python3 tools/wad_device.py $(OUT)
frame: all
	python3 tools/render_frame.py $(OUT)
build/rv32_fast: tools/rv32_fast.c
	mkdir -p build
	cc -O2 -o $@ $<
check: all model-probe build/qwenos-doomd.elf build/qwenos-live.elf build/rv32_fast
	python3 tools/check_layout.py $(OUT)
	python3 tools/rv32_qwenputer.py $(OUT)
	python3 -m unittest discover -s tests -v
clean:
	rm -rf build
.PHONY: live doomdmc all check clean frame asset doom-frame model-probe

# ---- merged E1M1 build (see MERGE_NOTES.md) ----
# make demo-elf          -> build/demo/qwenos-e1m1.elf  (mode 2 scripted E1M1, skip 15/35, chunk ROM plan, zero in-doomd disk requests)
# make demo-live         -> build/demo/qwenos-live-e1m1.elf (typed flow: boot -> `run /bin/doomd` -> E1M1 driven by keys; CHUNKROM=1 for the model run)
demo-elf: build/rv32_fast
	tools/mkdemo.sh $(PRESET)
demo-live: build/rv32_fast
	tools/mkdemo.sh live $(PRESET)
.PHONY: demo-elf demo-live
