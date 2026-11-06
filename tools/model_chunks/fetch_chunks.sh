#!/bin/bash
# Run on the Mac: ./fetch_chunks.sh <box-ip>   -> out/model/chunks/<chunk>/
rsync -a -e "ssh -i $HOME/.ssh/swarm-gpu -o StrictHostKeyChecking=no" ubuntu@$1:~/out/ /Users/jhome/qwenos-work/out/model/chunks/
