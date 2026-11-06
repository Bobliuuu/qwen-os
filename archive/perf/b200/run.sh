cd /Users/jhome/qwenos-work/perf/b200
timeout 1500 modal run modal_b200.py --gpu B200 --script exec_microbench.py --args "--elf build/qwenos-e1m1.elf --kernel-elf build/kernel-doomd.elf --disk E1.img --tokenizer /ckpt/q4-rv1/tokenizer.json --skip 3420000 --tokens 20000 --unroll 16 --profile --json /tmp/e.json" > b200_run1.log 2>&1
