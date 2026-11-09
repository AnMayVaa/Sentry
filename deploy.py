"""
deploy.py - pull the latest code on the Raspberry Pi and restart the Sentry service.

Uses your SSH key / ssh-agent (no password in this file). Settings can be
overridden with environment variables:

    SENTRY_PI_HOST   (default: ohmpatumwan.local)
    SENTRY_PI_USER   (default: ohmpatumwan)
    SENTRY_PI_PATH   (default: /home/ohmpatumwan/Sentry)
    SENTRY_SERVICE   (default: sentry)

If sudo on the Pi needs a password, you are prompted for it (it is never stored).
"""

import getpass
import os
import shlex
import sys

import paramiko

HOST = os.environ.get("SENTRY_PI_HOST", "ohmpatumwan.local")
USER = os.environ.get("SENTRY_PI_USER", "ohmpatumwan")
REPO_PATH = os.environ.get("SENTRY_PI_PATH", "/home/ohmpatumwan/Sentry")
SERVICE = os.environ.get("SENTRY_SERVICE", "sentry")


def run(client, command, sudo_password=None):
    stdin, stdout, stderr = client.exec_command(command)
    if sudo_password is not None:
        stdin.write(sudo_password + "\n")
        stdin.flush()
    out = stdout.read().decode()
    err = stderr.read().decode()
    code = stdout.channel.recv_exit_status()
    return code, out, err


def main():
    print(f"Connecting to {USER}@{HOST}...")
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.WarningPolicy())
    try:
        client.connect(HOST, username=USER, timeout=10)
        print("Connected! Pulling latest code...")

        code, out, err = run(client, f"cd {shlex.quote(REPO_PATH)} && git pull --ff-only")
        print(out)
        if code != 0:
            print("git pull failed:", err)
            return 1

        print(f"Restarting {SERVICE} service...")
        restart = f"systemctl restart {shlex.quote(SERVICE)}"
        code, out, err = run(client, f"sudo -n {restart}")
        if code != 0 and "password" in err.lower():
            pw = getpass.getpass(f"sudo password for {USER}@{HOST}: ")
            code, out, err = run(client, f"sudo -S -p '' {restart}", sudo_password=pw)
        if code != 0:
            print("Restart failed:", err)
            return 1

        code, out, _ = run(client, f"systemctl is-active {shlex.quote(SERVICE)}")
        print(f"Service state: {out.strip()}")
        if out.strip() != "active":
            return 1
        print("Deployment successful!")
        return 0
    except Exception as e:
        print(f"Deployment failed: {e}")
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
