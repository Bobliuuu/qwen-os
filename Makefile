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
build/qwenos-model-probe.elf: kernel/start.S kernel/app_call.S kernel/main.c include/qos.h linker/kernel.ld
	mkdir -p build
	$(CC) $(CFLAGS) -DQOS_MODEL_BRIDGE $(LINK) -Wl,-T,linker/kernel.ld kernel/start.S kernel/app_call.S kernel/main.c -o $@
# Genuine DOOM engine (DMC100-Doom, GPL) built by ports/doomdmc/build.sh as the /bin/doomd image.
# Needs the DMC100-Doom checkout (DMC=...) with its generated gen/ dir and a NOR image of the pack.
DMC_SRCS = $(wildcard ports/doomdmc/*.c ports/doomdmc/*.ld ports/doomdmc/*.h ports/doomdmc/build.sh ports/doomdmc/*.patch ports/doomdmc/mkflatrom.py)
build/doomdmc.elf: $(DMC_SRCS) apps/doomd_crt0.S linker/doomd.ld include/qos.h ports/doom/hal.c
	mkdir -p build
	ports/doomdmc/build.sh build/doomdmc
	cp build/doomdmc/doomd.elf $@
DOOMDMC_APPS = build/shell.elf build/paint.elf build/raycast.elf build/asset.elf build/doom.elf build/doomdmc.elf
build/qwenos-doomdmc.elf: build/kernel-doomd.elf $(DOOMDMC_APPS) tools/merge_elf.py
	python3 tools/merge_elf.py $@ build/kernel-doomd.elf $(DOOMDMC_APPS)
# NOR image whose map plans match this build's RAM layout (needs a WRITABLE DMC100-Doom work copy, DMCWORK=...)
build/doomdmc-layout.json: build/doomdmc.elf ports/doomdmc/mklayout.py
	python3 ports/doomdmc/mklayout.py build/doomdmc/doomd.elf $@
doomdmc-image: build/doomdmc-layout.json
	ports/doomdmc/mkimage.sh $(DMCWORK) $(abspath build/doomdmc-layout.json) $(abspath build/doomdmc-pack)
doomdmc: build/qwenos-doomdmc.elf
model-probe: build/qwenos-model-probe.elf
	python3 tools/model_probe_ref.py build/qwenos-model-probe.elf
doom-frame: all
	python3 tools/export_doom_frame.py --elf $(OUT)
asset: all
	python3 tools/wad_device.py $(OUT)
frame: all
	python3 tools/render_frame.py $(OUT)
check: all model-probe build/qwenos-doomd.elf
	python3 tools/check_layout.py $(OUT)
	python3 tools/rv32_qwenputer.py $(OUT)
	python3 -m unittest discover -s tests -v
clean:
	rm -rf build
.PHONY: doomdmc doomdmc-image all check clean frame asset doom-frame model-probe
