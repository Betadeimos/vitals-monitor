import psutil
import time
import os
import sys
import subprocess

# Windows-only imports for hung state detection
try:
    import ctypes
except ImportError:
    ctypes = None

def is_process_responding(pid):
    """
    Checks if a Windows process is responding by enumerating its top-level windows.
    Returns True if no windows are hung, or if not on Windows.
    """
    if os.name != 'nt' or ctypes is None:
        return True
    
    try:
        # State to capture if we found a hung window
        found_hung = [False]
        
        # WNDENUMPROC callback signature: BOOL CALLBACK EnumWindowsProc(_In_ HWND hwnd, _In_ LPARAM lParam);
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_void_p)
        
        def enum_handler(hwnd, lparam):
            lp_pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(lp_pid))
            if lp_pid.value == pid:
                # Only check hung state if the window is visible
                if ctypes.windll.user32.IsWindowVisible(hwnd):
                    # IsHungAppWindow returns True if the window is not responding
                    if ctypes.windll.user32.IsHungAppWindow(hwnd):
                        found_hung[0] = True
                        return False  # Stop enumerating
            return True  # Continue enumerating

        cb_handler = WNDENUMPROC(enum_handler)
        ctypes.windll.user32.EnumWindows(cb_handler, 0)
        
        return not found_hung[0]
    except Exception:
        # On error, default to True (conservative)
        return True

def find_process(target_script_name):
    """
    Scans running processes to find one that matches the target script name.
    """
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            # Check by process name directly first
            if target_script_name.lower() in proc.info['name'].lower():
                return proc
                
            # Check if it's a python process and if the target script is in its cmdline
            name = proc.info['name']
            if 'python' in name.lower():
                cmdline = proc.info['cmdline']
                if cmdline and any(target_script_name in arg for arg in cmdline):
                    return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return None

def get_process_metrics(proc):
    """
    Retrieves CPU and RAM usage for a given process.
    """
    try:
        # psutil.cpu_percent needs to be called twice or with an interval to get a reading, 
        # but here it's called repeatedly in the loop. 
        # For the first call, it might return 0.0.
        cpu_percent = proc.cpu_percent(interval=None) 
        # Normalize CPU by dividing by number of cores
        cpu_percent = cpu_percent / psutil.cpu_count()
        
        memory_info = proc.memory_info()
        memory_gb = memory_info.rss / (1024 * 1024 * 1024)
        
        # Get priority and affinity
        priority = proc.nice()
        cpu_affinity = proc.cpu_affinity()
        
        return {
            'cpu_percent': round(cpu_percent, 2),
            'memory_gb': round(memory_gb, 2),
            'priority': priority,
            'cpu_affinity': cpu_affinity
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None

def get_storage_metrics():
    """
    Return a dictionary with "C" and "D" usage (used, total in GB).
    """
    metrics = {}
    for drive in ["C:", "D:"]:
        try:
            usage = psutil.disk_usage(drive)
            metrics[drive[0]] = {
                'used_gb': round(usage.used / (1024 ** 3), 1),
                'total_gb': round(usage.total / (1024 ** 3), 1)
            }
        except (FileNotFoundError, PermissionError, OSError):
            # Drive might not exist or be accessible
            pass
    return metrics

def get_vram_metrics():
    """
    Execute nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits.
    Handle FileNotFoundError or CalledProcessError by returning None.
    """
    try:
        # On Windows, we might need shell=True or the full path if nvidia-smi is not in PATH,
        # but usually it is if the drivers are installed.
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            stderr=subprocess.STDOUT
        ).decode('utf-8').strip()
        
        # Output format: "used, total" (e.g., "512, 8192")
        parts = output.split(',')
        if len(parts) == 2:
            used_mb, total_mb = map(float, parts)
            return {
                'used_gb': round(used_mb / 1024, 1),
                'total_gb': round(total_mb / 1024, 1)
            }
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        return None
    return None

def monitor(target_script_name):
    """
    Main monitoring loop.
    """
    print(f"Starting Vitals Watchdog. Searching for '{target_script_name}'...")
    
    proc = None
    while True:
        if proc is None:
            proc = find_process(target_script_name)
            if proc:
                print(f"Found process! Locking onto PID: {proc.pid}")
            else:
                print(f"'{target_script_name}' not found. Waiting...")
                time.sleep(5)
                continue
        
        metrics = get_process_metrics(proc)
        if metrics:
            print(f"CPU: {metrics['cpu_percent']}% | RAM: {metrics['memory_gb']} GB")
        else:
            print(f"Process lost! Searching again...")
            proc = None
        
        time.sleep(1)

def main():
    monitor("max_simulator.py")

if __name__ == "__main__":
    main()
