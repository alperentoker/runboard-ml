# A real remote machine for the tests (tests/test_docker_remote.py): Ubuntu with sshd, Python and a one-node SLURM
# cluster that keeps accounting (slurmdbd on MariaDB), so runboard's SSH and SLURM backends run against the real
# ssh, sbatch, sacct, squeue and scancel. The test user is `rb`; the test passes its public key in AUTHORIZED_KEY.
# Started with systemd as its first process instead of start.sh, it boots like a Linux machine: the autostart test
# checks there that runboard's user service starts when the user's session does.
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends openssh-server python3 tar procps munge slurm-wlm slurmdbd mariadb-server \
    systemd dbus libpam-systemd \
 && rm -rf /var/lib/apt/lists/*
RUN useradd -m -s /bin/bash rb && mkdir -p /run/sshd /home/rb/.ssh && chown rb:rb /home/rb/.ssh && chmod 700 /home/rb/.ssh
COPY slurm.conf slurmdbd.conf cgroup.conf /etc/slurm/
COPY start.sh /start.sh
RUN chown slurm:slurm /etc/slurm/slurmdbd.conf && chmod 600 /etc/slurm/slurmdbd.conf && chmod +x /start.sh
EXPOSE 22
CMD ["/start.sh"]
