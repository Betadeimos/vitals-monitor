import psutil
import time
import os
import sys
import subprocess

# Windows-only imports for hung state detection
try:
    import ctypes
    from ctypes import wintypes
except ImportError:
    ctypes = None

# IOCTL for getting physical disk number from drive handle
IOCTL_STORAGE_GET_DEVICE_NUMBER = 0x002D1080

class STORAGE_DEVICE_NUMBER(ctypes.Structure):
    _fields_ = [
        ("DeviceType", wintypes.DWORD),
        ("DeviceNumber", wintypes.DWORD),
        ("PartitionNumber", wintypes.DWORD),
    ]

def get_physical_drive_name(drive_letter):
    """
    On Windows, maps a logical drive letter (e.g., 'C:') to a physical 
    drive name used by psutil (e.g., 'PhysicalDrive1').
    """
    if os.name != 'nt' or ctypes is None:
        return drive_letter
    
    # Normalize drive letter for CreateFile
    dl = drive_letter.strip("\\")
    drive_path = f"\\\\.\\{dl}"
    
    # Open handle to the drive
    h_device = ctypes.windll.kernel32.CreateFileW(
        drive_path,
        0, # No access needed
        0x00000001 | 0x00000002, # FILE_SHARE_READ | FILE_SHARE_WRITE
        None,
        3, # OPEN_EXISTING
        0,
        None
    )
    
    if h_device == -1:
        return drive_letter # Fallback
    
    sdn = STORAGE_DEVICE_NUMBER()
    bytes_returned = wintypes.DWORD()
    
    success = ctypes.windll.kernel32.DeviceIoControl(
        h_device,
        IOCTL_STORAGE_GET_DEVICE_NUMBER,
        None, 0,
        ctypes.byref(sdn), ctypes.sizeof(sdn),
        ctypes.byref(bytes_returned),
        None
    )
    
    ctypes.windll.kernel32.CloseHandle(h_device)
    
    if success:
        return f"PhysicalDrive{sdn.DeviceNumber}"
    return drive_letter

def get_system_window_map():
    """
    Performs a single EnumWindows pass to map PIDs to their main window info.
    Returns { pid: {'title': str, 'is_responding': bool, 'hwnd': int} }
    """
    if os.name != 'nt' or ctypes is None:
        return {}

    window_map = {}
    
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_void_p)
    
    def enum_handler(hwnd, lparam):
        if not ctypes.windll.user32.IsWindowVisible(hwnd):
            return True
            
        lp_pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(lp_pid))
        pid = lp_pid.value
        
        # We prioritize the "main" window (usually the one with a title)
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        title = ""
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value

        is_responding = not ctypes.windll.user32.IsHungAppWindow(hwnd)
        
        # If we already have a window for this PID, only replace if:
        # 1. The new window has a title and the old one didn't.
        # 2. Both have "3ds max" but the new one has a LONGER title (scene path).
        # 3. The new one has "3ds max" but the old one didn't.
        
        current = window_map.get(pid)
        is_new_max = "3ds max" in title.lower()
        is_old_max = current and "3ds max" in (current['title'] or "").lower()
        
        should_replace = False
        if not current:
            should_replace = True
        elif title and not current['title']:
            should_replace = True
        elif is_new_max and not is_old_max:
            should_replace = True
        elif is_new_max and is_old_max and len(title) > len(current['title']):
            should_replace = True
            
        if should_replace:
            window_map[pid] = {
                'title': title,
                'is_responding': is_responding,
                'hwnd': hwnd
            }
            
        return True

    cb_handler = WNDENUMPROC(enum_handler)
    ctypes.windll.user32.EnumWindows(cb_handler, 0)
    return window_map

def is_process_responding(pid):
    """
    Checks if a Windows process is responding by enumerating its top-level windows.
    """
    if os.name != 'nt' or ctypes is None:
        return True
    
    try:
        found_hung = [False]
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_void_p)
        
        def enum_handler(hwnd, lparam):
            lp_pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(lp_pid))
            if lp_pid.value == pid:
                if ctypes.windll.user32.IsWindowVisible(hwnd):
                    if ctypes.windll.user32.IsHungAppWindow(hwnd):
                        found_hung[0] = True
                        return False
            return True

        cb_handler = WNDENUMPROC(enum_handler)
        ctypes.windll.user32.EnumWindows(cb_handler, 0)
        return not found_hung[0]
    except Exception:
        return True

def get_main_window_handle(pid):
    """
    Finds the main window handle (HWND) for a given process PID on Windows.
    """
    if os.name != 'nt' or ctypes is None:
        return None
    
    try:
        handles = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_void_p)
        
        def enum_handler(hwnd, lparam):
            lp_pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(lp_pid))
            if lp_pid.value == pid:
                if ctypes.windll.user32.IsWindowVisible(hwnd):
                    handles.append(hwnd)
            return True

        cb_handler = WNDENUMPROC(enum_handler)
        ctypes.windll.user32.EnumWindows(cb_handler, 0)
        
        if not handles: return None

        # Prioritize windows with "3ds Max" in title and longest title
        max_handles = []
        for h in handles:
            length = ctypes.windll.user32.GetWindowTextLengthW(h)
            title = ""
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(h, buff, length + 1)
                title = buff.value
            
            if "3ds max" in title.lower():
                max_handles.append((h, len(title)))
        
        if max_handles:
            return max(max_handles, key=lambda x: x[1])[0]
        return handles[0]
    except Exception:
        return None

def attempt_rescue(pid):
    """
    Sends a WM_KEYDOWN message with VK_ESCAPE to the process's main window.
    Only works on Windows.
    """
    if os.name != 'nt' or ctypes is None:
        return False
    
    hwnd = get_main_window_handle(pid)
    if hwnd:
        try:
            WM_KEYDOWN = 0x0100
            VK_ESCAPE = 0x1B
            ctypes.windll.user32.PostMessageW(hwnd, WM_KEYDOWN, VK_ESCAPE, 0)
            return True
        except Exception:
            pass
    return False

def get_window_title(pid):
    """
    Returns the window title of the main window for a given PID on Windows.
    """
    if os.name != 'nt' or ctypes is None:
        return None
    
    hwnd = get_main_window_handle(pid)
    if hwnd:
        try:
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
                return buff.value
        except Exception:
            pass
    return None

def get_foreground_pid():
    """
    Returns the PID of the current foreground window on Windows.
    """
    if os.name != 'nt' or ctypes is None:
        return None
    
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return None
        
        lp_pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(lp_pid))
        return lp_pid.value
    except Exception:
        return None

def clean_title(title, max_length=40):
    """
    Strips common 3ds Max suffixes and truncates the title to max_length.
    """
    if not title:
        return ""
    
    suffixes = [" - Autodesk 3ds Max 2024", " - Autodesk 3ds Max 2023", " - Autodesk 3ds Max 2022", " - 3ds Max"]
    cleaned = title
    for suffix in suffixes:
        if cleaned.endswith(suffix):
            cleaned = cleaned[:-len(suffix)]
            break
            
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length-3] + "..."
        
    return cleaned

def find_processes(target_script_name, all_procs):
    """
    Categorizes the pre-fetched process list to find all targets.
    """
    found = []
    for proc in all_procs:
        try:
            name = (proc.info.get('name') or "").lower()
            
            if target_script_name.lower() in name:
                found.append(proc)
                continue

            if 'python' in name:
                # Lazy-fetch cmdline only for python processes
                cmdline = proc.cmdline()
                if any(target_script_name.lower() in arg.lower() for arg in cmdline):
                    found.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return found

def find_process(target_script_name):
    """
    Scans running processes to find one that matches the target script name.
    Used for tests and standalone mode.
    """
    for proc in psutil.process_iter(attrs=['pid', 'name', 'cmdline']):
        try:
            name = (proc.info.get('name') or "").lower()
            cmdline = proc.info.get('cmdline') or []

            if target_script_name.lower() in name:
                return proc

            if 'python' in name:
                if any(target_script_name.lower() in arg.lower() for arg in cmdline):
                    return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return None

def get_process_metrics(proc):
    """
    Retrieves CPU and RAM usage for a given process.
    """
    try:
        cpu_raw = proc.cpu_percent(interval=None)
        count = psutil.cpu_count() or 1
        cpu_normalized = cpu_raw / count
        
        memory_info = proc.memory_info()
        memory_gb = memory_info.rss / (1024 * 1024 * 1024)
        
        priority = proc.nice()
        cpu_affinity = proc.cpu_affinity()
        
        return {
            'cpu_percent': round(cpu_normalized, 2),
            'memory_gb': round(memory_gb, 2),
            'priority': priority,
            'cpu_affinity': cpu_affinity
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, AttributeError):
        return None

def get_storage_metrics():
    """
    Returns a dictionary with drive utilization (Active Time %).
    """
    if os.name != 'nt':
        return {}

    try:
        t1 = time.perf_counter()
        io1 = psutil.disk_io_counters(perdisk=True)
        time.sleep(0.1)
        t2 = time.perf_counter()
        io2 = psutil.disk_io_counters(perdisk=True)
        dt_s = t2 - t1
    except Exception:
        return {"C": {"utilization_percent": 0.0}, "D": {"utilization_percent": 0.0}}

    metrics = {}
    for letter in ["C", "D"]:
        p_name = get_physical_drive_name(letter + ":")
        io_key = p_name if p_name in io1 else (letter + ":" if (letter + ":") in io1 else None)
        util = 0.0
        if io_key:
            c1, c2 = io1[io_key], io2[io_key]
            b1 = getattr(c1, 'busy_time', c1.read_time + c1.write_time)
            b2 = getattr(c2, 'busy_time', c2.read_time + c2.write_time)
            # busy_time might be mocked or missing
            if not isinstance(b1, (int, float)): b1 = c1.read_time + c1.write_time
            if not isinstance(b2, (int, float)): b2 = c2.read_time + c2.write_time
            
            dbusy_ms = b2 - b1
            util = (dbusy_ms / (dt_s * 1000)) * 100
            
            bytes_moved = (c2.read_bytes + c2.write_bytes) - (c1.read_bytes + c1.write_bytes)
            if bytes_moved > 0:
                mb_s = (bytes_moved / (1024 * 1024)) / dt_s
                synthetic_util = mb_s * 10 
                util = max(util, min(synthetic_util, 100.0))
        
        metrics[letter] = {'utilization_percent': round(min(max(util, 0.0), 100.0), 1)}
    return metrics

def get_vram_metrics(pids=None):
    """
    Execute nvidia-smi and return batch results.
    """
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            stderr=subprocess.STDOUT
        ).decode('utf-8').strip()
        
        total_used_mb = 0.0
        total_max_mb = 0.0
        lines = output.split('\n')
        for line in lines:
            if not line.strip(): continue
            parts = line.split(',')
            if len(parts) == 2:
                total_used_mb += float(parts[0].strip())
                total_max_mb += float(parts[1].strip())
        
        if total_max_mb <= 0: return None

        metrics = {
            'used_gb': round(total_used_mb / 1024, 1),
            'total_gb': round(total_max_mb / 1024, 1),
            'per_pid_vram_gb': {},
            'shared_used_gb': 0.0
        }

        if os.name == 'nt':
            try:
                cmd = ['typeperf', '-sc', '1', '\\GPU Adapter Memory(*)\\Shared Usage']
                res = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, creationflags=0x08000000).decode('utf-8', errors='ignore')
                res_lines = [line.strip() for line in res.split('\n') if line.strip()]
                if len(res_lines) >= 2:
                    data_line = next((l for l in res_lines if l.startswith('"') and ',' in l and any(c.isdigit() for c in l[:20])), None)
                    if data_line:
                        vals = data_line.split(',')
                        total_shared_bytes = sum(float(v.strip('"')) for v in vals[1:] if v.strip('"'))
                        metrics['shared_used_gb'] = round(total_shared_bytes / (1024**3), 2)
            except Exception: pass

        if pids:
            try:
                apps_output = subprocess.check_output(
                    ["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
                    stderr=subprocess.STDOUT
                ).decode('utf-8').strip()
                for pid in pids: metrics['per_pid_vram_gb'][pid] = 0.0
                for line in apps_output.split('\n'):
                    if not line.strip(): continue
                    parts = line.split(',')
                    if len(parts) == 2:
                        p, v = int(parts[0].strip()), float(parts[1].strip())
                        if p in pids: metrics['per_pid_vram_gb'][p] += round(v / 1024, 2)
            except Exception: pass

        return metrics
    except Exception: return None

def empty_working_set(pid):
    """
    Forces the working set of the given PID to the pagefile.
    """
    if os.name != 'nt' or ctypes is None: return False
    try:
        PROCESS_SET_QUOTA = 0x0100
        h_process = ctypes.windll.kernel32.OpenProcess(PROCESS_SET_QUOTA, False, pid)
        if h_process:
            try:
                success = ctypes.windll.psapi.EmptyWorkingSet(h_process)
                return bool(success)
            finally:
                ctypes.windll.kernel32.CloseHandle(h_process)
        return False
    except Exception: return False

def monitor(target_script_name):
    """
    Main monitoring loop.
    """
    print(f"Starting Vitals Watchdog. Searching for '{target_script_name}'...")
    proc = None
    while True:
        if proc is None:
            proc = find_process(target_script_name)
            if proc: print(f"Found process! Locking onto PID: {proc.pid}")
            else:
                print(f"'{target_script_name}' not found. Waiting...")
                time.sleep(5)
                continue
        metrics = get_process_metrics(proc)
        if metrics: print(f"CPU: {metrics['cpu_percent']}% | RAM: {metrics['memory_gb']} GB")
        else:
            print(f"Process lost! Searching again...")
            proc = None
        time.sleep(1)

def main():
    monitor("max_simulator.py")

if __name__ == "__main__":
    main()
