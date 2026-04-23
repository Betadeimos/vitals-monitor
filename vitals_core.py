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

def get_main_window_handle(pid):
    """
    Finds the main window handle (HWND) for a given process PID on Windows.
    Prioritizes windows with titles containing "3ds Max".
    Returns None if not found or not on Windows.
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
                # We prioritize visible windows
                if ctypes.windll.user32.IsWindowVisible(hwnd):
                    handles.append(hwnd)
            return True

        cb_handler = WNDENUMPROC(enum_handler)
        ctypes.windll.user32.EnumWindows(cb_handler, 0)
        
        if not handles:
            return None

        # Prioritize 3ds Max titles
        max_handles = []
        for h in handles:
            length = ctypes.windll.user32.GetWindowTextLengthW(h)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(h, buff, length + 1)
                title = buff.value
                if "3ds max" in title.lower():
                    max_handles.append((h, len(title)))
        
        if max_handles:
            # Pick the one with the longest title (usually scene path)
            return max(max_handles, key=lambda x: x[1])[0]

        return handles[0] # Fallback to first visible
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
            # PostMessageW(hwnd, msg, wparam, lparam)
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
    Returns None if not on Windows or if foreground window cannot be determined.
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
    Appends an ellipsis if truncated.
    """
    if not title:
        return ""
    
    # Strip common suffixes
    suffixes = [" - Autodesk 3ds Max 2024", " - Autodesk 3ds Max 2023", " - Autodesk 3ds Max 2022", " - 3ds Max"]
    cleaned = title
    for suffix in suffixes:
        if cleaned.endswith(suffix):
            cleaned = cleaned[:-len(suffix)]
            break
            
    if len(cleaned) > max_length:
        # Truncate to max_length - 3 to fit the ellipsis
        cleaned = cleaned[:max_length-3] + "..."
        
    return cleaned

def find_process(target_script_name):
    """
    Scans running processes to find one that matches the target script name.
    """
    for proc in psutil.process_iter(attrs=['pid', 'name', 'cmdline']):
        try:
            name = (proc.info.get('name') or "").lower()
            cmdline = proc.info.get('cmdline') or []

            # Check by process name directly first
            if target_script_name.lower() in name:
                return proc

            # Check if it's a python process and if the target script is in its cmdline
            if 'python' in name:
                if any(target_script_name.lower() in arg.lower() for arg in cmdline):
                    return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return None

def find_processes(target_script_name):
    """
    Scans running processes to find all that match the target script name.
    """
    found = []
    for proc in psutil.process_iter(attrs=['pid', 'name', 'cmdline']):
        try:
            name = (proc.info.get('name') or "").lower()
            cmdline = proc.info.get('cmdline') or []

            if target_script_name.lower() in name:
                found.append(proc)
                continue

            if 'python' in name:
                if any(target_script_name.lower() in arg.lower() for arg in cmdline):
                    found.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return found

def get_process_metrics(proc):
    """
    Retrieves CPU and RAM usage for a given process.
    Returns metrics normalized to 0-100% scale for CPU.
    """
    try:
        # On Windows, proc.cpu_percent() returns usage since last call, 
        # but it can be > 100.0 if multi-core usage is high.
        # We divide by cpu_count to normalize to a 0-100% system-wide scale.
        cpu_raw = proc.cpu_percent(interval=None)
        count = psutil.cpu_count() or 1
        cpu_normalized = cpu_raw / count
        
        memory_info = proc.memory_info()
        memory_gb = memory_info.rss / (1024 * 1024 * 1024)
        
        # Get priority and affinity
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

_pdh_query = None
_pdh_counters = {}

def _init_pdh():
    global _pdh_query, _pdh_counters
    if os.name != 'nt' or ctypes is None:
        return
    
    try:
        _pdh_query = PDH_HQUERY()
        # PdhOpenQueryW(szDataSource, dwUserData, phQuery)
        status = ctypes.windll.pdh.PdhOpenQueryW(None, 0, ctypes.byref(_pdh_query))
        if status != 0:
            _pdh_query = None
            return

        # Use PdhAddEnglishCounterW to avoid localization issues
        # It uses the English names even on localized Windows versions
        for drive in ["C:", "D:"]:
            drive_name = get_physical_drive_name(drive)
            if drive_name.startswith("PhysicalDrive"):
                disk_index = drive_name.replace("PhysicalDrive", "")
                # Path: \PhysicalDisk(index)\% Disk Time
                path = f"\\PhysicalDisk({disk_index})\\% Disk Time"
                counter = PDH_HCOUNTER()
                # PdhAddEnglishCounterW(hQuery, szFullCounterPath, dwUserData, phCounter)
                status = ctypes.windll.pdh.PdhAddEnglishCounterW(_pdh_query, path, 0, ctypes.byref(counter))
                if status == 0:
                    _pdh_counters[drive[0]] = counter
        
        # Prime the counters
        ctypes.windll.pdh.PdhCollectQueryData(_pdh_query)
    except Exception:
        _pdh_query = None

def get_storage_metrics():
    """
    Returns a dictionary with drive utilization (Active Time %).
    Uses high-precision sub-sampling with a byte-activity fallback for guaranteed signal.
    """
    if os.name != 'nt':
        return {}

    try:
        # High precision sub-sampling
        t1 = time.perf_counter()
        io1 = psutil.disk_io_counters(perdisk=True)
        
        time.sleep(0.1) # 100ms sample window
        
        t2 = time.perf_counter()
        io2 = psutil.disk_io_counters(perdisk=True)
        
        dt_s = t2 - t1
    except Exception:
        return {"C": {"utilization_percent": 0.0}, "D": {"utilization_percent": 0.0}}

    metrics = {}
    
    # Mapping C: and D:
    for letter in ["C", "D"]:
        p_name = get_physical_drive_name(letter + ":")
        io_key = p_name if p_name in io1 else (letter + ":" if (letter + ":") in io1 else None)
            
        util = 0.0
        if io_key:
            c1, c2 = io1[io_key], io2[io_key]
            
            # 1. Try time-based (busy_time is best, read+write time is fallback)
            # Use getattr with a default and check if the result is a number to be robust against mocks
            b1 = getattr(c1, 'busy_time', None)
            if not isinstance(b1, (int, float)): b1 = c1.read_time + c1.write_time
            
            b2 = getattr(c2, 'busy_time', None)
            if not isinstance(b2, (int, float)): b2 = c2.read_time + c2.write_time
            
            dbusy_ms = b2 - b1
            util = (dbusy_ms / (dt_s * 1000)) * 100
            
            # 2. Aggressive Byte Fallback (Task Manager Active Time reflects I/O intensity)
            # If util is suspiciously low (< 5%) but bytes are moving fast, use throughput
            bytes_moved = (c2.read_bytes + c2.write_bytes) - (c1.read_bytes + c1.write_bytes)
            if bytes_moved > 0:
                mb_s = (bytes_moved / (1024 * 1024)) / dt_s
                # Synthetic: 10MB/s = 100% active time for high-signal UI movement
                synthetic_util = mb_s * 10 
                util = max(util, min(synthetic_util, 100.0))
        
        metrics[letter] = {'utilization_percent': round(min(max(util, 0.0), 100.0), 1)}
    
    return metrics

def get_vram_metrics(pid=None):
    """
    Execute nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits.
    Sums across all GPUs if multiple are present.
    If pid is provided, also try to fetch vram usage for that specific process.
    """
    try:
        # Get total GPU memory (all GPUs)
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
        
        if total_max_mb <= 0:
            return None

        metrics = {
            'used_gb': round(total_used_mb / 1024, 1),
            'total_gb': round(total_max_mb / 1024, 1),
            'process_vram_gb': 0.0,
            'shared_used_gb': 0.0
        }

        # Shared GPU Memory (Windows fallback)
        if os.name == 'nt':
            try:
                # Use typeperf to get Shared Usage across all GPUs
                # creationflags=0x08000000 is CREATE_NO_WINDOW
                cmd = ['typeperf', '-sc', '1', '\\GPU Adapter Memory(*)\\Shared Usage']
                res = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, creationflags=0x08000000).decode('utf-8', errors='ignore')
                res_lines = [line.strip() for line in res.split('\n') if line.strip()]
                
                # typeperf output usually:
                # [0] "(PDH-CSV 4.0)","\\...","..." (Header)
                # [1] "04/22/2026 14:54:43.223","9389805568.000000",... (Data)
                # [2] Exiting, please wait...
                
                if len(res_lines) >= 2:
                    # Look for the line that starts with a quoted timestamp
                    data_line = None
                    for line in res_lines:
                        if line.startswith('"') and ',' in line and any(c.isdigit() for c in line[:20]):
                            data_line = line
                            break
                    
                    if data_line:
                        vals = data_line.split(',')
                        total_shared_bytes = 0.0
                        # Skip the timestamp (first column)
                        for v in vals[1:]:
                            try:
                                v_clean = v.strip('"')
                                if v_clean:
                                    total_shared_bytes += float(v_clean)
                            except (ValueError, IndexError):
                                continue
                        metrics['shared_used_gb'] = round(total_shared_bytes / (1024**3), 2)
            except Exception:
                pass

        if pid:
            try:
                # Get VRAM usage per PID
                apps_output = subprocess.check_output(
                    ["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
                    stderr=subprocess.STDOUT
                ).decode('utf-8').strip()
                
                process_used_mb = 0.0
                for line in apps_output.split('\n'):
                    if not line.strip(): continue
                    app_pid_parts = line.split(',')
                    if len(app_pid_parts) == 2:
                        app_pid_str, app_vram_str = app_pid_parts
                        if int(app_pid_str.strip()) == pid:
                            # A process can use memory on multiple GPUs
                            process_used_mb += float(app_vram_str.strip())
                
                metrics['process_vram_gb'] = round(process_used_mb / 1024, 2)
            except Exception:
                # If we can't get PID-specific info, fallback to 0.0 or None
                # We already initialized to 0.0, which is safer for the stacked bar
                pass

        return metrics
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
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
