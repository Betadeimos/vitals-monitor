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
        "ram_spike_window_seconds": 2.0,
        "auto_remediation_seconds": 10.0
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
        self.target_pids = set()
        self.running = True
        self._lock = threading.Lock()
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()

    def _update_loop(self):
        while self.running:
            with self._lock:
                pids = list(self.target_pids)
            metrics = vitals_core.get_vram_metrics(pids=pids)
            with self._lock:
                self.current_metrics = metrics
            time.sleep(self.interval)

    def update_pids(self, pids):
        with self._lock:
            self.target_pids = set(pids)

    def get_metrics(self):
        with self._lock:
            return self.current_metrics

    def stop(self):
        self.running = False

class StorageMonitor:
    """Non-blocking Storage monitor that runs in a daemon thread."""
    def __init__(self, interval=1.0):
        self.interval = interval
        self.current_metrics = {}
        self.running = True
        self._lock = threading.Lock()
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()

    def _update_loop(self):
        while self.running:
            metrics = vitals_core.get_storage_metrics()
            with self._lock:
                self.current_metrics = metrics
            # Storage metrics sample for 100ms internally, so we sleep for the rest
            time.sleep(max(0, self.interval - 0.1))

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

    def get_slope(self, window_seconds=30):
        """Returns slope in GB/min over recent readings. Positive = growing."""
        if len(self.readings) < 2:
            return 0.0
        now = self.readings[-1][0]
        cutoff = now - window_seconds
        pts = [(t, m) for t, m in self.readings if t >= cutoff]
        if len(pts) < 2:
            return 0.0
        t0 = pts[0][0]
        xs = [t - t0 for t, _ in pts]
        ys = [m for _, m in pts]
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        den = sum((x - mx) ** 2 for x in xs)
        return 0.0 if den == 0 else (num / den) * 60  # GB/min

# ANSI Escape Codes
RESET = "\033[0m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
ORANGE = "\033[38;5;208m"
WHITE = "\033[37m"
RED = "\033[31m"
RED_BLINK = "\033[1;31m"
MOVE_CURSOR_TOP = "\033[H"
CLEAR_SCREEN = "\033[2J"
CLEAR_FROM_CURSOR = "\033[J"
CLEAR_LINE = "\033[K"

# States
NORMAL = "NORMAL"
WARNING = "WARNING"
CRITICAL = "CRITICAL"
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
    Tier 3 (Hung): Triggered if the process is not responding.
    """
    if threshold_gb is None:
        threshold_gb = float(CONFIG["tier1"]["ram_spike_threshold_gb"])
    else:
        threshold_gb = float(threshold_gb)

    if not is_responding:
        return HUNG, "Process is NOT RESPONDING (Hung)"

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

def draw_disk_bar(label, utilization_percent, mb_s=0.0):
    bar_length = 40
    ratio = min(max(utilization_percent / 100.0, 0.0), 1.0)
    filled_length = int(bar_length * ratio)

    color = get_usage_color(utilization_percent)
    label_str = f"{color}{label:<12}{RESET}"
    bar_str = '■' * filled_length + '-' * (bar_length - filled_length)
    colored_bar = f"{color}{bar_str}{RESET}"
    border_open = f"{CYAN}[{RESET}"
    border_close = f"{CYAN}]{RESET}"

    return f"{label_str} {border_open}{colored_bar}{border_close} {mb_s:.1f} MB/s"

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
    
    return f"{label_str} {border_open}{other_bar}{target_bar}{free_bar}{border_close} {system_ram_percent:.1f}%  {target_gb:.1f}/{total_gb:.1f}GB"

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
    
    return f"{label_str} {border_open}{other_bar}{target_bar}{idle_bar}{border_close} {target_cpu_percent:.1f}%  Sys {system_cpu_percent:.1f}%"

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

def draw_gpu_bar(vram_metrics, process_gb=0.0, state=NORMAL):
    """
    Unified GPU bar: [other-white | process-colored | free-dashes | shared-red].
    Shared spillage blocks occupy the rightmost positions, replacing free space.
    Scale is total dedicated VRAM so both segments share one visual ruler.
    """
    bar_length = 40
    used_gb = vram_metrics['used_gb']
    total_gb = vram_metrics['total_gb']
    shared_gb = vram_metrics.get('shared_used_gb', 0.0) or 0.0

    if process_gb is None:
        process_gb = 0.0

    if total_gb <= 0:
        label_str = f"{WHITE}{'VRAM [GPU]':<12}{RESET}"
        border_open = f"{CYAN}[{RESET}"
        border_close = f"{CYAN}]{RESET}"
        return f"{label_str} {border_open}{'-' * bar_length}{border_close} N/A"

    vram_percent = (used_gb / total_gb) * 100
    other_gb = max(used_gb - process_gb, 0.0)

    other_chars = int(bar_length * other_gb / total_gb)
    proc_chars = int(bar_length * process_gb / total_gb)

    if other_gb > 0 and other_chars == 0:
        other_chars = 1
    if process_gb > 0 and proc_chars == 0:
        proc_chars = 1

    # Cap dedicated segments to bar_length
    if other_chars + proc_chars > bar_length:
        excess = (other_chars + proc_chars) - bar_length
        if other_chars >= excess:
            other_chars -= excess
        else:
            proc_chars -= excess

    available = max(bar_length - other_chars - proc_chars, 0)

    # Shared blocks fill from the right of the available space
    shared_chars = min(int(bar_length * shared_gb / total_gb), available)
    if shared_gb > 0 and shared_chars == 0 and available > 0:
        shared_chars = 1

    free_chars = available - shared_chars

    if state in (CRITICAL, HUNG):
        proc_color = RED_BLINK
    elif state == WARNING:
        proc_color = YELLOW
    else:
        proc_color = GREEN

    other_bar = f"{WHITE}{'■' * other_chars}{RESET}" if other_chars > 0 else ""
    proc_bar = f"{proc_color}{'■' * proc_chars}{RESET}" if proc_chars > 0 else ""
    free_bar = "-" * free_chars
    shared_bar = f"{RED_BLINK}{'■' * shared_chars}{RESET}" if shared_chars > 0 else ""

    label_color = get_usage_color(vram_percent)
    label_str = f"{label_color}{'VRAM [GPU]':<12}{RESET}"
    border_open = f"{CYAN}[{RESET}"
    border_close = f"{CYAN}]{RESET}"

    suffix = f"{vram_percent:.1f}%"
    if shared_gb > 0:
        suffix += f" +{shared_gb:.1f}GB"

    return f"{label_str} {border_open}{other_bar}{proc_bar}{free_bar}{shared_bar}{border_close} {suffix}"


_demoted_hogs = set()
_demoted_names: set = set()

def manage_orchestration(active_instances, system_ram_percent, foreground_pid, all_procs):
    """
    Graduated orchestration:
      70-85% RAM — BELOW_NORMAL for hogs (gentle)
      >85% RAM   — IDLE for hogs + empty working set (aggressive)
    Priority-locked instances are never touched.
    Returns a frozenset of demoted process names (for UI display).
    """
    global _demoted_hogs, _demoted_names

    GENTLE_THRESHOLD = 70.0
    AGGRESSIVE_THRESHOLD = 85.0

    COLLATERAL_NAMES = frozenset({
        "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe",
        "discord.exe", "slack.exe", "teams.exe", "msteams.exe",
        "spotify.exe", "outlook.exe", "thunderbird.exe",
        "code.exe", "cursor.exe", "devenv.exe",
    })

    HIGH_PRIORITY        = getattr(psutil, 'HIGH_PRIORITY_CLASS', 128)
    ABOVE_NORMAL_PRIORITY= getattr(psutil, 'ABOVE_NORMAL_PRIORITY_CLASS', 32768)
    NORMAL_PRIORITY      = getattr(psutil, 'NORMAL_PRIORITY_CLASS', 32)
    BELOW_NORMAL_PRIORITY= getattr(psutil, 'BELOW_NORMAL_PRIORITY_CLASS', 16384)
    IDLE_PRIORITY        = getattr(psutil, 'IDLE_PRIORITY_CLASS', 64)

    is_gentle     = system_ram_percent > GENTLE_THRESHOLD
    is_aggressive = system_ram_percent > AGGRESSIVE_THRESHOLD

    # 1. Handle active instances (skip locked; VIP elevation on aggressive only)
    for pid, ctx in active_instances.items():
        if ctx.get('priority_locked', False):
            continue
        proc = ctx['proc']
        try:
            if pid == foreground_pid:
                if is_aggressive:
                    if proc.nice() != HIGH_PRIORITY:
                        proc.nice(HIGH_PRIORITY)
                    ctx['status_msg'] = "VIP · HIGH PRIORITY"
                else:
                    if proc.nice() != NORMAL_PRIORITY:
                        proc.nice(NORMAL_PRIORITY)
                    if ctx.get('status_msg') == "VIP · HIGH PRIORITY":
                        ctx['status_msg'] = None
            else:
                if is_aggressive:
                    if proc.nice() != IDLE_PRIORITY:
                        proc.nice(IDLE_PRIORITY)
                        vitals_core.empty_working_set(proc.pid)
                    ctx['status_msg'] = "DEMOTED TO RECLAIM RAM"
                else:
                    if proc.nice() != NORMAL_PRIORITY:
                        proc.nice(NORMAL_PRIORITY)
                    if ctx.get('status_msg') == "DEMOTED TO RECLAIM RAM":
                        ctx['status_msg'] = None
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
            continue

    # 2. Handle collateral hogs
    if is_gentle:
        target_prio = IDLE_PRIORITY if is_aggressive else BELOW_NORMAL_PRIORITY
        for proc in all_procs:
            try:
                p_name = proc.info['name']
                if not p_name or p_name.lower() not in COLLATERAL_NAMES:
                    continue
                if proc.pid == foreground_pid:
                    continue
                if proc.nice() != target_prio:
                    proc.nice(target_prio)
                    if is_aggressive:
                        vitals_core.empty_working_set(proc.pid)
                    _demoted_hogs.add(proc)
                    _demoted_names.add(p_name.lower().replace('.exe', ''))
            except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError, KeyError):
                continue
    else:
        for proc in list(_demoted_hogs):
            try:
                if proc.is_running() and proc.nice() != NORMAL_PRIORITY:
                    proc.nice(NORMAL_PRIORITY)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        _demoted_hogs.clear()
        _demoted_names.clear()

    return frozenset(_demoted_names)

def restore_all(active_instances=None):
    """
    Restores all tracked instances and any collateral hogs that were demoted.
    """
    global _demoted_hogs
    NORMAL_PRIORITY = getattr(psutil, 'NORMAL_PRIORITY_CLASS', 32)
    
    # 1. Restore tracked instances
    if active_instances:
        for ctx in active_instances.values():
            try:
                proc = ctx['proc']
                if proc.is_running():
                    if proc.nice() != NORMAL_PRIORITY:
                        proc.nice(NORMAL_PRIORITY)
            except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                pass
            
    # 2. Restore collateral hogs
    for proc in list(_demoted_hogs):
        try:
            if proc.is_running():
                if proc.nice() != NORMAL_PRIORITY:
                    proc.nice(NORMAL_PRIORITY)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    _demoted_hogs.clear()

def render_ui(metrics=None, storage_metrics=None, vram_metrics=None, system_cpu=None,
              state=NORMAL, warning_msg="", instances=None, global_warning=None,
              feedback_msg=None, action_log=None, session_seconds=0, demoted_names=None):
    WIDTH = 80
    separator_line = f"{CYAN}| {'-'*(WIDTH-4)} |{RESET}"

    def _state_color(s):
        return YELLOW if s == WARNING else (RED_BLINK if s in (CRITICAL, HUNG) else CYAN)

    def make_border(s=NORMAL):
        return f"{_state_color(s)}+{'='*(WIDTH-2)}+{RESET}"

    def format_line(content, align='left'):
        vis_len = len(ANSI_ESCAPE.sub('', content))
        pad = max(0, (WIDTH - 4) - vis_len)
        if align == 'center':
            left = pad // 2
            right = pad - left
            return f"{CYAN}| {RESET}{' ' * left}{content}{' ' * right}{CYAN} |{RESET}"
        return f"{CYAN}| {RESET}{content}{' ' * pad}{CYAN} |{RESET}"

    lines = []

    # ── Header border — title + session timer in one line ─────────────────
    session_str = time.strftime("%H:%M:%S", time.gmtime(int(session_seconds)))
    title_inner = "= VITALS "                         # 9 chars
    timer_inner = f" session  {session_str} ="        # 20 chars
    fill_len = (WIDTH - 2) - len(title_inner) - len(timer_inner)
    lines.append(f"{CYAN}+{title_inner}{'=' * fill_len}{timer_inner}+{RESET}")

    # ── Global section (disk bars + throttled names) ───────────────────────
    if storage_metrics or demoted_names:
        if storage_metrics:
            for drive in sorted(storage_metrics.keys()):
                data = storage_metrics[drive]
                lines.append(format_line(draw_disk_bar(
                    f"DISK {drive}", data['utilization_percent'], data.get('mb_s', 0.0))))
        # Throttled names — always 1 line when global section is shown
        if demoted_names:
            names_str = "  ·  ".join(sorted(demoted_names)[:4])
            lines.append(format_line(f"{YELLOW}throttled  {names_str}{RESET}"))
        else:
            lines.append(format_line(""))
        lines.append(make_border())

    if instances is None:
        instances = [{'metrics': metrics, 'vram_metrics': vram_metrics,
                      'state': state, 'warning_msg': warning_msg, 'pid': None, 'title': None}]

    for inst in instances:
        i_metrics  = inst.get('metrics')
        i_vram     = inst.get('vram_metrics')
        i_state    = inst.get('state', NORMAL)
        i_msg      = inst.get('warning_msg', '')
        i_pid      = inst.get('pid')
        i_title    = inst.get('title')
        i_status   = inst.get('status_msg')
        i_locked   = inst.get('priority_locked', False)
        i_render   = inst.get('render_mode', False)
        i_r_start  = inst.get('render_start')

        # ── Instance header ───────────────────────────────────────────────
        if i_pid is not None:
            cleaned = vitals_core.clean_title(i_title, max_length=35)
            pid_part = f"{WHITE}>{RESET} {i_pid}  {cleaned}" if cleaned else f"{WHITE}>{RESET} {i_pid}"
            if i_render and i_r_start:
                elapsed = int(time.time() - i_r_start)
                m, s = divmod(elapsed, 60)
                badge = f"{GREEN}[ render  {m:02d}:{s:02d} ]{RESET}"
            else:
                badge = ""
            pid_vis   = len(ANSI_ESCAPE.sub('', pid_part))
            badge_vis = len(ANSI_ESCAPE.sub('', badge))
            gap = max(1, (WIDTH - 4) - pid_vis - badge_vis)
            lines.append(format_line(f"{pid_part}{' ' * gap}{badge}"))

        if not i_metrics:
            continue

        # ── Status matrix ─────────────────────────────────────────────────
        priority_raw = i_metrics.get('priority', 'N/A')
        priority_val = PRIORITY_MAP.get(priority_raw, str(priority_raw))
        affinity_list = i_metrics.get('cpu_affinity')
        if isinstance(affinity_list, list):
            total_cores = psutil.cpu_count() or 1
            affinity_val = f"{len(affinity_list)}/{total_cores}"
        else:
            affinity_val = 'N/A'
        lock_str = "  locked" if i_locked else "        "
        status_matrix = (
            f"{CYAN}priority  {priority_val:<12}  cores  {affinity_val:<7}{lock_str}{RESET}"
        )
        lines.append(format_line(status_matrix))

        # ── Bars ──────────────────────────────────────────────────────────
        lines.append(format_line(draw_stacked_cpu_bar(
            i_metrics['cpu_percent'], system_cpu_percent=system_cpu, state=i_state)))
        lines.append(format_line(draw_stacked_ram_bar(i_metrics['memory_gb'], state=i_state)))

        # ── VRAM ──────────────────────────────────────────────────────────
        if i_vram is not None:
            lines.append(separator_line)
            shared_gb  = i_vram.get('shared_used_gb', 0.0)
            vram_state = (CRITICAL if shared_gb > 0
                          else (WARNING if i_vram['total_gb'] > 0
                                and i_vram['used_gb'] / i_vram['total_gb'] > 0.9
                                else NORMAL))
            pid_vram_gb = i_vram.get('per_pid_vram_gb', {}).get(i_pid, 0.0)
            lines.append(format_line(draw_gpu_bar(i_vram, process_gb=pid_vram_gb, state=vram_state)))
            if shared_gb > 0:
                lines.append(format_line(
                    f"{RED_BLINK}!!! GPU MEMORY OVERFLOW INTO SYSTEM RAM !!!{RESET}", align='center'))

        # ── Single status line ────────────────────────────────────────────
        if i_status:
            icon_color = YELLOW if i_state == WARNING else CYAN
            msg_line = f"{icon_color}[ * ]  {i_status}{RESET}"
        elif i_state == CRITICAL:
            msg_line = f"{RED_BLINK}[ x ]  CRITICAL: system RAM exhausted{RESET}"
        elif i_state == HUNG:
            msg_line = f"{RED_BLINK}[ x ]  HUNG: process not responding{RESET}"
        elif i_state == WARNING:
            triggers = []
            if "Memory spike" in i_msg: triggers.append("RAM spike")
            if "High CPU"    in i_msg: triggers.append("CPU spike")
            trigger_str = " + ".join(triggers) if triggers else "activity spike"
            msg_line = f"{YELLOW}[ ! ] WARNING: {trigger_str}{RESET}"
        else:
            msg_line = f"{GREEN}[ ~ ]  monitoring active{RESET}"

        lines.append(format_line(msg_line, align='center'))

        # ── Action log — always 2 lines for fixed height ──────────────────
        log = list(action_log) if action_log else []
        for i in range(2):
            entry = log[i] if i < len(log) else ""
            if entry:
                lines.append(format_line(f"{CYAN}›{RESET}  {entry}"))
            else:
                lines.append(format_line(""))

        lines.append(make_border(i_state))

    # ── Footer ────────────────────────────────────────────────────────────
    if feedback_msg:
        footer_content = f"{GREEN}{feedback_msg}{RESET}"
    else:
        footer_content = (
            f"F{CYAN}:{RESET}flush  "
            f"B{CYAN}:{RESET}boost  "
            f"R{CYAN}:{RESET}restore  "
            f"{CYAN}[{RESET}{CYAN}:{RESET}strip  "
            f"{CYAN}]{RESET}{CYAN}:{RESET}restore  "
            f"Q{CYAN}:{RESET}quit"
        )
    lines.append(format_line(footer_content, align='center'))

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

def _handle_key(char, active_instances, foreground_pid):
    """
    Dispatch a single keypress to an action. Returns a feedback string or None.
    Raises KeyboardInterrupt on Q.
    """
    HIGH_PRIORITY = getattr(psutil, 'HIGH_PRIORITY_CLASS', 128)
    NORMAL_PRIORITY = getattr(psutil, 'NORMAL_PRIORITY_CLASS', 32)

    if char == 'F':
        freed_gb = 0.0
        for pid, ctx in active_instances.items():
            try:
                proc = ctx['proc']
                before = proc.memory_info().rss / 1024 ** 3
                vitals_core.empty_working_set(pid)
                after = proc.memory_info().rss / 1024 ** 3
                freed_gb += max(before - after, 0.0)
            except Exception:
                pass
        return f"[F] flushed working set  (~{freed_gb:.1f} GB recovered)"

    elif char == 'B':
        for ctx in active_instances.values():
            try:
                ctx['proc'].nice(HIGH_PRIORITY)
                ctx['priority_locked'] = True
            except Exception:
                pass
        return "[B] boosted to HIGH priority  (locked)"

    elif char == 'R':
        for ctx in active_instances.values():
            ctx['priority_locked'] = False
        restore_all(active_instances)
        return "[R] restored all priorities to NORMAL"

    elif char == '[':
        cores = CONFIG.get('tier3', {}).get('cores_to_strip', [0, 1])
        changed = 0
        for ctx in active_instances.values():
            try:
                proc = ctx['proc']
                new_aff = [c for c in proc.cpu_affinity() if c not in cores]
                if new_aff:
                    proc.cpu_affinity(new_aff)
                    changed += 1
            except Exception:
                pass
        return f"[[] Stripped cores {cores} from {changed} instance(s)"

    elif char == ']':
        total_cores = psutil.cpu_count() or 1
        for ctx in active_instances.values():
            try:
                ctx['proc'].cpu_affinity(list(range(total_cores)))
            except Exception:
                pass
        return "[] Restored full CPU affinity"

    elif char == 'Q':
        raise KeyboardInterrupt

    return None


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
    
    active_instances = {}   # pid -> ctx dict
    vram_monitor    = VRAMMonitor()
    storage_monitor = StorageMonitor()
    action_log      = deque(maxlen=3)
    session_start   = time.time()

    # Render-mode detection constants
    RENDER_CPU_THRESHOLD  = 35.0   # % (normalised)
    RENDER_TRIGGER_S      = 15.0   # sustained seconds to enter render mode
    RENDER_CLEAR_S        = 5.0    # idle seconds to leave render mode
    # Hung detection grace period — avoids false positives during file loads
    HUNG_GRACE_S          = 4.0    # seconds of sustained non-response before HUNG fires

    try:
        while True:
            # 1. High-Performance Unified Discovery pass (NO cmdline fetching here)
            all_procs = list(psutil.process_iter(['pid', 'name']))
            
            # 2. Unified Window Scan (One pass for titles and responding states)
            window_map = vitals_core.get_system_window_map()
            
            # Scan for new instances (Lazily fetch cmdline ONLY for python)
            target_procs = vitals_core.find_processes(target_script_name or '3dsmax', all_procs)
            if not target_script_name:
                # Add default targets if none specified
                target_procs.extend(vitals_core.find_processes('max_simulator', all_procs))
            
            # Deduplicate by PID
            seen_pids = set()
            unique_procs = []
            for p in target_procs:
                if p.pid not in seen_pids:
                    unique_procs.append(p)
                    seen_pids.add(p.pid)

            for proc in unique_procs:
                if proc.pid not in active_instances:
                    # Fetch window title from our batch map
                    win_info = window_map.get(proc.pid, {'title': None})
                    active_instances[proc.pid] = {
                        'proc':           proc,
                        'tracker':        MemoryTracker(),
                        'state':          NORMAL,
                        'title':          win_info['title'],
                        'status_msg':     None,
                        'warning_since':  None,
                        'priority_locked':False,
                        'render_mode':    False,
                        'render_start':   None,
                        'high_cpu_since': None,
                        'low_cpu_since':  None,
                        'hung_since':     None,
                    }
                    clear_screen(full=True)
                    print(f"{CLEAR_LINE}{GREEN}Found process! Locking onto PID: {proc.pid}{RESET}")
            
            # 3. Check for closed instances
            pids_to_remove = []
            for pid, ctx in active_instances.items():
                if not ctx['proc'].is_running():
                    pids_to_remove.append(pid)
                    
            for pid in pids_to_remove:
                del active_instances[pid]
                clear_screen(full=True)
                print(f"{CLEAR_LINE}{RED_BLINK}Process {pid} lost! Removing from dashboard...{RESET}")
            
            if not active_instances:
                clear_screen(full=True)
                print(f"{CLEAR_LINE}{CYAN}{target_display} not found. Waiting...{RESET}")
                time.sleep(1)
                continue

            # Update VRAM monitor with current PIDs
            vram_monitor.update_pids(active_instances.keys())

            system_cpu = psutil.cpu_percent(interval=None)
            system_ram_percent = psutil.virtual_memory().percent
            storage_metrics = storage_monitor.get_metrics()
            
            # 4. VIP Detection & Orchestration (returns demoted names for UI)
            foreground_pid = vitals_core.get_foreground_pid()
            demoted_names = manage_orchestration(
                active_instances, system_ram_percent, foreground_pid, all_procs)

            instances_data = []
            has_critical   = False
            critical_proc  = None
            critical_ctx   = None
            vram_metrics   = vram_monitor.get_metrics()
            now            = time.time()

            for pid, ctx in list(active_instances.items()):
                proc    = ctx['proc']
                tracker = ctx['tracker']

                metrics = vitals_core.get_process_metrics(proc)
                if not metrics:
                    continue

                tracker.add_reading(metrics['memory_gb'])

                win_info = window_map.get(pid, {'is_responding': True, 'title': None})

                # Refresh title on every loop so file opens within Max are reflected
                new_title = win_info.get('title')
                if new_title:
                    ctx['title'] = new_title

                # Hung grace period — brief non-response (file open, save) must not trigger HUNG
                raw_responding = win_info.get('is_responding', True)
                if not raw_responding:
                    if ctx['hung_since'] is None:
                        ctx['hung_since'] = now
                    effective_responding = (now - ctx['hung_since']) < HUNG_GRACE_S
                else:
                    ctx['hung_since'] = None
                    effective_responding = True

                state, msg   = determine_state(
                    metrics, system_ram_percent, tracker,
                    threshold_gb=threshold_gb, is_responding=effective_responding)
                ctx['state'] = state

                # ── Render mode detection ─────────────────────────────────
                cpu = metrics['cpu_percent']
                if cpu > RENDER_CPU_THRESHOLD:
                    ctx['low_cpu_since'] = None
                    if ctx['high_cpu_since'] is None:
                        ctx['high_cpu_since'] = now
                    if not ctx['render_mode'] and (now - ctx['high_cpu_since']) >= RENDER_TRIGGER_S:
                        ctx['render_mode']  = True
                        ctx['render_start'] = ctx['high_cpu_since']
                else:
                    ctx['high_cpu_since'] = None
                    if ctx['render_mode']:
                        if ctx['low_cpu_since'] is None:
                            ctx['low_cpu_since'] = now
                        elif (now - ctx['low_cpu_since']) >= RENDER_CLEAR_S:
                            ctx['render_mode']    = False
                            ctx['render_start']   = None
                            ctx['low_cpu_since']  = None

                # ── Auto-remediation ──────────────────────────────────────
                # Skip during render — flushing working set mid-render harms performance
                auto_rem_s = float(CONFIG.get('tier1', {}).get('auto_remediation_seconds', 10.0))
                if state == WARNING and not ctx.get('render_mode', False):
                    if ctx['warning_since'] is None:
                        ctx['warning_since'] = now
                    elif now - ctx['warning_since'] >= auto_rem_s:
                        try:
                            before = proc.memory_info().rss / 1024 ** 3
                            vitals_core.empty_working_set(pid)
                            after  = proc.memory_info().rss / 1024 ** 3
                            freed  = max(before - after, 0.0)
                            if freed >= 0.05:
                                action_log.appendleft(f"[auto] flushed {freed:.1f} GB from PID {pid}")
                        except Exception:
                            pass
                        ctx['warning_since'] = now
                else:
                    ctx['warning_since'] = None

                if state in (CRITICAL, HUNG):
                    has_critical = True
                    critical_proc = proc
                    critical_ctx  = ctx

                instances_data.append({
                    'pid':             pid,
                    'title':           ctx['title'],
                    'metrics':         metrics,
                    'vram_metrics':    vram_metrics,
                    'state':           state,
                    'warning_msg':     msg,
                    'status_msg':      ctx['status_msg'],
                    'priority_locked': ctx['priority_locked'],
                    'render_mode':     ctx['render_mode'],
                    'render_start':    ctx['render_start'],
                })

            if not instances_data:
                time.sleep(interval_s)
                continue

            ui_output = render_ui(
                storage_metrics=storage_metrics,
                system_cpu=system_cpu,
                instances=instances_data,
                demoted_names=demoted_names if demoted_names else None,
                action_log=list(action_log) if action_log else None,
                session_seconds=now - session_start,
            )
            # Use full clear when critical/hung so the prompt below the box is erased
            clear_screen(full=has_critical)
            print(ui_output)

            if has_critical and critical_proc:
                critical_state = critical_ctx['state']
                choice = None
                if os.name == 'nt':
                    if critical_state == HUNG:
                        prompt = (f"{CLEAR_LINE}{RED_BLINK}HUNG PID {critical_proc.pid}!"
                                  f"  [E] Rescue (send Esc)   [K] Kill   [N] Continue: {RESET}")
                    else:
                        prompt = (f"{CLEAR_LINE}{RED_BLINK}CRITICAL PID {critical_proc.pid}!"
                                  f"  [K] Kill   [N] Continue: {RESET}")
                    print(prompt, end="", flush=True)
                    # Poll for keypress for up to interval_s — gives user time to react
                    deadline = time.time() + interval_s
                    while time.time() < deadline:
                        if msvcrt.kbhit():
                            try:
                                char = msvcrt.getch().decode('utf-8', errors='ignore').upper()
                                if char in ('Y', 'K'): choice = 'K'
                                elif char == 'E': choice = 'E'
                                elif char == 'N': choice = 'N'
                            except (UnicodeDecodeError, AttributeError):
                                pass
                            break
                        time.sleep(0.05)
                else:
                    try:
                        raw = input(f"{CLEAR_LINE}{RED_BLINK}CRITICAL PID {critical_proc.pid}! Kill? [K/N]: {RESET}").strip().upper()
                        if raw in ('Y', 'K'): choice = 'K'
                        elif raw == 'N': choice = 'N'
                    except EOFError:
                        time.sleep(2)
                        critical_ctx['tracker'] = MemoryTracker()

                if choice == 'E':
                    rescued = vitals_core.attempt_rescue(critical_proc.pid)
                    action_log.appendleft("[E] rescue signal sent" if rescued else "[E] rescue failed — no window handle")
                    time.sleep(1)
                elif choice == 'K':
                    try:
                        critical_proc.terminate()
                        action_log.appendleft(f"[K] terminated PID {critical_proc.pid}")
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                    if critical_proc.pid in active_instances:
                        del active_instances[critical_proc.pid]
                    time.sleep(2)
                    continue
                elif choice == 'N':
                    critical_ctx['tracker'] = MemoryTracker()
                    action_log.appendleft(f"[N] spike history cleared for PID {critical_proc.pid}")
            else:
                # Non-blocking key dispatch (always active when not in a critical prompt)
                if os.name == 'nt' and msvcrt.kbhit():
                    try:
                        char = msvcrt.getch().decode('utf-8', errors='ignore').upper()
                        result = _handle_key(char, active_instances, foreground_pid)
                        if result:
                            action_log.appendleft(result)
                    except KeyboardInterrupt:
                        raise
                    except Exception:
                        pass
                time.sleep(interval_s)
    finally:
        restore_all(active_instances)
        vram_monitor.stop()
        storage_monitor.stop()

def main():
    try:
        args = parse_args()
        start_monitoring(args.target, args.threshold, args.interval)
    except KeyboardInterrupt:
        restore_all()
        clear_screen(full=True)
        print(f"{CLEAR_LINE}[INFO] Monitoring terminated by user. Exiting...")
        sys.exit(0)

if __name__ == "__main__":
    main()
