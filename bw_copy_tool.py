import os
import subprocess
import getpass
import json
import time
import shutil
import sys
from pathlib import Path
from datetime import datetime, timedelta

# ----------------------- CONFIG -----------------------

CACHE_FILE = Path.home() / ".bw_cache.json"
CACHE_TTL_SECONDS = 3600  # 1 hour
# Configuration
LOG_FILE = Path(__file__).parent / "bw_tool.log"
FREE_SPACE_LIMIT_BYTES = 200 * 1024 * 1024 * 1024  # 200 GB
MAX_RETRIES = 3  # Maximum number of retry attempts
RETRY_DELAY = 3  # Delay between retries in seconds

# Speed optimization settings
SPEED_OPTIMIZATION = "auto"  # "rsync", "scp", or "auto"

# ----------------------- LOGGING ----------------------

def log_action(action, folder, status, extra=""):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as log:
        log.write(f"[{timestamp}] ACTION: {action} | FOLDER: {folder} | STATUS: {status} | {extra}\n")


def log_user_operation(operation, details, user_input="", result="", extra=""):
    """Log user operations with detailed information"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as log:
        log.write(f"[{timestamp}] USER_OP: {operation} | DETAILS: {details} | INPUT: {user_input} | RESULT: {result} | {extra}\n")


def log_file_operation(operation, file_path, size="", status="", extra=""):
    """Log file-specific operations"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as log:
        log.write(f"[{timestamp}] FILE_OP: {operation} | PATH: {file_path} | SIZE: {size} | STATUS: {status} | {extra}\n")


def log_session_start(bw_name, connection_type, remote_ip, remote_user):
    """Log session start information"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # Add session separator for better readability
    separator = "=" * 80
    session_header = f"####### BW Recordings Copy Tool - Session Start #######"
    
    with open(LOG_FILE, "a") as log:
        log.write(f"\n{separator}\n")
        log.write(f"{session_header}\n")
        log.write(f"{separator}\n")
        log.write(f"[{timestamp}] SESSION_START | BW_NAME: {bw_name} | CONNECTION: {connection_type} | IP: {remote_ip} | USER: {remote_user}\n")


def log_session_end(bw_name, total_operations=0, successful_operations=0):
    """Log session end information"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # Add session end separator
    separator = "=" * 80
    session_footer = f"####### BW Recordings Copy Tool - Session End #######"
    
    with open(LOG_FILE, "a") as log:
        log.write(f"[{timestamp}] SESSION_END | BW_NAME: {bw_name} | TOTAL_OPS: {total_operations} | SUCCESSFUL: {successful_operations}\n")
        log.write(f"{separator}\n")
        log.write(f"{session_footer}\n")
        log.write(f"{separator}\n\n")

# ----------------------- UTILS ------------------------

def print_banner():
    print("=" * 60)
    print("\U0001F4E6  Welcome to the BW Recordings Copy Tool  \U0001F4E6")
    print("=" * 60)


def load_cached_credentials():
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
        if time.time() - data["timestamp"] < CACHE_TTL_SECONDS:
            return data["username"], data["password"]
        else:
            return None
    except Exception:
        return None


def cache_credentials(username, password):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump({"username": username, "password": password, "timestamp": time.time()}, f)
        os.chmod(CACHE_FILE, 0o600)
    except Exception as e:
        print("⚠️ Failed to cache credentials:", e)


def remove_ssh_key(remote_ip):
    known_hosts_path = os.path.expanduser("~/.ssh/known_hosts")
    subprocess.run(f"ssh-keygen -R {remote_ip} -f {known_hosts_path}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def get_local_free_space():
    total, used, free = shutil.disk_usage(Path.cwd())
    return free


def ensure_valid_credentials(remote_user, remote_ip, password):
    """Verify SSH credentials; if invalid, prompt user to re-enter and update cache."""
    print("\n🔐 Verifying SSH credentials...")
    # Quick sanity check for obviously bad cached usernames (e.g., '1'/'2' from menu input)
    if not remote_user or remote_user.isdigit():
        print("❌ Cached username looks invalid. Please re-enter your SSH credentials.")
    else:
        if check_ssh_connection(remote_user, remote_ip, password):
            return remote_user, password
        print("❌ Cached credentials failed. Please re-enter your SSH username and password.")

    for attempt in range(3):
        new_user = input("👤 Enter remote SSH username: ").strip()
        new_pass = getpass.getpass("🔐 Enter SSH password: ").strip()
        if check_ssh_connection(new_user, remote_ip, new_pass):
            cache_credentials(new_user, new_pass)
            print("✅ Credentials verified and updated.")
            return new_user, new_pass
        else:
            print("❌ Authentication failed. Please try again.")

    print("⚠️  Using existing credentials; authentication may fail.")
    return remote_user, password


def run_with_retry(cmd, description="command", max_retries=MAX_RETRIES, delay=RETRY_DELAY, capture_output=True):
    """Run a command with retry logic and exponential backoff"""
    for attempt in range(max_retries):
        if attempt > 0:
            print(f"🔄 Retry attempt {attempt + 1}/{max_retries} for {description}...")
            time.sleep(delay * attempt)  # Exponential backoff
        
        print(f"🚀 Running {description} (attempt {attempt + 1}/{max_retries})...")
        result = subprocess.run(cmd, shell=True, capture_output=capture_output, text=True)
        
        if result.returncode == 0:
            print(f"✅ {description} completed successfully!")
            return result
        else:
            print(f"❌ {description} failed (attempt {attempt + 1}/{max_retries})")
            if attempt == max_retries - 1:
                print(f"💥 {description} failed after {max_retries} attempts")
            else:
                print(f"⏳ Waiting {delay * (attempt + 1)} seconds before retry...")
    
    return result


def check_folder_overwrite(base_local_path, folder_name):
    """Check if destination folder exists and prompt user for action"""
    if base_local_path.exists():
        print(f"⚠️  Destination folder '{folder_name}' already exists at:")
        print(f"   {base_local_path}")
        while True:
            choice = input("Choose action (S)kip/(O)verwrite/(R)ename: ").strip().lower()
            if choice in ['s', 'skip']:
                print(f"⏭️  Skipping '{folder_name}'")
                return "skip"
            elif choice in ['o', 'overwrite']:
                print(f"🗑️  Will overwrite existing folder '{folder_name}'")
                return "overwrite"
            elif choice in ['r', 'rename']:
                new_name = input(f"Enter new name for '{folder_name}': ").strip()
                if new_name:
                    new_path = base_local_path.parent / new_name
                    print(f"📝 Will copy to '{new_name}' instead")
                    return f"rename:{new_name}"
                else:
                    print("❌ Invalid name, please try again")
            else:
                print("❌ Invalid choice. Please enter 'S', 'O', 'R' or 'skip', 'overwrite', 'rename'")
    return "proceed"


def parse_rsync_progress(line):
    """Parse rsync progress output to extract percentage and speed"""
    if "progress2" in line:
        # Extract percentage from rsync --info=progress2 output
        if "%" in line:
            try:
                percent = line.split("%")[0].split()[-1]
                return float(percent)
            except:
                pass
    return None


class ProgressBar:
    """Simple progress display with speed and ETA"""
    
    def __init__(self, total_size_bytes, description="Copying"):
        self.total_size = total_size_bytes
        self.description = description
        self.current_size = 0
        self.start_time = time.time()
        self.last_update = 0
        
    def update(self, bytes_transferred):
        """Update progress with bytes transferred"""
        self.current_size = bytes_transferred
        current_time = time.time()
        
        # Update display every 1 second
        if current_time - self.last_update >= 1.0:
            self.last_update = current_time
            self.display()
    
    def display(self):
        """Display current progress as single line"""
        if self.total_size <= 0:
            return
            
        elapsed = time.time() - self.start_time
        if elapsed <= 0:
            return
            
        # Calculate progress
        progress = min(self.current_size / self.total_size, 1.0)
        percent = progress * 100
        
        # Calculate speed
        current_speed = self.current_size / elapsed if elapsed > 0 else 0
        
        # Calculate ETA
        if current_speed > 0:
            remaining_bytes = self.total_size - self.current_size
            eta_seconds = remaining_bytes / current_speed
            eta = str(timedelta(seconds=int(eta_seconds)))
        else:
            eta = "∞"
        
        # Format sizes
        current_mb = self.current_size / (1024 * 1024)
        total_mb = self.total_size / (1024 * 1024)
        speed_mb = current_speed / (1024 * 1024)
        
        # Display as single line: "Copying file.db3: 45.2% | 987.6MB / 2190.4MB | 112.5 MB/s | ETA: 0:10:45"
        status_line = f"\r{self.description}: {percent:5.1f}% | {current_mb:6.1f}MB / {total_mb:6.1f}MB | {speed_mb:5.1f} MB/s | ETA: {eta}"
        
        # Clear line and print
        sys.stdout.write('\033[K')  # Clear line
        sys.stdout.write(status_line)
        sys.stdout.flush()
    
    def finish(self):
        """Complete the progress display"""
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            avg_speed = self.total_size / elapsed / (1024 * 1024)  # MB/s
            print(f"\n✅ {self.description} completed in {elapsed:.1f}s | Average speed: {avg_speed:.1f} MB/s")


def test_network_speed(remote_user, remote_ip, password):
    """Test network speed with a simple file transfer"""
    print("🌐 Testing network speed...")
    
    # Create a test file on remote
    test_cmd = f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no {remote_user}@{remote_ip} 'dd if=/dev/zero of=/tmp/speedtest.dat bs=1M count=100 2>/dev/null && echo \"Test file created\"'"
    result = run_with_retry(test_cmd, "speed test file creation")
    
    if result.returncode == 0:
        # Download test file
        print("📊 Downloading test file to measure speed...")
        print("⏳ Running speed test download...")
        start_time = time.time()
        download_cmd = f"sshpass -p '{password}' rsync -av --progress --no-compress --partial -e \"ssh -o Compression=no -o TCPKeepAlive=yes -o ServerAliveInterval=60 -o Ciphers=aes128-gcm@openssh.com\" {remote_user}@{remote_ip}:/tmp/speedtest.dat ./speedtest.tmp"
        result = subprocess.run(download_cmd, shell=True, capture_output=False, text=True, bufsize=1, universal_newlines=True)
        end_time = time.time()
        
        if result.returncode == 0:
            duration = end_time - start_time
            file_size_mb = 100  # 100MB test file
            speed_mbps = (file_size_mb * 8) / duration  # Convert to Mbps
            
            print(f"📈 Network speed test results:")
            print(f"   File size: {file_size_mb} MB")
            print(f"   Duration: {duration:.2f} seconds")
            print(f"   Speed: {speed_mbps:.1f} Mbps ({speed_mbps/8:.1f} MB/s)")
            
            # Clean up
            subprocess.run("rm -f ./speedtest.tmp", shell=True)
            cleanup_cmd = f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no {remote_user}@{remote_ip} 'rm -f /tmp/speedtest.dat'"
            subprocess.run(cleanup_cmd, shell=True)
            
            return speed_mbps
        else:
            print("❌ Speed test download failed")
            return None
    else:
        print("❌ Speed test file creation failed")
        return None


def diagnose_speed_issues(remote_user, remote_ip, password):
    """Diagnose why copy speed is slow"""
    print("🔍 Diagnosing speed issues...")
    
    # Test 1: Network latency
    print("\n📡 Testing network latency...")
    ping_cmd = f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no {remote_user}@{remote_ip} 'ping -c 3 8.8.8.8'"
    result = run_with_retry(ping_cmd, "network latency test")
    if result.returncode == 0:
        print("✅ Network connectivity OK")
    else:
        print("❌ Network connectivity issues detected")
    
    # Test 2: Remote disk I/O
    print("\n💾 Testing remote disk I/O...")
    disk_cmd = f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no {remote_user}@{remote_ip} 'dd if=/dev/zero of=/tmp/iotest.dat bs=1M count=50 2>&1 | grep copied'"
    result = run_with_retry(disk_cmd, "remote disk I/O test", capture_output=True)
    if result.returncode == 0:
        print(f"✅ Remote disk I/O: {result.stdout.strip()}")
    else:
        print("❌ Remote disk I/O test failed")
    
    # Test 3: Local disk I/O
    print("\n💾 Testing local disk I/O...")
    local_disk_cmd = "dd if=/dev/zero of=./iotest.tmp bs=1M count=50 2>&1 | grep copied"
    result = subprocess.run(local_disk_cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✅ Local disk I/O: {result.stdout.strip()}")
        subprocess.run("rm -f ./iotest.tmp", shell=True)
    else:
        print("❌ Local disk I/O test failed")
    
    # Test 4: SSH connection quality
    print("\n🔐 Testing SSH connection quality...")
    ssh_cmd = f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no {remote_user}@{remote_ip} 'echo \"SSH test successful\"'"
    start_time = time.time()
    result = run_with_retry(ssh_cmd, "SSH connection test", capture_output=True)
    end_time = time.time()
    ssh_latency = (end_time - start_time) * 1000  # Convert to ms
    
    if result.returncode == 0:
        print(f"✅ SSH latency: {ssh_latency:.1f} ms")
        if ssh_latency > 100:
            print("⚠️  High SSH latency detected - this can slow down transfers")
    else:
        print("❌ SSH connection test failed")
    
    # Test 5: Try different SSH ciphers
    print("\n🔐 Testing SSH cipher performance...")
    ciphers = ["aes128-gcm@openssh.com", "aes256-gcm@openssh.com", "aes128-ctr", "aes256-ctr"]
    
    for cipher in ciphers:
        cipher_cmd = f"sshpass -p '{password}' ssh -c {cipher} -o StrictHostKeyChecking=no {remote_user}@{remote_ip} 'echo \"Cipher {cipher} test\"'"
        start_time = time.time()
        result = subprocess.run(cipher_cmd, shell=True, capture_output=True, text=True)
        end_time = time.time()
        
        if result.returncode == 0:
            latency = (end_time - start_time) * 1000
            print(f"   {cipher}: {latency:.1f} ms")
        else:
            print(f"   {cipher}: Failed")
    
    print("\n💡 Recommendations:")
    print("   - If SSH latency > 100ms: Network congestion or distance")
    print("   - If disk I/O slow: Storage bottleneck")
    print("   - Try different SSH ciphers for best performance")

# ---------------------- SSH & FILE OPS ---------------------

def check_ssh_connection(remote_user, remote_ip, password):
    remove_ssh_key(remote_ip)
    
    # Simple SSH connection without encryption overhead
    print("🔄 Testing SSH connection...")
    cmd = f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no -o Compression=no -o TCPKeepAlive=yes -o ServerAliveInterval=60 {remote_user}@{remote_ip} 'echo OK'"
    result = run_with_retry(cmd, "SSH connection test", capture_output=True)
    
    if result.returncode == 0:
        print("✅ SSH connection successful")
        return True
    else:
        print("❌ SSH connection failed")
        return False


def get_remote_folders_with_sizes(remote_user, remote_ip, remote_path, password):
    if not check_ssh_connection(remote_user, remote_ip, password):
        log_action("CONNECT", "N/A", "FAILED", "SSH connection refused")
        print("❌ SSH connection failed!")
        return []

    print("📦 Retrieving folder list and sizes...")
    list_cmd = f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no {remote_user}@{remote_ip} 'cd \"{remote_path}\" && du -sh * 2>/dev/null'"
    result = run_with_retry(list_cmd, "folder list retrieval")

    if result.returncode != 0:
        print("❌ Failed to retrieve folder list.")
        return []

    folders = []
    for line in result.stdout.strip().split("\n"):
        if line:
            size, name = line.split("\t")
            folders.append((name, size))
    return folders


def test_copy_methods(remote_user, remote_ip, remote_path, folder, password):
    """Test different copy methods to find the fastest one"""
    print("🚀 Testing copy methods for optimal speed...")
    
    # Test 1: Optimized rsync
    print("📊 Testing optimized rsync...")
    start_time = time.time()
    test_cmd = f"sshpass -p '{password}' rsync -av --no-compress --partial --info=progress2 -e \"ssh -o Compression=no -o TCPKeepAlive=yes -o ServerAliveInterval=60 -o Ciphers=aes128-gcm@openssh.com\" '{remote_user}@{remote_ip}:{remote_path}/{folder}' ./speed_test_temp/ --dry-run"
    result = subprocess.run(test_cmd, shell=True, capture_output=True, text=True)
    rsync_time = time.time() - start_time
    
    # Test 2: Ultra-fast SCP
    print("📊 Testing ultra-fast SCP...")
    start_time = time.time()
    test_cmd = f"sshpass -p '{password}' scp -o Compression=no -o TCPKeepAlive=yes -o ServerAliveInterval=60 -o Ciphers=aes128-gcm@openssh.com -r '{remote_user}@{remote_ip}:{remote_path}/{folder}' ./speed_test_temp/ --dry-run"
    result = subprocess.run(test_cmd, shell=True, capture_output=True, text=True)
    scp_time = time.time() - start_time
    
    # Clean up test directory
    subprocess.run("rm -rf ./speed_test_temp", shell=True, capture_output=True)
    
    print(f"📈 Copy method speed test results:")
    print(f"   Rsync: {rsync_time:.2f} seconds")
    print(f"   SCP: {scp_time:.2f} seconds")
    
    # Return the faster method
    if rsync_time <= scp_time:
        print("✅ Rsync selected as faster method")
        return "rsync"
    else:
        print("✅ SCP selected as faster method")
        return "scp"


def copy_folder(remote_user, remote_ip, remote_path, folder, password, bw_name):
    base_local_path = Path.cwd() / "bw_storage" / bw_name / "recordings" / folder
    
    # Check for folder overwrite
    overwrite_action = check_folder_overwrite(base_local_path, folder)
    if overwrite_action == "skip":
        log_file_operation("COPY_SKIPPED", folder, "", "USER_SKIP", "User chose to skip existing folder")
        return False
    elif overwrite_action.startswith("rename:"):
        new_name = overwrite_action.split(":")[1]
        base_local_path = Path.cwd() / "bw_storage" / bw_name / "recordings" / new_name
        print(f"📝 Will copy to renamed folder: {new_name}")
        log_file_operation("COPY_RENAMED", folder, "", "RENAMED", f"Renamed to: {new_name}")
    elif overwrite_action == "overwrite":
        print(f"🗑️  Removing existing folder: {base_local_path}")
        shutil.rmtree(base_local_path, ignore_errors=True)
        log_file_operation("COPY_OVERWRITE", folder, "", "OVERWRITE", f"Existing folder removed: {base_local_path}")
    
    base_local_path.mkdir(parents=True, exist_ok=True)
    
    # First get folder size for progress calculation
    print("📊 Getting folder size...")
    size_cmd = f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no {remote_user}@{remote_ip} 'du -sb \"{remote_path}/{folder}\"'"
    size_result = run_with_retry(size_cmd, "folder size check")
    
    total_size = 0
    if size_result.returncode == 0:
        try:
            total_size = int(size_result.stdout.strip().split('\t')[0])
            print(f"📁 Total size: {total_size / (1024*1024):.1f} MB")
            log_file_operation("COPY_SIZE_CHECK", folder, f"{total_size} bytes", "SUCCESS", f"{total_size / (1024*1024):.1f} MB")
        except:
            print("⚠️  Could not determine folder size")
            log_file_operation("COPY_SIZE_CHECK", folder, "unknown", "FAILED", "Could not parse size")
    
    # Test which copy method is fastest (only if auto-detection is enabled)
    if SPEED_OPTIMIZATION == "auto":
        fastest_method = test_copy_methods(remote_user, remote_ip, remote_path, folder, password)
    else:
        fastest_method = SPEED_OPTIMIZATION
        print(f"🚀 Using {fastest_method.upper()} (user preference)")
    
    # Use rsync with retry logic for maximum speed
    print("🚀 Starting copy with retry logic...")
    remote_folder = f"{remote_user}@{remote_ip}:{remote_path}/{folder}"
    print(f"📁 From: {remote_folder}")
    print(f"📁 To: {base_local_path}")
    
    # Initialize progress bar
    progress_bar = ProgressBar(total_size, f"Copying {folder}")
    
    try:
        if fastest_method == "rsync":
            # Use the fastest possible rsync configuration with SSH optimization
            # Single quotes around paths, but double quotes around the SSH command to preserve optimization flags
            cmd = f"sshpass -p '{password}' rsync -av --progress --no-compress --partial -e \"ssh -o Compression=no -o TCPKeepAlive=yes -o ServerAliveInterval=60 -o Ciphers=aes128-gcm@openssh.com\" '{remote_folder}' '{base_local_path}/'"
            
            # Run rsync with real-time progress parsing
            process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
            
            for line in process.stdout:
                # Parse rsync progress output (--progress format)
                if line.strip() and not line.startswith('sending incremental file list'):
                    try:
                        # Look for lines like: "1,234,567  45%  123.45MB/s    0:00:45"
                        if '%' in line and 'MB/s' in line:
                            parts = line.split()
                            for i, part in enumerate(parts):
                                if part.endswith('%'):
                                    percent = float(part[:-1])
                                    bytes_transferred = int((percent / 100) * total_size)
                                    progress_bar.update(bytes_transferred)
                                    break
                    except:
                        pass
                elif "bytes sent" in line and "bytes received" in line:
                    try:
                        # Extract bytes received
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part.isdigit() and i > 0 and parts[i-1] == "received":
                                bytes_received = int(part)
                                progress_bar.update(bytes_received)
                                break
                    except:
                        pass
            
            result = process.wait()
            
        else:
            # Use ultra-fast SCP with progress monitoring
            cmd = f"sshpass -p '{password}' scp -o Compression=no -o TCPKeepAlive=yes -o ServerAliveInterval=60 -o Ciphers=aes128-gcm@openssh.com -r '{remote_folder}' '{base_local_path}/'"
            
            # Run SCP with progress monitoring
            process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
            
            # For SCP, we estimate progress based on time elapsed since SCP doesn't provide detailed progress
            start_time = time.time()
            while process.poll() is None:
                elapsed = time.time() - start_time
                # Estimate progress based on time (assuming constant speed)
                if elapsed > 0 and total_size > 0:
                    # Estimate based on typical network speed (adjust as needed)
                    estimated_speed = 100 * 1024 * 1024  # Assume 100 MB/s as baseline
                    estimated_bytes = min(int(elapsed * estimated_speed), total_size)
                    progress_bar.update(estimated_bytes)
                    progress_bar.display()
                time.sleep(0.5)  # Update every 0.5 seconds
            
            result = process.returncode
        
    finally:
        # Complete the progress bar
        progress_bar.finish()
    
    if result == 0:
        print(f"✅ Copy completed successfully!")
        log_action("COPY", folder, "SUCCESS")
        log_file_operation("COPY_COMPLETE", folder, f"{total_size} bytes", "SUCCESS", f"Local path: {base_local_path}")
        return True
    else:
        print(f"❌ Copy failed after all retry attempts.")
        log_action("COPY", folder, "FAILED")
        log_file_operation("COPY_FAILED", folder, f"{total_size} bytes", "FAILED", "All retry attempts exhausted")
        return False


def copy_logs(remote_user, remote_ip, password, bw_name):
    """Copy logs from /bwr/cramim/debrief/archive/logs"""
    base_local_path = Path.cwd() / "bw_storage" / bw_name / "logs"
    
    # Check for folder overwrite
    overwrite_action = check_folder_overwrite(base_local_path, "logs")
    if overwrite_action == "skip":
        log_file_operation("COPY_LOGS_SKIPPED", "logs", "", "USER_SKIP", "User chose to skip existing logs folder")
        return False
    elif overwrite_action.startswith("rename:"):
        new_name = overwrite_action.split(":")[1]
        base_local_path = Path.cwd() / "bw_storage" / bw_name / new_name
        print(f"📝 Will copy to renamed folder: {new_name}")
        log_file_operation("COPY_LOGS_RENAMED", "logs", "", "RENAMED", f"Renamed to: {new_name}")
    elif overwrite_action == "overwrite":
        print(f"🗑️  Removing existing logs folder: {base_local_path}")
        shutil.rmtree(base_local_path, ignore_errors=True)
        log_file_operation("COPY_LOGS_OVERWRITE", "logs", "", "OVERWRITE", f"Existing folder removed: {base_local_path}")
    
    base_local_path.mkdir(parents=True, exist_ok=True)
    remote_folder = f"{remote_user}@{remote_ip}:/bwr/cramim/debrief/archive/logs"
    
    print(f"🚀 Copying logs with retry logic for maximum speed...")
    log_file_operation("COPY_LOGS_START", "logs", "", "STARTED", f"Remote: {remote_folder}, Local: {base_local_path}")
    
    # Initialize progress bar for logs
    progress_bar = ProgressBar(0, "Copying logs")  # Size unknown for logs
    
    try:
        cmd = f"sshpass -p '{password}' rsync -av --progress --no-compress --partial --info=progress2 -e \"ssh -o Compression=no -o TCPKeepAlive=yes -o ServerAliveInterval=60 -o Ciphers=aes128-gcm@openssh.com\" '{remote_folder}/' '{base_local_path}/'"
        
        # Run rsync with real-time progress parsing
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
        
        for line in process.stdout:
            # Parse rsync progress output (--progress format)
            if line.strip() and not line.startswith('sending incremental file list'):
                try:
                    # Look for lines like: "1,234,567  45%  123.45MB/s    0:00:45"
                    if '%' in line and 'MB/s' in line:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part.endswith('%'):
                                percent = float(part[:-1])
                                # For logs, we don't know total size, so just show percentage
                                progress_bar.current_size = int(percent * 1024 * 1024)  # Estimate 1MB per percent
                                progress_bar.display()
                                break
                except:
                    pass
        
        exit_code = process.wait()
    finally:
        # Complete the progress bar
        progress_bar.finish()

    if exit_code == 0:
        print(f"✅ Copied logs successfully to {base_local_path}")
        log_action("COPY_LOGS", "logs", "SUCCESS")
        log_file_operation("COPY_LOGS_SUCCESS", "logs", "", "SUCCESS", f"Local path: {base_local_path}")
        return True
    else:
        print(f"❌ Failed to copy logs after all retry attempts.")
        log_action("COPY_LOGS", "logs", "FAILED")
        log_file_operation("COPY_LOGS_FAILED", "logs", "", "FAILED", "All retry attempts exhausted")
        return False


def copy_bags(remote_user, remote_ip, password, bw_name):
    """Copy bags from /bwr/cramim/debrief/archive/bags"""
    base_local_path = Path.cwd() / "bw_storage" / bw_name / "bags"
    
    # Check for folder overwrite
    overwrite_action = check_folder_overwrite(base_local_path, "bags")
    if overwrite_action == "skip":
        log_file_operation("COPY_BAGS_SKIPPED", "bags", "", "USER_SKIP", "User chose to skip existing bags folder")
        return False
    elif overwrite_action.startswith("rename:"):
        new_name = overwrite_action.split(":")[1]
        base_local_path = Path.cwd() / "bw_storage" / bw_name / new_name
        print(f"📝 Will copy to renamed folder: {new_name}")
        log_file_operation("COPY_BAGS_RENAMED", "bags", "", "RENAMED", f"Renamed to: {new_name}")
    elif overwrite_action == "overwrite":
        print(f"🗑️  Removing existing bags folder: {base_local_path}")
        shutil.rmtree(base_local_path, ignore_errors=True)
        log_file_operation("COPY_BAGS_OVERWRITE", "bags", "", "OVERWRITE", f"Existing folder removed: {base_local_path}")
    
    base_local_path.mkdir(parents=True, exist_ok=True)
    remote_folder = f"{remote_user}@{remote_ip}:/bwr/cramim/debrief/archive/bags"
    
    print(f"🚀 Copying bags with retry logic for maximum speed...")
    log_file_operation("COPY_BAGS_START", "bags", "", "STARTED", f"Remote: {remote_folder}, Local: {base_local_path}")
    
    # Initialize progress bar for bags
    progress_bar = ProgressBar(0, "Copying bags")  # Size unknown for bags
    
    try:
        cmd = f"sshpass -p '{password}' rsync -av --progress --no-compress --partial --info=progress2 -e \"ssh -o Compression=no -o TCPKeepAlive=yes -o ServerAliveInterval=60 -o Ciphers=aes128-gcm@openssh.com\" '{remote_folder}/' '{base_local_path}/'"
        
        # Run rsync with real-time progress parsing
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
        
        for line in process.stdout:
            # Parse rsync progress output (--progress format)
            if line.strip() and not line.startswith('sending incremental file list'):
                try:
                    # Look for lines like: "1,234,567  45%  123.45MB/s    0:00:45"
                    if '%' in line and 'MB/s' in line:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part.endswith('%'):
                                percent = float(part[:-1])
                                # For bags, we don't know total size, so just show percentage
                                progress_bar.current_size = int(percent * 1024 * 1024)  # Estimate 1MB per percent
                                progress_bar.display()
                                break
                except:
                    pass
        
        exit_code = process.wait()
    finally:
        # Complete the progress bar
        progress_bar.finish()

    if exit_code == 0:
        print(f"✅ Copied bags successfully to {base_local_path}")
        log_action("COPY_BAGS", "bags", "SUCCESS")
        log_file_operation("COPY_BAGS_SUCCESS", "bags", "", "SUCCESS", f"Local path: {base_local_path}")
        return True
    else:
        print(f"❌ Failed to copy bags after all retry attempts.")
        log_action("COPY_BAGS", "bags", "FAILED")
        log_file_operation("COPY_BAGS_FAILED", "bags", "", "FAILED", "All retry attempts exhausted")
        return False


def delete_remote_folder(remote_user, remote_ip, remote_path, folder, password):
    remote_folder_path = f"{remote_path}/{folder}"
    cmd = f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no {remote_user}@{remote_ip} 'rm -rf \"{remote_folder_path}\"'"
    result = run_with_retry(cmd, f"deletion of {folder}", capture_output=False)
    if result.returncode == 0:
        print(f"✅ Deleted '{folder}' from remote.")
        log_action("DELETE", folder, "SUCCESS")
    else:
        print(f"❌ Failed to delete '{folder}' after all retry attempts.")
        log_action("DELETE", folder, "FAILED")

# -------------------------- MAIN -------------------------

def main():
    print_banner()
    
    # Session tracking variables
    session_operations = 0
    successful_operations = 0
    
    # Global speed optimization setting
    global SPEED_OPTIMIZATION

    print("\n📋 Enter the remote system name (e.g., BW104):")
    bw_name = input("Remote name: ").strip().upper()
    if not bw_name.startswith("BW") or not bw_name[2:].isdigit():
        print("❌ Invalid remote name. Exiting.")
        return

    print("\n🌐 Select connection type:")
    print("1. Wi-Fi")
    print("2. RJ45 (LAN)")
    conn_type = input("Enter 1 or 2: ").strip()

    if conn_type == "1":
        ssid = f"{bw_name}-AP"
        print(f"📡 Connecting to Wi-Fi SSID: {ssid}...")
        subprocess.run(f"nmcli dev wifi connect '{ssid}' password '12345678'", shell=True)
        remote_ip = "192.168.40.101"
        connection_type = "Wi-Fi"
    elif conn_type == "2":
        remote_ip = "10.2.2.2"
        connection_type = "RJ45"
    else:
        print("❌ Invalid connection type. Exiting.")
        return

    creds = load_cached_credentials()
    if creds:
        remote_user, password = creds
        print(f"🔐 Using cached credentials for user '{remote_user}'")
    else:
        remote_user = input("👤 Enter remote SSH username: ").strip()
        password = getpass.getpass("🔐 Enter SSH password: ").strip()
        cache_credentials(remote_user, password)

    # Verify credentials and re-prompt if needed
    remote_user, password = ensure_valid_credentials(remote_user, remote_ip, password)

    # Log session start
    log_session_start(bw_name, connection_type, remote_ip, remote_user)
    log_user_operation("LOGIN", f"User logged in to {bw_name}", f"Connection: {connection_type}, IP: {remote_ip}", "SUCCESS", f"User: {remote_user}")

    while True:
        print("\n📁 What would you like to copy?")
        print("1. Recordings")
        print("2. Bags")
        print("3. Logs")
        print("4. Test Network Speed")
        print("5. Diagnose Speed Issues")
        print("6. Speed Optimization Settings")
        print("7. Exit")
        print(f"🚀 Current speed setting: {SPEED_OPTIMIZATION.upper()}")
        data_type = input("Choose (1/2/3/4/5/6/7): ").strip()
        
        session_operations += 1
        log_user_operation("MENU_SELECTION", "Data type selection", f"Choice: {data_type}", "PROCESSING")

        if data_type == "7":
            print("👋 Goodbye!")
            log_user_operation("EXIT", "User chose to exit", "Choice: 7", "SUCCESS")
            break
        elif data_type == "6":
            log_user_operation("SPEED_OPTIMIZATION", "Speed optimization settings", "Choice: 6", "PROCESSING")
            print("\n🚀 Speed Optimization Settings:")
            print("1. Force Rsync (default)")
            print("2. Force SCP (ultra-fast)")
            print("3. Auto-detect fastest method")
            print("4. Return to main menu")
            speed_choice = input("Choose optimization (1/2/3/4): ").strip()
            
            if speed_choice == "1":
                SPEED_OPTIMIZATION = "rsync"
                print("✅ Rsync will be used for all transfers")
                log_user_operation("SPEED_OPTIMIZATION", "Rsync forced", f"Choice: {speed_choice}", "SUCCESS")
            elif speed_choice == "2":
                SPEED_OPTIMIZATION = "scp"
                print("✅ SCP will be used for all transfers (ultra-fast)")
                log_user_operation("SPEED_OPTIMIZATION", "SCP forced", f"Choice: {speed_choice}", "SUCCESS")
            elif speed_choice == "3":
                SPEED_OPTIMIZATION = "auto"
                print("✅ Auto-detection enabled - fastest method will be chosen automatically")
                log_user_operation("SPEED_OPTIMIZATION", "Auto-detect enabled", f"Choice: {speed_choice}", "SUCCESS")
            elif speed_choice == "4":
                log_user_operation("SPEED_OPTIMIZATION", "Return to main menu", f"Choice: {speed_choice}", "SUCCESS")
                continue
            else:
                print("❌ Invalid choice")
                log_user_operation("SPEED_OPTIMIZATION", "Invalid choice", f"Choice: {speed_choice}", "FAILED")
            continue
        elif data_type == "4":
            log_user_operation("NETWORK_TEST", "Network speed test initiated", "Choice: 4", "PROCESSING")
            test_network_speed(remote_user, remote_ip, password)
            successful_operations += 1
            log_user_operation("NETWORK_TEST", "Network speed test completed", "Choice: 4", "SUCCESS")
            continue
        elif data_type == "5":
            log_user_operation("DIAGNOSE", "Speed diagnosis initiated", "Choice: 5", "PROCESSING")
            diagnose_speed_issues(remote_user, remote_ip, password)
            successful_operations += 1
            log_user_operation("DIAGNOSE", "Speed diagnosis completed", "Choice: 5", "SUCCESS")
            continue
        elif data_type not in ["1", "2", "3"]:
            print("❌ Invalid option.")
            log_user_operation("MENU_SELECTION", "Invalid data type selection", f"Choice: {data_type}", "FAILED", "Invalid option")
            continue

        # Set remote path based on data type
        if data_type == "1":
            remote_path = "/bwr/cramim/recordings"
            data_name = "recordings"
        elif data_type == "2":
            remote_path = "/bwr/cramim/debrief/archive/bags"
            data_name = "bags"
        elif data_type == "3":
            remote_path = "/bwr/cramim/debrief/archive/logs"
            data_name = "logs"

        log_user_operation("DATA_TYPE_SELECTED", f"Selected {data_name} for operations", f"Data type: {data_type}", "SUCCESS", f"Remote path: {remote_path}")

        # Show action menu for selected data type
        while True:
            print(f"\n🔄 Actions for {data_name}:")
            if data_type == "1":
                print("1. Copy recording(s)")
                print("2. List recordings")
                print("3. Delete a recording")
                print("4. Return to data type selection")
                print("5. Exit")
                action = input("Choose (1/2/3/4/5): ").strip()
                
                session_operations += 1
                log_user_operation("RECORDING_ACTION", f"Recording action selection", f"Action: {action}", "PROCESSING")

                if action == "5":
                    print("👋 Goodbye!")
                    log_user_operation("EXIT", "User chose to exit from recording menu", f"Action: {action}", "SUCCESS")
                    return
                elif action == "4":
                    log_user_operation("RETURN_MENU", "Return to data type selection", f"Action: {action}", "SUCCESS")
                    break  # Return to data type selection
                elif action == "1":
                    log_user_operation("COPY_RECORDINGS", "Copy recordings initiated", f"Action: {action}", "PROCESSING")
                    folders = get_remote_folders_with_sizes(remote_user, remote_ip, remote_path, password)
                    if not folders:
                        log_user_operation("COPY_RECORDINGS", "No folders found to copy", f"Action: {action}", "FAILED", "No folders available")
                        continue

                    print("\n📁 Available recordings:")
                    for i, (name, size) in enumerate(folders, 1):
                        print(f" {i}. {name} [{size}]")

                    selection = input("Enter folder number(s) separated by comma: ").strip()
                    log_user_operation("FOLDER_SELECTION", f"User selected folders for copy", f"Selection: {selection}", "PROCESSING", f"Available folders: {len(folders)}")
                    
                    indices = [int(i) for i in selection.split(',') if i.strip().isdigit() and 1 <= int(i) <= len(folders)]
                    copied_folders = []
                    failed_folders = []

                    for i in indices:
                        folder, size_str = folders[i - 1]
                        num, unit = float(size_str[:-1]), size_str[-1].upper()
                        multiplier = {'K': 1e3, 'M': 1e6, 'G': 1e9, 'T': 1e12}.get(unit, 1)
                        estimated_bytes = num * multiplier

                        if estimated_bytes > get_local_free_space():
                            print(f"⚠️  Not enough space to copy '{folder}'. Skipping.")
                            log_action("COPY", folder, "SKIPPED", "Insufficient space")
                            log_file_operation("COPY_SKIPPED", folder, size_str, "INSUFFICIENT_SPACE", f"Estimated: {estimated_bytes} bytes")
                            failed_folders.append(folder)
                            continue
                        
                        log_file_operation("COPY_START", folder, size_str, "STARTED", f"Estimated: {estimated_bytes} bytes")
                        if copy_folder(remote_user, remote_ip, remote_path, folder, password, bw_name):
                            copied_folders.append(folder)
                            log_file_operation("COPY_SUCCESS", folder, size_str, "SUCCESS", f"Local path: {Path.cwd() / 'bw_storage' / bw_name / 'recordings' / folder}")
                            successful_operations += 1
                        else:
                            failed_folders.append(folder)
                            log_file_operation("COPY_FAILED", folder, size_str, "FAILED", "Copy operation failed")

                    # Log copy operation summary
                    log_user_operation("COPY_SUMMARY", f"Copy operation completed", f"Selected: {len(indices)}, Copied: {len(copied_folders)}, Failed: {len(failed_folders)}", "SUCCESS" if copied_folders else "PARTIAL", f"Copied: {copied_folders}, Failed: {failed_folders}")

                    if copied_folders:
                        confirm = input(f"\n🧹 Delete copied folder(s) from remote now? (yes/no): ").strip().lower()
                        log_user_operation("DELETE_CONFIRMATION", f"User asked about deleting copied folders", f"Response: {confirm}", "PROCESSING", f"Folders: {copied_folders}")
                        
                        if confirm == "yes":
                            log_user_operation("DELETE_INITIATED", f"Deleting copied folders from remote", f"Response: {confirm}", "PROCESSING", f"Folders to delete: {copied_folders}")
                            for folder in copied_folders:
                                log_file_operation("DELETE_START", folder, "", "STARTED", "Deleting from remote after successful copy")
                                delete_remote_folder(remote_user, remote_ip, remote_path, folder, password)
                                log_file_operation("DELETE_SUCCESS", folder, "", "SUCCESS", "Deleted from remote after successful copy")
                            log_user_operation("DELETE_COMPLETED", f"All copied folders deleted from remote", f"Response: {confirm}", "SUCCESS", f"Deleted folders: {copied_folders}")
                        else:
                            log_user_operation("DELETE_DECLINED", f"User declined to delete copied folders", f"Response: {confirm}", "SUCCESS", f"Kept folders: {copied_folders}")

                elif action == "2":
                    log_user_operation("LIST_RECORDINGS", "List recordings requested", f"Action: {action}", "PROCESSING")
                    folders = get_remote_folders_with_sizes(remote_user, remote_ip, remote_path, password)
                    if not folders:
                        log_user_operation("LIST_RECORDINGS", "No recordings found to list", f"Action: {action}", "FAILED", "No folders available")
                        continue

                    print("\n📁 Available recordings:")
                    for i, (name, size) in enumerate(folders, 1):
                        print(f" {i}. {name} [{size}]")
                    print("\n📝 End of list.")
                    
                    log_user_operation("LIST_RECORDINGS", f"Recordings listed successfully", f"Action: {action}", "SUCCESS", f"Total recordings: {len(folders)}")
                    successful_operations += 1

                elif action == "3":
                    log_user_operation("DELETE_RECORDINGS", "Delete recordings requested", f"Action: {action}", "PROCESSING")
                    folders = get_remote_folders_with_sizes(remote_user, remote_ip, remote_path, password)
                    if not folders:
                        log_user_operation("DELETE_RECORDINGS", "No recordings found to delete", f"Action: {action}", "FAILED", "No folders available")
                        continue

                    print("\n📁 Available recordings:")
                    for i, (name, size) in enumerate(folders, 1):
                        print(f" {i}. {name} [{size}]")

                    selection = input("Enter folder number(s) separated by comma: ").strip()
                    log_user_operation("DELETE_SELECTION", f"User selected folders for deletion", f"Selection: {selection}", "PROCESSING", f"Available folders: {len(folders)}")
                    
                    indices = [int(i) for i in selection.split(',') if i.strip().isdigit() and 1 <= int(i) <= len(folders)]
                    deleted_folders = []

                    for i in indices:
                        folder, size_str = folders[i - 1]
                        log_file_operation("DELETE_START", folder, size_str, "STARTED", "Manual deletion requested by user")
                        delete_remote_folder(remote_user, remote_ip, remote_path, folder, password)
                        deleted_folders.append(folder)
                        log_file_operation("DELETE_SUCCESS", folder, size_str, "SUCCESS", "Manual deletion completed")
                    
                    if deleted_folders:
                        log_user_operation("DELETE_COMPLETED", f"Manual deletion completed", f"Selection: {selection}", "SUCCESS", f"Deleted folders: {deleted_folders}")
                        successful_operations += 1

            elif data_type == "2":
                print("1. Copy bags")
                print("2. Return to data type selection")
                print("3. Exit")
                action = input("Choose (1/2/3): ").strip()
                
                session_operations += 1
                log_user_operation("BAGS_ACTION", f"Bags action selection", f"Action: {action}", "PROCESSING")

                if action == "3":
                    print("👋 Goodbye!")
                    log_user_operation("EXIT", "User chose to exit from bags menu", f"Action: {action}", "SUCCESS")
                    return
                elif action == "2":
                    log_user_operation("RETURN_MENU", "Return to data type selection", f"Action: {action}", "SUCCESS")
                    break  # Return to data type selection
                elif action == "1":
                    log_user_operation("COPY_BAGS", "Copy bags initiated", f"Action: {action}", "PROCESSING")
                    if copy_bags(remote_user, remote_ip, password, bw_name):
                        successful_operations += 1
                        log_user_operation("COPY_BAGS", "Copy bags completed successfully", f"Action: {action}", "SUCCESS", f"Local path: {Path.cwd() / 'bw_storage' / bw_name / 'bags'}")

            elif data_type == "3":
                print("1. Copy logs")
                print("2. Return to data type selection")
                print("3. Exit")
                action = input("Choose (1/2/3): ").strip()
                
                session_operations += 1
                log_user_operation("LOGS_ACTION", f"Logs action selection", f"Action: {action}", "PROCESSING")

                if action == "3":
                    print("👋 Goodbye!")
                    log_user_operation("EXIT", "User chose to exit from logs menu", f"Action: {action}", "SUCCESS")
                    return
                elif action == "2":
                    log_user_operation("RETURN_MENU", "Return to data type selection", f"Action: {action}", "SUCCESS")
                    break  # Return to data type selection
                elif action == "1":
                    log_user_operation("COPY_LOGS", "Copy logs initiated", f"Action: {action}", "PROCESSING")
                    if copy_logs(remote_user, remote_ip, password, bw_name):
                        successful_operations += 1
                        log_user_operation("COPY_LOGS", "Copy logs completed successfully", f"Action: {action}", "SUCCESS", f"Local path: {Path.cwd() / 'bw_storage' / bw_name / 'logs'}")

    # Log session end
    log_session_end(bw_name, session_operations, successful_operations)
    log_user_operation("SESSION_END", f"Session ended for {bw_name}", f"Total operations: {session_operations}", "SUCCESS", f"Successful operations: {successful_operations}")


if __name__ == "__main__":
    main()

