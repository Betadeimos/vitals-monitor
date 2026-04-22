import os
import sys
import time
import argparse
import threading
import json
import re
from collections import deque
import psutil
import vitals_core

ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

if os.name == 'nt':
    import msvcrt

CONFIG_FILE = "vitals_config.json"
DEFAULT_CONFIG = {
    "tier1": {
        "cpu_threshold_percent": 80.0,
        "ram_spike_threshold_gb": 0.10,
        "ram_spike_window_seconds": 2.0
    },
    "tier2": {
        "system_ram_threshold_percent": 90.0,
        "window_seconds": 5.0
    },
    "tier3": {
        "cores_to_strip": [0, 1]
    },
    "monitoring": {
        "refresh_interval_seconds": 0.5,
        "vram_monitor_interval_seconds": 2.0,
        "memory_tracker_window_size_seconds": 5.0
    }
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4)
        except Exception:
            return DEFAULT_CONFIG
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return DEFAULT_CONFIG

CONFIG = load_config()

class VRAMMonitor:
    """Non-blocking VRAM monitor that caches results from nvidia-smi."""
    def __init__(self, interval=None):
        self.interval = interval if interval is not None else CONFIG["monitoring"]["vram_monitor_interval_seconds"]
        self.current_metrics = None
        self.target_pid = None
        self.running = True
        self._lock = threading.Lock()
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()

    def _update_loop(self):
        while self.running:
            with self._lock:
                pid = self.target_pid
            metrics = vitals_core.get_vram_metrics(pid=pid)
            with self._lock:
                self.current_metrics = metrics
            time.sleep(self.interval)

    def set_target_pid(self, pid):
        with self._lock:
            self.target_pid = pid

    def get_metrics(self):
        with self._lock:
            return self.current_metrics

    def stop(self):
        self.running = False

class MemoryTracker:
    def __init__(self, window_size_seconds=None):
        self.window_size_seconds = window_size_seconds if window_size_seconds is not None else CONFIG["monitoring"]["memory_tracker_window_size_seconds"]
        self.readings = deque()

    def add_reading(self, memory_gb, timestamp=None):
        if timestamp is None:
            timestamp = time.time()
        self.readings.append((timestamp, memory_gb))
        
        # Evict old readings
        while self.readings and self.readings[0][0] < timestamp - self.window_size_seconds:
            self.readings.popleft()

    def check_threshold(self, threshold_gb, window_seconds=None, current_time=None):
        if len(self.readings) < 2:
            return False
        
        if window_seconds is None:
            window_seconds = CONFIG["tier1"]["ram_spike_window_seconds"]

        if current_time is None:
            current_time = self.readings[-1][0]
            
        # Get readings within the sub-window [current_time - window_seconds, current_time]
        sub_window = [r for r in self.readings if r[0] >= current_time - window_seconds]
        
        if not sub_window:
            return False
            
        min_mem = min(r[1] for r in sub_window)
        current_mem = self.readings[-1][1]
        
        return (current_mem - min_mem) > threshold_gb

    def is_spike(self, threshold_gb):
        # Kept for backward compatibility
        return self.check_threshold(threshold_gb)

# ANSI Escape Codes
RESET = "\033[0m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
ORANGE = "\033[38;5;208m"
WHITE = "\033[37m"
RED = "\033[31m"
RED_BLINK = "\033[1;5;31m"
MOVE_CURSOR_TOP = "\033[H"
CLEAR_SCREEN = "\033[2J"
CLEAR_FROM_CURSOR = "\033[J"
CLEAR_LINE = "\033[K"

# States
NORMAL = "NORMAL"
WARNING = "WARNING"
CRITICAL = "CRITICAL"
LIFE_SUPPORT = "LIFE_SUPPORT"
HUNG = "HUNG"

PRIORITY_MAP = {
    32: "Normal",
    16384: "Below Normal",
    64: "Idle",
    32768: "Above Normal",
    128: "High",
    256: "Realtime"
}

def determine_state(metrics, system_ram_percent, tracker, threshold_gb=None, is_responding=True):
    """
    Tier 1 (Warning): Triggered by sudden memory spikes OR high CPU.
    Tier 2 (Critical): Triggered ONLY when total system RAM exceeds threshold.
    Tier 3 (Life Support): Triggered if the process is not responding.
    """
    if threshold_gb is None:
        threshold_gb = float(CONFIG["tier1"]["ram_spike_threshold_gb"])
    else:
        threshold_gb = float(threshold_gb)

    if not is_responding:
        return LIFE_SUPPORT, "Process is NOT RESPONDING (Hung)"

    system_ram_threshold = float(CONFIG["tier2"]["system_ram_threshold_percent"])
    if system_ram_percent > system_ram_threshold:
        return CRITICAL, f"System RAM > {system_ram_threshold}% ({system_ram_percent:.1f}%)"
    
    is_spike = tracker.check_threshold(threshold_gb)
    is_high_cpu = metrics['cpu_percent'] > float(CONFIG["tier1"]["cpu_threshold_percent"])
    
    if is_spike or is_high_cpu:
        reasons = []
        if is_spike: reasons.append(f"Memory spike detected (>{threshold_gb}GB in {float(CONFIG['tier1']['ram_spike_window_seconds'])}s)")
        if is_high_cpu: reasons.append(f"High CPU usage ({metrics['cpu_percent']:.1f}%)")
        return WARNING, " | ".join(reasons)
    
    return NORMAL, ""

def set_priority(proc, new_state, current_state=None, ctx=None):
    """
    Adjusts the target process priority based on the current state.
    """
    if new_state == current_state:
        return
    
    try:
        if new_state == WARNING:
            if os.name == 'nt':
                # Windows: BELOW_NORMAL_PRIORITY_CLASS
                proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            else:
                # Unix: Higher nice value means lower priority
                proc.nice(10)
            if ctx:
                ctx['status_msg'] = "[INFO] Throttling process priority for stability..."
            else:
                print(f"{CLEAR_LINE}[INFO] Throttling process priority for stability...")
        elif new_state == NORMAL and current_state == WARNING:
            if os.name == 'nt':
                # Windows: NORMAL_PRIORITY_CLASS
                proc.nice(psutil.NORMAL_PRIORITY_CLASS)
            else:
                # Unix: 0 is normal priority
                proc.nice(0)
            if ctx:
                ctx['status_msg'] = "[INFO] Restoring process priority."
            else:
                print(f"{CLEAR_LINE}[INFO] Restoring process priority.")
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        # Gracefully handle if we can't change priority
        pass

def apply_life_support(proc, ctx):
    """
    Saves current process affinity and priority, then throttles them.
    """
    saved_context = ctx['ls_context']
    if saved_context.get('affinity') is not None:
        return # Already applied
    
    try:
        # Save current state
        saved_context['affinity'] = proc.cpu_affinity()
        saved_context['priority'] = proc.nice()
        
        # Throttling
        ctx['status_msg'] = "[LIFE SUPPORT] Throttling cores & priority..."
        
        # Affinity: exclude cores from config if possible
        count = psutil.cpu_count() or 1
        all_cores = list(range(count))
        cores_to_strip = CONFIG["tier3"]["cores_to_strip"]
        
        new_affinity = [c for c in all_cores if c not in cores_to_strip]
        
        if not new_affinity:
            # Fallback if all cores were stripped
            new_affinity = [all_cores[-1]]
            
        try:
            proc.cpu_affinity(new_affinity)
        except (psutil.AccessDenied, PermissionError):
             ctx['status_msg'] = "[ERROR] Admin privileges required for affinity throttling."
        
        # Priority: IDLE
        if os.name == 'nt':
            # psutil.IDLE_PRIORITY_CLASS might not be defined on all platforms, 
            # but we are in a block that checks os.name == 'nt'
            proc.nice(getattr(psutil, 'IDLE_PRIORITY_CLASS', 0x00000040))
        else:
            proc.nice(19) # Maximum nice value on Unix
            
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        # Clear context if we failed to set everything so we don't think we are in LS
        saved_context['affinity'] = None
        saved_context['priority'] = None

def restore_life_support(proc, ctx):
    """
    Restores original process affinity and priority.
    """
    saved_context = ctx['ls_context']
    if saved_context.get('affinity') is None:
        return
        
    try:
        ctx['status_msg'] = "[LIFE SUPPORT] Restoring original affinity & priority."
        try:
            proc.cpu_affinity(saved_context['affinity'])
        except (psutil.AccessDenied, PermissionError):
            ctx['status_msg'] = "[ERROR] Admin privileges required for affinity restoration."
        proc.nice(saved_context['priority'])
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass
    finally:
        saved_context['affinity'] = None
        saved_context['priority'] = None

def get_usage_color(percent):
    if percent <= 50:
        return GREEN
    elif percent <= 75:
        return YELLOW
    elif percent <= 90:
        return ORANGE
    else:
        return RED_BLINK

def draw_shared_vram_bar(shared_used_gb):
    bar_length = 40
    if shared_used_gb <= 0:
        color = GREEN
    else:
        color = RED # Bleeding detected
        
    label_str = f"{color}{'SHARED GPU':<12}{RESET}"
    border_open = f"{CYAN}[{RESET}"
    border_close = f"{CYAN}]{RESET}"
    
    # 1 block per 0.5 GB, max 40 blocks (20 GB)
    filled_length = min(int(shared_used_gb * 2), bar_length)
    if shared_used_gb > 0 and filled_length == 0:
        filled_length = 1
        
    bar_str = '■' * filled_length + '-' * (bar_length - filled_length)
    colored_bar = f"{color}{bar_str}{RESET}"
    
    return f"{label_str} {border_open}{colored_bar}{border_close} {shared_used_gb:.2f} GB"

def draw_bar(label, value, max_value, bar_length=40, char='■', state=NORMAL):
    ratio = min(max(value / max_value, 0.0), 1.0)
    filled_length = int(bar_length * ratio)
    
    if state in (CRITICAL, HUNG):
        color = RED_BLINK
    elif state == LIFE_SUPPORT:
        color = ORANGE
    elif state == WARNING:
        color = YELLOW
    else:
        color = GREEN
    
    label_color = get_usage_color(ratio * 100)
    label_str = f"{label_color}{label:<12}{RESET}"
    bar_str = char * filled_length + '-' * (bar_length - filled_length)
    colored_bar = f"{color}{bar_str}{RESET}"
    border_open = f"{CYAN}[{RESET}"
    border_close = f"{CYAN}]{RESET}"
    
    return f"{label_str} {border_open}{colored_bar}{border_close} {ratio * 100:.1f}%"

def draw_stacked_ram_bar(target_gb, state=NORMAL):
    bar_length = 40
    vm = psutil.virtual_memory()
    total_gb = vm.total / (1024 ** 3)
    used_gb = vm.used / (1024 ** 3)
    system_ram_percent = (used_gb / total_gb) * 100
    
    # Other Apps RAM = Total System Used - Target Process RAM
    other_gb = max(used_gb - target_gb, 0.0)
    
    other_ratio = other_gb / total_gb
    target_ratio = target_gb / total_gb
    
    other_chars = int(bar_length * other_ratio)
    target_chars = int(bar_length * target_ratio)
    
    # Ensure at least 1 char if there is some usage but it rounds to 0
    if other_gb > 0 and other_chars == 0: other_chars = 1
    if target_gb > 0 and target_chars == 0: target_chars = 1

    # Check if we exceed bar_length
    if other_chars + target_chars > bar_length:
        excess = (other_chars + target_chars) - bar_length
        if other_chars >= excess:
            other_chars -= excess
        else:
            target_chars -= excess

    free_chars = max(bar_length - other_chars - target_chars, 0)

    if state in (CRITICAL, HUNG):
        target_color = RED_BLINK
    elif state == LIFE_SUPPORT:
        target_color = ORANGE
    elif state == WARNING:
        target_color = YELLOW
    else:
        target_color = GREEN
        
    # Other Apps: '■' (White), Target: '■' (State Color), Free: '-'
    other_bar = f"{WHITE}{'■' * other_chars}{RESET}"
    target_bar = f"{target_color}{'■' * target_chars}{RESET}"
    free_bar = "-" * free_chars
    
    label_color = get_usage_color(system_ram_percent)
    label_str = f"{label_color}{'RAM':<12}{RESET}"
    border_open = f"{CYAN}[{RESET}"
    border_close = f"{CYAN}]{RESET}"
    
    return f"{label_str} {border_open}{other_bar}{target_bar}{free_bar}{border_close} {system_ram_percent:.1f}%"

def draw_stacked_cpu_bar(target_cpu_percent, system_cpu_percent=None, state=NORMAL):
    bar_length = 40
    
    # Use provided system cpu or sample it (fallback)
    if system_cpu_percent is None:
        system_cpu_percent = psutil.cpu_percent()
    
    # Other Apps CPU = Total System CPU - Target Process CPU
    # Ensure other_cpu doesn't go below 0 if target measurement exceeds system (can happen due to timing)
    other_cpu = max(system_cpu_percent - target_cpu_percent, 0.0)
    
    # ratios are based on 100.0%
    other_ratio = other_cpu / 100.0
    target_ratio = target_cpu_percent / 100.0
    
    other_chars = int(round(bar_length * other_ratio))
    target_chars = int(round(bar_length * target_ratio))
    
    # Ensure we show at least 1 colored block if there is usage > 0%
    if target_cpu_percent > 0.0 and target_chars == 0:
        target_chars = 1
    if other_cpu > 0.0 and other_chars == 0:
        other_chars = 1

    if other_chars + target_chars > bar_length:
        excess = (other_chars + target_chars) - bar_length
        if other_chars >= excess:
            other_chars -= excess
        else:
            target_chars -= excess
            
    idle_chars = bar_length - other_chars - target_chars

    if state in (CRITICAL, HUNG):
        target_color = RED_BLINK
    elif state == LIFE_SUPPORT:
        target_color = ORANGE
    elif state == WARNING:
        target_color = YELLOW
    else:
        target_color = GREEN
        
    # Other Apps: '■' (White), Target: '■' (State Color), Idle: '-'
    other_bar = f"{WHITE}{'■' * other_chars}{RESET}"
    target_bar = f"{target_color}{'■' * target_chars}{RESET}"
    idle_bar = "-" * idle_chars
    
    label_color = get_usage_color(system_cpu_percent)
    label_str = f"{label_color}{'CPU':<12}{RESET}"
    border_open = f"{CYAN}[{RESET}"
    border_close = f"{CYAN}]{RESET}"
    
    return f"{label_str} {border_open}{other_bar}{target_bar}{idle_bar}{border_close} {system_cpu_percent:.1f}%"

def draw_stacked_vram_bar(vram_metrics, state=NORMAL):
    bar_length = 40
    used_gb = vram_metrics['used_gb']
    total_gb = vram_metrics['total_gb']
    process_gb = vram_metrics.get('process_vram_gb', 0.0)

    if process_gb is None:
        process_gb = 0.0

    if total_gb <= 0:
        # Fallback if no VRAM info
        label_str = f"{WHITE}{'VRAM [GPU]':<12}{RESET}"
        border_open = f"{CYAN}[{RESET}"
        border_close = f"{CYAN}]{RESET}"
        return f"{label_str} {border_open}{'-' * bar_length}{border_close} N/A"
    
    vram_percent = (used_gb / total_gb) * 100

    # Other Apps VRAM = Total System Used - Target Process VRAM
    other_gb = max(used_gb - process_gb, 0.0)
    
    other_ratio = other_gb / total_gb
    target_ratio = process_gb / total_gb
    
    other_chars = int(bar_length * other_ratio)
    target_chars = int(bar_length * target_ratio)
    
    # Ensure at least 1 char if there is some usage but it rounds to 0
    if other_gb > 0 and other_chars == 0: other_chars = 1
    if process_gb > 0 and target_chars == 0: target_chars = 1
    
    # Check if we exceed bar_length
    if other_chars + target_chars > bar_length:
        excess = (other_chars + target_chars) - bar_length
        if other_chars > excess:
            other_chars -= excess
        else:
            target_chars = bar_length - other_chars
            
    free_chars = max(bar_length - other_chars - target_chars, 0)
    
    # Ensure the bar is exactly bar_length
    total_chars = other_chars + target_chars + free_chars
    if total_chars < bar_length:
        free_chars += (bar_length - total_chars)
    elif total_chars > bar_length:
        # Should not happen with logic above, but for safety:
        free_chars = max(0, bar_length - other_chars - target_chars)

    if state in (CRITICAL, HUNG):
        target_color = RED_BLINK
    elif state == LIFE_SUPPORT:
        target_color = ORANGE
    elif state == WARNING:
        target_color = YELLOW
    else:
        target_color = GREEN
        
    # Other Apps: '■' (White), Target: '■' (State Color), Free: '-'
    other_bar = f"{WHITE}{'■' * other_chars}{RESET}"
    target_bar = f"{target_color}{'■' * target_chars}{RESET}"
    free_bar = "-" * free_chars
    
    label_color = get_usage_color(vram_percent)
    label_str = f"{label_color}{'VRAM [GPU]':<12}{RESET}"
    border_open = f"{CYAN}[{RESET}"
    border_close = f"{CYAN}]{RESET}"
    
    return f"{label_str} {border_open}{other_bar}{target_bar}{free_bar}{border_close} {vram_percent:.1f}%"

def render_ui(metrics=None, storage_metrics=None, vram_metrics=None, system_cpu=None, state=NORMAL, warning_msg="", instances=None):
    WIDTH = 80
    border_line = f"{CYAN}+{'='*(WIDTH-2)}+{RESET}"
    separator_line = f"{CYAN}| {'-'*(WIDTH-4)} |{RESET}"
    
    def format_line(content, align='left'):
        vis_len = len(ANSI_ESCAPE.sub('', content))
        pad = max(0, (WIDTH - 4) - vis_len)
        if align == 'center':
            left = pad // 2
            right = pad - left
            return f"{CYAN}| {RESET}{' ' * left}{content}{' ' * right}{CYAN} |{RESET}"
        else:
            return f"{CYAN}| {RESET}{content}{' ' * pad}{CYAN} |{RESET}"
            
    lines = []
    
    # Header
    header_text = "V I T A L S   M O N I T O R"
    lines.append(border_line)
    lines.append(format_line(f"{WHITE}{header_text}{RESET}", align='center'))
    lines.append(border_line)
    
    # GLOBAL SYSTEM METRICS
    if storage_metrics:
        lines.append(format_line(f"{WHITE}GLOBAL SYSTEM METRICS{RESET}", align='center'))
        for drive in sorted(storage_metrics.keys()):
            data = storage_metrics[drive]
            lines.append(format_line(draw_bar(f"DISK {drive}", data['utilization_percent'], 100, state=NORMAL)))
        lines.append(border_line)

    if instances is None:
        instances = [{'metrics': metrics, 'vram_metrics': vram_metrics, 'state': state, 'warning_msg': warning_msg, 'pid': None, 'title': None}]
        
    for idx, inst in enumerate(instances):
        i_metrics = inst.get('metrics')
        i_vram = inst.get('vram_metrics')
        i_state = inst.get('state', NORMAL)
        i_msg = inst.get('warning_msg', '')
        i_pid = inst.get('pid')
        i_title = inst.get('title')
        i_status = inst.get('status_msg')

        if i_pid is not None:
            cleaned_title = vitals_core.clean_title(i_title, max_length=40)
            title_str = f" [{cleaned_title}]" if cleaned_title else ""
            inst_header = f"INSTANCE: PID {i_pid}{title_str}"
            lines.append(format_line(f"{WHITE}{inst_header}{RESET}", align='center'))
        
        if not i_metrics:
            continue
            
        # Status Matrix
        priority_raw = i_metrics.get('priority', 'N/A')
        priority_val = PRIORITY_MAP.get(priority_raw, str(priority_raw))
        
        affinity_list = i_metrics.get('cpu_affinity')
        if isinstance(affinity_list, list):
            allowed_cores = len(affinity_list)
            total_cores = psutil.cpu_count() or 1
            affinity_val = f"{allowed_cores}/{total_cores}"
        else:
            affinity_val = 'N/A'
            
        status_matrix = f"{CYAN}[ PRIORITY: {priority_val:<12} ] [ CORES: {affinity_val:<5} ]{RESET}"
        lines.append(format_line(status_matrix, align='center'))
        
        # CPU (Stacked)
        cpu_str = draw_stacked_cpu_bar(i_metrics['cpu_percent'], system_cpu_percent=system_cpu, state=i_state)
        lines.append(format_line(cpu_str))
        
        # RAM (Stacked)
        ram_str = draw_stacked_ram_bar(i_metrics['memory_gb'], state=i_state)
        lines.append(format_line(ram_str))
        
        # System Metrics (VRAM)
        if i_vram is not None or (metrics is not None and vram_metrics is None):
            lines.append(separator_line)
            
            if i_vram is not None:
                shared_gb = i_vram.get('shared_used_gb', 0.0)
                
                vram_state = NORMAL
                # If bleeding into shared memory, force RED/CRITICAL state
                if shared_gb > 0:
                    vram_state = CRITICAL
                elif i_vram['total_gb'] > 0 and (i_vram['used_gb'] / i_vram['total_gb']) > 0.9:
                    vram_state = LIFE_SUPPORT # ORANGE
                
                lines.append(format_line(draw_stacked_vram_bar(i_vram, state=vram_state)))
                
                # SHARED GPU line
                lines.append(format_line(draw_shared_vram_bar(shared_gb)))
                
                if shared_gb > 0:
                    lines.append(format_line(f"{RED_BLINK}!!! WARNING: SHARED GPU MEMORY SPILLAGE !!!{RESET}", align='center'))
            else:
                lines.append(format_line(f"{YELLOW}{'VRAM':<12} [VRAM: NVIDIA DRIVER NOT FOUND]{RESET}"))

        lines.append(separator_line)
        
        # Message Line
        if i_status:
            if i_state == WARNING:
                msg_line = f"{YELLOW}{i_status}{RESET}"
            elif i_state == LIFE_SUPPORT:
                msg_line = f"{ORANGE}{i_status}{RESET}"
            else:
                msg_line = f"{CYAN}{i_status}{RESET}"
        elif i_state == CRITICAL:
            msg_line = f"{RED_BLINK}!!! CRITICAL: SYSTEM RAM EXHAUSTED !!!{RESET}"
        elif i_state == LIFE_SUPPORT:
            msg_line = f"{ORANGE}!!! LIFE SUPPORT: THROTTLING CORES & PRIORITY !!!{RESET}"
        elif i_state == HUNG:
            msg_line = f"{RED_BLINK}!!! PROCESS HUNG (NOT RESPONDING) !!!{RESET}"
        elif i_state == WARNING:
            msg_line = f"{YELLOW}--- WARNING: STABILIZING RESOURCES ---{RESET}"
        else:
            msg_line = f"{GREEN}[ STATUS: MONITORING ACTIVE ]{RESET}"
            
        detail_line = f"{i_msg[:70]:<70}" if i_msg else ""
        
        lines.append(format_line(msg_line, align='center'))
        if i_msg:
            color = RED_BLINK if i_state in (CRITICAL, HUNG) else (ORANGE if i_state == LIFE_SUPPORT else YELLOW)
            lines.append(format_line(f"{color}{detail_line}{RESET}", align='center'))
        else:
            lines.append(format_line("", align='center'))

        
        lines.append(border_line)
        
    return "\n".join([line + CLEAR_LINE for line in lines])
def parse_args():
    parser = argparse.ArgumentParser(
        description=f"{CYAN}V I T A L S   W A T C H D O G\nReal-time resource monitor and crash predictor.{RESET}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"{CYAN}Usage Examples:\n  python vitals.py\n  python vitals.py 3dsmax --threshold 0.25\n  python vitals.py my_app -t 0.1 -i 1.0{RESET}"
    )
    parser.add_argument('target', nargs='?', default=None, 
                        help='Target process name to monitor (default: search for 3dsmax or max_simulator)')
    parser.add_argument('-t', '--threshold', type=float, default=0.10,
                        help='Memory spike threshold in GB to trigger warnings (default: 0.10)')
    parser.add_argument('-i', '--interval', type=float, default=0.5,
                        help='Refresh interval in seconds (default: 0.5)')
    return parser.parse_args()

def clear_screen(full=False):
    if sys.stdout.isatty():
        if full:
            # Move cursor to top-left and clear everything below it
            sys.stdout.write(f"{MOVE_CURSOR_TOP}{CLEAR_FROM_CURSOR}")
        else:
            # Just move cursor to top-left for flicker-free update
            sys.stdout.write(MOVE_CURSOR_TOP)
        sys.stdout.flush()

def start_monitoring(target_script_name=None, threshold_gb=None, interval_s=None):
    if threshold_gb is None:
        threshold_gb = CONFIG["tier1"]["ram_spike_threshold_gb"]
    if interval_s is None:
        interval_s = CONFIG["monitoring"]["refresh_interval_seconds"]

    targets = [target_script_name] if target_script_name else ['3dsmax', 'max_simulator']
    target_display = " or ".join([f"'{t}'" for t in targets])

    # Clear screen initially
    clear_screen(full=True)
    print(f"{CLEAR_LINE}{CYAN}Starting Vitals Watchdog. Searching for {target_display}...{RESET}")
    
    active_instances = {} # pid -> dict
    
    try:
        while True:
            # 1. Scan for new instances
            current_procs = []
            for t in targets:
                current_procs.extend(vitals_core.find_processes(t))
            
            # Deduplicate by PID
            seen_pids = set()
            unique_procs = []
            for p in current_procs:
                if p.pid not in seen_pids:
                    unique_procs.append(p)
                    seen_pids.add(p.pid)

            for proc in unique_procs:
                if proc.pid not in active_instances:
                    vram_monitor = VRAMMonitor()
                    vram_monitor.set_target_pid(proc.pid)
                    active_instances[proc.pid] = {
                        'proc': proc,
                        'tracker': MemoryTracker(),
                        'state': NORMAL,
                        'ls_context': {'affinity': None, 'priority': None},
                        'vram_monitor': vram_monitor,
                        'title': vitals_core.get_window_title(proc.pid),
                        'status_msg': None
                    }
                    clear_screen(full=True)
                    print(f"{CLEAR_LINE}{GREEN}Found process! Locking onto PID: {proc.pid}{RESET}")
            
            # 2. Check for closed instances
            pids_to_remove = []
            for pid, ctx in active_instances.items():
                if not ctx['proc'].is_running():
                    pids_to_remove.append(pid)
                    ctx['vram_monitor'].stop()
                    
            for pid in pids_to_remove:
                del active_instances[pid]
                clear_screen(full=True)
                print(f"{CLEAR_LINE}{RED_BLINK}Process {pid} lost! Removing from dashboard...{RESET}")
            
            if not active_instances:
                clear_screen(full=True)
                print(f"{CLEAR_LINE}{CYAN}{target_display} not found. Waiting...{RESET}")
                time.sleep(1)
                continue

            system_cpu = psutil.cpu_percent(interval=None)
            system_ram_percent = psutil.virtual_memory().percent
            storage_metrics = vitals_core.get_storage_metrics()
            
            instances_data = []
            has_critical = False
            critical_proc = None
            critical_ctx = None
            
            for pid, ctx in list(active_instances.items()):
                proc = ctx['proc']
                tracker = ctx['tracker']
                ls_context = ctx['ls_context']
                vram_monitor = ctx['vram_monitor']
                current_state = ctx['state']
                
                metrics = vitals_core.get_process_metrics(proc)
                if not metrics:
                    continue # might have closed just now
                
                tracker.add_reading(metrics['memory_gb'])
                
                is_responding = vitals_core.is_process_responding(proc.pid)
                state, msg = determine_state(metrics, system_ram_percent, tracker, threshold_gb=threshold_gb, is_responding=is_responding)
                
                # Rescue attempt on Windows if CRITICAL
                if state == CRITICAL and os.name == 'nt':
                    if not ls_context.get('rescue_attempted'):
                        vitals_core.attempt_rescue(proc.pid)
                        ls_context['rescue_attempted'] = True
                        ls_context['rescue_msg'] = "[RESCUE] Sending ESCAPE signal to abort calculation..."
                    
                    if ls_context.get('rescue_msg'):
                        msg += f" | {ls_context['rescue_msg']}"
                elif state in (NORMAL, WARNING):
                    ls_context['rescue_attempted'] = False
                    ls_context['rescue_msg'] = None

                # Life Support handling
                if state == LIFE_SUPPORT:
                    apply_life_support(proc, ctx)
                elif current_state == LIFE_SUPPORT and state != LIFE_SUPPORT:
                    restore_life_support(proc, ctx)

                # Update priority if state changed
                set_priority(proc, state, current_state, ctx)
                ctx['state'] = state
                
                if state == CRITICAL:
                    has_critical = True
                    critical_proc = proc
                    critical_ctx = ctx

                vram_metrics = vram_monitor.get_metrics()
                
                instances_data.append({
                    'pid': pid,
                    'title': ctx['title'],
                    'metrics': metrics,
                    'vram_metrics': vram_metrics,
                    'state': state,
                    'warning_msg': msg,
                    'status_msg': ctx['status_msg']
                })
                
            if not instances_data:
                time.sleep(interval_s)
                continue

            ui_output = render_ui(
                storage_metrics=storage_metrics,
                system_cpu=system_cpu,
                instances=instances_data
            )
            clear_screen()
            print(ui_output)
            
            if has_critical and critical_proc:
                # Prompt for kill
                choice = None
                if os.name == 'nt':
                    print(f"{CLEAR_LINE}{RED_BLINK}CRITICAL! Forcefully kill target process PID {critical_proc.pid}? [Y/N]: {RESET}", end="", flush=True)
                    if msvcrt.kbhit():
                        try:
                            char = msvcrt.getch().decode('utf-8', errors='ignore').upper()
                            if char == 'Y': choice = 'Y'
                            elif char == 'N': choice = 'N'
                        except (UnicodeDecodeError, AttributeError):
                            pass
                else:
                    # Fallback for non-Windows (still blocking as before)
                    try:
                        choice = input(f"{CLEAR_LINE}{RED_BLINK}CRITICAL! Forcefully kill target process PID {critical_proc.pid}? [Y/N]: {RESET}").strip().upper()
                    except EOFError:
                        print(f"{CLEAR_LINE}{RED_BLINK}Non-interactive environment detected. Cannot prompt for kill.{RESET}")
                        time.sleep(2)
                        critical_ctx['tracker'] = MemoryTracker()

                if choice == 'Y':
                    try:
                        critical_proc.terminate()
                        print(f"\n{CLEAR_LINE}{GREEN}Process {critical_proc.pid} terminated.{RESET}")
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                    critical_ctx['vram_monitor'].stop()
                    if critical_proc.pid in active_instances:
                        del active_instances[critical_proc.pid]
                    time.sleep(2)
                    continue
                elif choice == 'N':
                    print(f"\n{CLEAR_LINE}{CYAN}Resuming monitoring. Spike history cleared for PID {critical_proc.pid}.{RESET}")
                    critical_ctx['tracker'] = MemoryTracker()
            else:
                # Ensure the line below the UI is clear when not in CRITICAL
                print(f"{CLEAR_LINE}", end="", flush=True)
                
            time.sleep(interval_s)
    finally:
        for ctx in active_instances.values():
            ctx['vram_monitor'].stop()

def main():
    try:
        args = parse_args()
        start_monitoring(args.target, args.threshold, args.interval)
    except KeyboardInterrupt:
        clear_screen(full=True)
        print(f"{CLEAR_LINE}[INFO] Monitoring terminated by user. Exiting...")
        sys.exit(0)

if __name__ == "__main__":
    main()
