#!/bin/bash
# Starts the test machine: the test user's key, MariaDB, munge, slurmdbd, slurmctld, slurmd, then sshd in front.
set -e
printf '%s\n' "$AUTHORIZED_KEY" > /home/rb/.ssh/authorized_keys
chown rb:rb /home/rb/.ssh/authorized_keys && chmod 600 /home/rb/.ssh/authorized_keys
ssh-keygen -A >/dev/null

mkdir -p /var/spool/slurmd /var/spool/slurmctld /var/log/slurm
chown slurm:slurm /var/spool/slurmctld /var/log/slurm
if ! grep -q '^NodeName=' /etc/slurm/slurm.conf; then
  echo "$(slurmd -C | head -1) State=UNKNOWN" >> /etc/slurm/slurm.conf
  echo "PartitionName=debug Nodes=rbnode Default=YES MaxTime=INFINITE State=UP" >> /etc/slurm/slurm.conf
fi

[ -f /etc/munge/munge.key ] || mungekey --create >/dev/null 2>&1 || create-munge-key >/dev/null 2>&1
chown munge:munge /etc/munge/munge.key && chmod 400 /etc/munge/munge.key
mkdir -p /run/munge && chown munge:munge /run/munge
runuser -u munge -- munged

service mariadb start >/dev/null
mysql -e "CREATE DATABASE IF NOT EXISTS slurm_acct_db; CREATE USER IF NOT EXISTS 'slurm'@'localhost' IDENTIFIED BY 'slurm';
          GRANT ALL ON slurm_acct_db.* TO 'slurm'@'localhost'; FLUSH PRIVILEGES;"
slurmdbd
for i in $(seq 1 30); do sacctmgr -n list cluster >/dev/null 2>&1 && break; sleep 1; done
sacctmgr -i add cluster rb >/dev/null 2>&1 || true
slurmctld
mkdir -p /sys/fs/cgroup/system.slice  # where slurmd puts its own cgroup (see cgroup.conf)
slurmd
exec /usr/sbin/sshd -D -e
