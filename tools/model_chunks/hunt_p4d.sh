#!/bin/bash
# Retry p4d.24xlarge launch across AZs until capacity (max ~40 min). Logs to hunt_p4d.log. Auto-terminates after 180 min via user-data.
AMI=ami-0a4ca2e8b9e2301cf
SG=sg-0639a5a16c85956c0
UD=$(printf '#!/bin/bash\nshutdown -h +180\n')
for i in $(seq 1 40); do
  for s in subnet-0f22b6f0826d7dc26 subnet-07a7973b75721ccd3 subnet-0764b300ba13624ff subnet-00ad0ae33a4861c7b; do
    out=$(aws ec2 run-instances --profile lab --region us-east-1 --image-id $AMI --instance-type p4d.24xlarge --count 1 \
      --key-name swarm-gpu --security-group-ids $SG --subnet-id $s \
      --instance-initiated-shutdown-behavior terminate \
      --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=150,VolumeType=gp3,Throughput=1000,Iops=6000,DeleteOnTermination=true}' \
      --user-data "$UD" \
      --tag-specifications 'ResourceType=instance,Tags=[{Key=Project,Value=qwenos-doom},{Key=Name,Value=qwenos-doom-p4d}]' \
      --query 'Instances[0].InstanceId' --output text 2>&1) 
    echo "$(date +%T) try$i $s: $(echo $out | cut -c1-160)" >> hunt_p4d.log
    case "$out" in i-*) echo "$out $(date +%s)" > p4d.id; echo "GOT $out" >> hunt_p4d.log; exit 0;; esac
  done
  sleep 45
done
echo "gave up" >> hunt_p4d.log
