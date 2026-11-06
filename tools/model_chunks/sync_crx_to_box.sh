#!/bin/bash
# Mac -> GPU box (p4d at launch time or the Lambda A100): ./sync_crx_to_box.sh <ip> [user=ubuntu] [key=~/.ssh/swarm-gpu]
# Copies the merged ELF, symbol ELF, kernel ELF, chunk plan, E1 image, driver tools and the fleet chunk plan to ~/crx/ and verifies md5s.
IP=${1:?ip}; U=${2:-ubuntu}; K=${3:-$HOME/.ssh/swarm-gpu}
M=/Users/jhome/qwenos-work/wt-merge/repo; T=/Users/jhome/qwenos-work/bundle/repo/tools; O=/Users/jhome/qwenos-work/out/model
S="ssh -i $K -o StrictHostKeyChecking=no"
ssh_() { $S $U@$IP "$@"; }
ssh_ 'mkdir -p ~/crx/build ~/crx/tools ~/out'
rsync -a -e "$S" $M/build/demo/qwenos-e1m1.elf $M/build/demo/crx-plan.json $M/build/demo/crx-plan.bin $M/build/kernel-doomd.elf $U@$IP:crx/build/
rsync -a -e "$S" $M/build/lr-demo/doomd.elf $U@$IP:crx/build/doomd-sym.elf
rsync -a -e "$S" $M/engine/../../engine/DMC100-Doom/build/sw/nor/E1.img $U@$IP:crx/E1.img 2>/dev/null || rsync -a -e "$S" $M/../engine/DMC100-Doom/build/sw/nor/E1.img $U@$IP:crx/E1.img
rsync -a -e "$S" $T/model_doom_qwen.py $T/chunkrom.py $T/upstream_ref.py $T/upstream_doomd.py $T/wad_device.py $T/rv32_qwenputer.py $U@$IP:crx/tools/
rsync -a -e "$S" $O/chunks.plan $O/run_chunks_crx.sh $U@$IP:crx/
echo "local:"; md5 -r $M/build/demo/qwenos-e1m1.elf $M/build/demo/crx-plan.bin $M/../engine/DMC100-Doom/build/sw/nor/E1.img
echo "box:";   ssh_ 'cd ~/crx; md5sum build/qwenos-e1m1.elf build/crx-plan.bin E1.img'
