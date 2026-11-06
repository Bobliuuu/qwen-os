#!/bin/bash
# Launch ONE p4d.24xlarge (8x A100-40GB, ~$21.96/h) from the qwenos-doom AMI. Auto-terminates after 180 min.
# Usage: AMI=ami-... ./launch_p4d.sh        (DRY=1 for --dry-run)   Prints instance id + IP.
set -e
AMI=${AMI:-ami-0a4ca2e8b9e2301cf}
P="--profile lab --region us-east-1"
SG=sg-0639a5a16c85956c0
# AZ subnets of the vpc (1a,1b had no g5; try all until p4d capacity is found)
SUBNETS="subnet-0f22b6f0826d7dc26 subnet-07a7973b75721ccd3 subnet-00ad0ae33a4861c7b subnet-0764b300ba13624ff subnet-09a80a9e25362c0cc subnet-07ab4b564fac5eab4"
UD=$(printf '#!/bin/bash\nshutdown -h +180\n')
for s in $SUBNETS; do
  out=$(aws ec2 run-instances $P ${DRY:+--dry-run} --image-id $AMI --instance-type p4d.24xlarge --count 1 \
    --key-name swarm-gpu --security-group-ids $SG --subnet-id $s \
    --instance-initiated-shutdown-behavior terminate \
    --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=150,VolumeType=gp3,Throughput=1000,Iops=6000,DeleteOnTermination=true}' \
    --user-data "$UD" \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Project,Value=qwenos-doom},{Key=Name,Value=qwenos-doom-p4d}]' \
    --query 'Instances[0].InstanceId' --output text 2>&1) || true
  echo "$s: $out"
  case "$out" in i-*) ID=$out; break;; *DryRunOperation*) echo dry-run ok; exit 0;; esac
done
[ -n "$ID" ] || { echo "no capacity in any AZ"; exit 1; }
aws ec2 wait instance-running $P --instance-ids $ID
IP=$(aws ec2 describe-instances $P --instance-ids $ID --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
echo "INSTANCE=$ID IP=$IP  terminate: aws ec2 terminate-instances --profile lab --region us-east-1 --instance-ids $ID"
echo "$ID $IP" > /Users/jhome/qwenos-work/out/model/p4d.id
