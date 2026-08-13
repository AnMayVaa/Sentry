import paramiko
import sys

hostname = "OhmPatumwan.local"
username = "pi"
password = "raspberry"

print(f"Connecting to {hostname}...")
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    client.connect(hostname, username=username, password=password, timeout=10)
    print("Connected! Running deployment commands...")
    
    # 1. Pull latest code
    print("Pulling latest code...")
    stdin, stdout, stderr = client.exec_command("cd /home/pi/CSI && git pull")
    print(stdout.read().decode())
    err = stderr.read().decode()
    if err:
        print("Git pull stderr:", err)
    
    # 2. Restart service (needs sudo, so we pipe the password)
    print("Restarting Sentry service...")
    stdin, stdout, stderr = client.exec_command("sudo -S systemctl restart sentry")
    stdin.write(password + "\n")
    stdin.flush()
    print(stdout.read().decode())
    err = stderr.read().decode()
    if err and "[sudo] password for pi:" not in err:
        print("Systemctl stderr:", err)
        
    print("Deployment successful!")
    
except Exception as e:
    print(f"Deployment failed: {e}")
finally:
    client.close()
