"""A stand-in for `ssh HOST COMMAND` in the tests: runs COMMAND with the local sh, in a "remote" home folder
(FAKE_SSH_HOME), passing stdin through. Options (-o X, -p N) are skipped like ssh would take them."""
import os
import subprocess
import sys

args = sys.argv[1:]
while args and args[0].startswith("-"):
    args = args[2:] if args[0] in ("-o", "-p", "-i", "-l") else args[1:]
host, cmd = args[0], args[1]
home = os.environ["FAKE_SSH_HOME"]
os.makedirs(home, exist_ok=True)
env = {**os.environ, "HOME": home}
sys.exit(subprocess.run(["sh", "-c", cmd], cwd=home, env=env, stdin=sys.stdin.buffer).returncode)
