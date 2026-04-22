import os
import sys
import time
import subprocess
import psutil

# ANSI Escape Codes for UI
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"
BOLD = "\033[1m"

def measure_nvidia_smi_time():
    """Measures the execution time of 'nvidia-smi' in milliseconds."""
    start_time = time.perf_counter()
    try:
        subprocess.check_output(["nvidia-smi"], stderr=subprocess.STDOUT)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return -1 # Indicate failure or not found
    end_time = time.perf_counter()
    return (end_time - start_time) * 1000

def measure_process_iteration_time():
    """Measures the time taken to iterate through all active processes."""
    start_time = time.perf_counter()
    count = 0
    for _ in psutil.process_iter(attrs=['pid', 'name']):
        count += 1
    end_time = time.perf_counter()
    elapsed_ms = (end_time - start_time) * 1000
    return elapsed_ms, count

def check_admin_affinity_permission():
    """Tests if current session can modify process CPU affinity using a dummy subprocess."""
    # Spawn a dummy process (e.g., 'cmd.exe /c pause' on Windows, 'sleep 10' on Unix)
    cmd = ["cmd.exe", "/c", "timeout /t 5"] if os.name == 'nt' else ["sleep", "5"]
    
    try:
        # Use a background process
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        p = psutil.Process(proc.pid)
        
        # Try to get and then set the same affinity
        current_affinity = p.cpu_affinity()
        p.cpu_affinity(current_affinity)
        
        # If no AccessDenied, we have permission
        has_permission = True
    except (psutil.AccessDenied, PermissionError):
        has_permission = False
    except Exception:
        has_permission = False
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=1)
        except:
            pass
            
    return has_permission

def render_report(results):
    """Prints a clean diagnostic report to the terminal."""
    report = []
    report.append("\n" + "="*60)
    report.append("V I T A L S   D O C T O R   D I A G N O S T I C S".center(60))
    report.append("="*60)
    
    # nvidia-smi result
    ns_time = results.get('nvidia_smi_ms', -1)
    if ns_time >= 0:
        ns_status = f"{GREEN}{ns_time:.2f} ms{RESET}"
    else:
        ns_status = f"{RED}NOT FOUND OR FAILED{RESET}"
    report.append(f"{'NVIDIA-SMI latency:':<30} {ns_status}")
    
    # Process iteration result
    iter_time = results.get('process_iter_ms', 0)
    iter_count = results.get('process_count', 0)
    report.append(f"{'Process iteration time:':<30} {GREEN}{iter_time:.2f} ms{RESET} ({iter_count} processes)")
    
    # Admin permission result
    has_admin = results.get('admin_affinity', False)
    admin_status = f"{GREEN}YES (SUCCESS){RESET}" if has_admin else f"{RED}NO (ACCESS DENIED){RESET}"
    report.append(f"{'CPU Affinity permissions:':<30} {admin_status}")
    
    report.append("\n" + "="*60)
    report.append("SYSTEM HEALTH SUMMARY".center(60))
    report.append("="*60)
    
    if ns_time > 500:
        report.append(f"{YELLOW}[!] Slow GPU query detected (>500ms). This may cause UI lag.{RESET}")
    if iter_time > 100:
        report.append(f"{YELLOW}[!] Process iteration is slow. Startup search might be sluggish.{RESET}")
    if not has_admin:
        report.append(f"{RED}[X] Admin permissions missing. Life Support core throttling will be disabled.{RESET}")
    else:
        report.append(f"{GREEN}[OK] All critical permissions and low-latency metrics confirmed.{RESET}")
    
    report.append("="*60 + "\n")
    
    print("\n".join(report))

def main():
    results = {}
    
    # 1. nvidia-smi
    results['nvidia_smi_ms'] = measure_nvidia_smi_time()
    
    # 2. Process iteration
    results['process_iter_ms'], results['process_count'] = measure_process_iteration_time()
    
    # 3. Admin affinity
    results['admin_affinity'] = check_admin_affinity_permission()
    
    render_report(results)

if __name__ == "__main__":
    main()
