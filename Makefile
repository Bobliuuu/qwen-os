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
$(OUT): build/kernel.elf build/shell.elf build/paint.elf build/raycast.elf build/asset.elf build/doom.elf tools/merge_elf.py
	python3 tools/merge_elf.py $@ build/kernel.elf build/shell.elf build/paint.elf build/raycast.elf build/asset.elf build/doom.elf
build/qwenos-model-probe.elf: kernel/start.S kernel/app_call.S kernel/main.c include/qos.h linker/kernel.ld
	mkdir -p build
	$(CC) $(CFLAGS) -DQOS_MODEL_BRIDGE $(LINK) -Wl,-T,linker/kernel.ld kernel/start.S kernel/app_call.S kernel/main.c -o $@
model-probe: build/qwenos-model-probe.elf
	python3 tools/model_probe_ref.py build/qwenos-model-probe.elf
doom-frame: all
	python3 tools/export_doom_frame.py --elf $(OUT)
asset: all
	python3 tools/wad_device.py $(OUT)
frame: all
	python3 tools/render_frame.py $(OUT)
check: all model-probe
	python3 tools/check_layout.py $(OUT)
	python3 tools/rv32_qwenputer.py $(OUT)
	python3 -m unittest discover -s tests -v
clean:
	rm -rf build
.PHONY: all check clean frame asset doom-frame model-probe
