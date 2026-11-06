# qwenos-doom GPU fleet (launched 2026-11-04 00:07 UTC, us-east-1c, tag Project=qwenos-doom)
3 x g5.xlarge (A10G 24GB, 16GB RAM, 100GB gp3), auto-shutdown +300 min (terminate on shutdown => dies ~05:08 UTC)
Key: ~/.ssh/swarm-gpu, user ubuntu. Price: g5.xlarge ~$1.006/h each + gp3 100GB ~$0.011/h each => ~$3.05/h fleet.
us-east-1a/1b had no g5 capacity.

| id | public IP (changes if stopped/started) |
|---|---|
| i-078685adb17ddc670 | <redacted-host> |
| i-0eb70e13af538209f | <redacted-host> |
| i-0f44ce311dcf940aa | <redacted-host> |

Hard cap if left to auto-terminate: 5h x $3.05 = ~$15.3. Estimate updated in final report.
Layout on each: ~/venv, ~/repo/{tools,ports/doomdmc,build/*.elf,E1.img}, ~/qwenputer (upstream clone, PYTHONPATH=~/qwenputer/experimental/riscv), ~/q4-rv1 (merged ckpt, 18GB bf16).
Not mine but running at launch: i-08c33847a624d36b1 (allgit-bench), i-09ccfdb88f2d89b07 (allgit-bench-extra), c6i.4xlarge ~$0.68/h each.
