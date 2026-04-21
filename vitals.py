import os
import sys
import time
import argparse
from collections import deque
import psutil
import vitals_core

class MemoryTracker:
    def __init__(self, window_size_seconds=5):
        self.window_size_seconds = window_size_seconds
        self.readings = deque()

    def add_reading(self, memory_gb, timestamp=None):
        if timestamp is None:
            timestamp = time.time()
        self.readings.append((timestamp, memory_gb))
        
        # Evict old readings - keep enough for the largest window (5s)
        while self.readings and self.readings[0][0] < timestamp - self.window_size_seconds:
            self.readings.popleft()

    def check_threshold(self, threshold_gb, window_seconds, current_time=None):
        if len(self.readings) < 2:
            return False
        
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
        # Kept for backward compatibility if needed, but we'll use check_threshold
        return self.check_threshold(threshold_gb, self.window_size_seconds)

# ANSI Escape Codes
RESET = "\033[0m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
ORANGE = "\033[38;5;208m"
WHITE = "\033[37m"
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

def determine_state(metrics, system_ram_percent, tracker, threshold_gb=0.1, is_responding=True):
    """
    Tier 1 (Warning): Triggered by sudden memory spikes (>0.1GB in 2s) OR high CPU (>80%).
    Tier 2 (Critical): Triggered ONLY when total system RAM > 90% capacity.
    Tier 3 (Life Support): Triggered if the process is not responding to Windows messages.
    """
    if not is_responding:
        return LIFE_SUPPORT, "Process is NOT RESPONDING (Hung)"

    if system_ram_percent > 90.0:
        return CRITICAL, f"System RAM > 90% ({system_ram_percent:.1f}%)"
    
    is_spike = tracker.check_threshold(threshold_gb, window_seconds=2)
    is_high_cpu = metrics['cpu_percent'] > 80.0
    
    if is_spike or is_high_cpu:
        reasons = []
        if is_spike: reasons.append(f"Memory spike detected (>{threshold_gb}GB in 2s)")
        if is_high_cpu: reasons.append(f"High CPU usage ({metrics['cpu_percent']:.1f}%)")
        return WARNING, " | ".join(reasons)
    
    return NORMAL, ""

def set_priority(proc, new_state, current_state=None):
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
            print(f"{CLEAR_LINE}{YELLOW}[INFO] Throttling process priority for stability...{RESET}")
            time.sleep(1) # Give user a moment to see the message
        elif new_state == NORMAL and current_state == WARNING:
            if os.name == 'nt':
                # Windows: NORMAL_PRIORITY_CLASS
                proc.nice(psutil.NORMAL_PRIORITY_CLASS)
            else:
                # Unix: 0 is normal priority
                proc.nice(0)
            print(f"{CLEAR_LINE}{CYAN}[INFO] Restoring process priority.{RESET}")
            time.sleep(1)
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        # Gracefully handle if we can't change priority
        pass

def apply_life_support(proc, saved_context):
    """
    Saves current process affinity and priority, then throttles them.
    """
    if saved_context.get('affinity') is not None:
        return # Already applied
    
    try:
        # Save current state
        saved_context['affinity'] = proc.cpu_affinity()
        saved_context['priority'] = proc.nice()
        
        # Throttling
        print(f"{CLEAR_LINE}{ORANGE}[LIFE SUPPORT] Throttling cores & priority...{RESET}")
        
        # Affinity: exclude cores 0 and 1 if possible
        all_cores = list(range(psutil.cpu_count()))
        new_affinity = [c for c in all_cores if c not in (0, 1)]
        
        if not new_affinity:
            # Fallback if only 1 or 2 cores exist
            new_affinity = [all_cores[-1]]
            
        proc.cpu_affinity(new_affinity)
        
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

def restore_life_support(proc, saved_context):
    """
    Restores original process affinity and priority.
    """
    if saved_context.get('affinity') is None:
        return
        
    try:
        print(f"{CLEAR_LINE}{CYAN}[LIFE SUPPORT] Restoring original affinity & priority.{RESET}")
        proc.cpu_affinity(saved_context['affinity'])
        proc.nice(saved_context['priority'])
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass
    finally:
        saved_context['affinity'] = None
        saved_context['priority'] = None

def draw_bar(label, value, max_value, bar_length=40, char='#', state=NORMAL):
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
    
    label_str = f"{CYAN}{label:<12}{RESET}"
    bar_str = char * filled_length + '-' * (bar_length - filled_length)
    colored_bar = f"{color}{bar_str}{RESET}"
    border_open = f"{CYAN}[{RESET}"
    border_close = f"{CYAN}]{RESET}"
    
    return f"{label_str} {border_open}{colored_bar}{border_close} {value:.2f} / {max_value:.1f} GB"

def draw_stacked_ram_bar(target_gb, state=NORMAL):
    bar_length = 40
    vm = psutil.virtual_memory()
    total_gb = vm.total / (1024 ** 3)
    used_gb = vm.used / (1024 ** 3)
    
    # Other Apps RAM = Total System Used - Target Process RAM
    other_gb = max(used_gb - target_gb, 0.0)
    
    other_ratio = other_gb / total_gb
    target_ratio = target_gb / total_gb
    
    other_chars = int(bar_length * other_ratio)
    target_chars = int(bar_length * target_ratio)
    free_chars = max(bar_length - other_chars - target_chars, 0)
    
    # Ensure the bar is exactly bar_length
    if (other_chars + target_chars + free_chars) < bar_length:
        free_chars += (bar_length - (other_chars + target_chars + free_chars))
    elif (other_chars + target_chars + free_chars) > bar_length:
        if other_chars > 0: other_chars -= 1
        elif target_chars > 0: target_chars -= 1

    if state in (CRITICAL, HUNG):
        target_color = RED_BLINK
    elif state == LIFE_SUPPORT:
        target_color = ORANGE
    elif state == WARNING:
        target_color = YELLOW
    else:
        target_color = GREEN
        
    # Other Apps: '.' (White-ish), Target: '#' (State Color), Free: '-'
    other_bar = "." * other_chars
    target_bar = f"{target_color}{'#' * target_chars}{RESET}"
    free_bar = "-" * free_chars
    
    label_str = f"{target_color}{'RAM':<12}{RESET}"
    border_open = f"{CYAN}[{RESET}"
    border_close = f"{CYAN}]{RESET}"
    
    return f"{label_str} {border_open}{other_bar}{target_bar}{free_bar}{border_close} {target_gb:.2f} GB"

def draw_stacked_cpu_bar(target_cpu_percent, state=NORMAL):
    bar_length = 40
    total_system_cpu = psutil.cpu_percent()
    
    # Other Apps CPU = Total System CPU - Target Process CPU
    other_cpu = max(total_system_cpu - target_cpu_percent, 0.0)
    
    # ratios are based on 100.0%
    other_ratio = other_cpu / 100.0
    target_ratio = target_cpu_percent / 100.0
    
    other_chars = int(round(bar_length * other_ratio))
    target_chars = int(round(bar_length * target_ratio))
    
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
        
    # Other Apps: '.' (White-ish), Target: '#' (State Color), Idle: '-'
    other_bar = "." * other_chars
    target_bar = f"{target_color}{'#' * target_chars}{RESET}"
    idle_bar = "-" * idle_chars
    
    label_str = f"{target_color}{'CPU':<12}{RESET}"
    border_open = f"{CYAN}[{RESET}"
    border_close = f"{CYAN}]{RESET}"
    
    return f"{label_str} {border_open}{other_bar}{target_bar}{idle_bar}{border_close} {target_cpu_percent:.2f}%"

def render_ui(metrics, storage_metrics=None, vram_metrics=None, state=NORMAL, warning_msg=""):
    lines = []
    border_line = f"{CYAN}{'='*60}{RESET}"
    
    # Header
    header_text = "V I T A L S   M O N I T O R"
    lines.append(border_line)
    lines.append(f"{CYAN}{header_text:^60}{RESET}")
    lines.append(border_line)
    
    # Status Matrix
    priority_raw = metrics.get('priority', 'N/A')
    priority_val = PRIORITY_MAP.get(priority_raw, str(priority_raw))
    
    affinity_list = metrics.get('cpu_affinity')
    if isinstance(affinity_list, list):
        allowed_cores = len(affinity_list)
        total_cores = psutil.cpu_count()
        affinity_val = f"{allowed_cores}/{total_cores}"
    else:
        affinity_val = 'N/A'
        
    status_matrix = f"{CYAN}[ PRIORITY: {priority_val:<12} ] [ CORES: {affinity_val:<5} ]{RESET}"
    padding_matrix = max(0, (60 - len(status_matrix.replace(CYAN, "").replace(RESET, ""))) // 2)
    lines.append(f"{' ' * padding_matrix}{status_matrix}")
    
    # CPU (Stacked)
    cpu_str = draw_stacked_cpu_bar(metrics['cpu_percent'], state=state)
    lines.append(cpu_str)
    
    # RAM (Stacked)
    ram_str = draw_stacked_ram_bar(metrics['memory_gb'], state=state)
    lines.append(ram_str)
    
    # System Metrics (Storage & VRAM)
    if storage_metrics or vram_metrics is not None:
        lines.append(f"{CYAN}{'-' * 60}{RESET}")
        
        if storage_metrics:
            for drive in sorted(storage_metrics.keys()):
                data = storage_metrics[drive]
                lines.append(draw_bar(f"DISK {drive}", data['used_gb'], data['total_gb'], state=NORMAL))
        
        if vram_metrics:
            vram_state = NORMAL
            if vram_metrics['total_gb'] > 0 and (vram_metrics['used_gb'] / vram_metrics['total_gb']) > 0.9:
                vram_state = LIFE_SUPPORT # ORANGE
            lines.append(draw_bar("VRAM [GPU]", vram_metrics['used_gb'], vram_metrics['total_gb'], state=vram_state))
        else:
            lines.append(f"{YELLOW}[VRAM: NVIDIA DRIVER NOT FOUND]{RESET}")

    lines.append(f"{CYAN}{'-' * 60}{RESET}")
    
    if state == CRITICAL:
        lines.append(f"{RED_BLINK}!!! CRITICAL: SYSTEM RAM EXHAUSTED !!!{RESET}")
        lines.append(f"{RED_BLINK}{warning_msg}{RESET}")
    elif state == LIFE_SUPPORT:
        lines.append(f"{ORANGE}!!! LIFE SUPPORT: THROTTLING CORES & PRIORITY !!!{RESET}")
        lines.append(f"{ORANGE}{warning_msg}{RESET}")
    elif state == HUNG:
        lines.append(f"{RED_BLINK}!!! PROCESS HUNG (NOT RESPONDING) !!!{RESET}")
        lines.append(f"{RED_BLINK}{warning_msg}{RESET}")
    elif state == WARNING:
        lines.append(f"{YELLOW}--- WARNING: STABILIZING RESOURCES ---{RESET}")
        lines.append(f"{YELLOW}{warning_msg}{RESET}")
    else:
        lines.append(f"{GREEN}Status: Normal{RESET}")
        lines.append("") # Consistent height padding
    
    lines.append(border_line)
        
    return "\n".join([line + CLEAR_LINE for line in lines])

def parse_args():
    parser = argparse.ArgumentParser(
        description=f"{CYAN}V I T A L S   W A T C H D O G\nReal-time resource monitor and crash predictor.{RESET}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"{CYAN}Usage Examples:\n  python vitals.py\n  python vitals.py 3dsmax --threshold 0.25\n  python vitals.py my_app -t 0.1 -i 1.0{RESET}"
    )
    parser.add_argument('target', nargs='?', default='max_simulator', 
                        help='Target process name to monitor (default: max_simulator)')
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

def start_monitoring(target_script_name="max_simulator", threshold_gb=0.10, interval_s=0.5):
    # Clear screen initially
    clear_screen(full=True)
    print(f"{CLEAR_LINE}{CYAN}Starting Vitals Watchdog. Searching for '{target_script_name}'...{RESET}")
    
    proc = None
    tracker = MemoryTracker(window_size_seconds=5)
    current_state = NORMAL
    ls_context = {'affinity': None, 'priority': None}
    
    TIER1_THRESHOLD_GB = threshold_gb # Warning
    TIER1_WINDOW_S = 2
    TIER2_THRESHOLD_GB = threshold_gb * 2.5 # Critical (scaled relative to warning)
    TIER2_WINDOW_S = 5
    
    while True:
        if proc is None:
            proc = vitals_core.find_process(target_script_name)
            if proc:
                clear_screen(full=True)
                print(f"{CLEAR_LINE}{GREEN}Found process! Locking onto PID: {proc.pid}{RESET}")
                ls_context = {'affinity': None, 'priority': None} # Reset context for new process
            else:
                clear_screen(full=True)
                print(f"{CLEAR_LINE}{CYAN}'{target_script_name}' not found. Waiting...{RESET}")
                time.sleep(1)
                continue
        
        metrics = vitals_core.get_process_metrics(proc)
        if metrics:
            tracker.add_reading(metrics['memory_gb'])
            
            is_responding = vitals_core.is_process_responding(proc.pid)
            system_ram_percent = psutil.virtual_memory().percent
            state, msg = determine_state(metrics, system_ram_percent, tracker, threshold_gb=threshold_gb, is_responding=is_responding)
            
            # Life Support handling
            if state == LIFE_SUPPORT:
                apply_life_support(proc, ls_context)
            elif current_state == LIFE_SUPPORT and state != LIFE_SUPPORT:
                restore_life_support(proc, ls_context)

            # Update priority if state changed (for WARNING/NORMAL)
            set_priority(proc, state, current_state)
            current_state = state

            storage_metrics = vitals_core.get_storage_metrics()
            vram_metrics = vitals_core.get_vram_metrics()
            ui_output = render_ui(metrics, storage_metrics=storage_metrics, vram_metrics=vram_metrics, state=state, warning_msg=msg)
            clear_screen()
            print(ui_output)
            
            if state == CRITICAL:
                # Prompt for kill
                try:
                    choice = input(f"{CLEAR_LINE}{RED_BLINK}CRITICAL! Forcefully kill target process? [Y/N]: {RESET}").strip().upper()
                    if choice == 'Y':
                        proc.terminate()
                        print(f"{CLEAR_LINE}{GREEN}Process {proc.pid} terminated.{RESET}")
                        proc = None
                        tracker = MemoryTracker(window_size_seconds=5)
                        ls_context = {'affinity': None, 'priority': None}
                        time.sleep(2)
                        continue
                    else:
                        print(f"{CLEAR_LINE}{CYAN}Resuming monitoring. Spike history cleared.{RESET}")
                        tracker = MemoryTracker(window_size_seconds=5) 
                except EOFError:
                    # Handle non-interactive environments
                    print(f"{CLEAR_LINE}{RED_BLINK}Non-interactive environment detected. Cannot prompt for kill.{RESET}")
                    time.sleep(2)
                    tracker = MemoryTracker(window_size_seconds=5)
            
        else:
            clear_screen(full=True)
            print(f"{CLEAR_LINE}{RED_BLINK}Process lost! Searching again...{RESET}")
            proc = None
            tracker = MemoryTracker(window_size_seconds=5) 
            ls_context = {'affinity': None, 'priority': None}
        
        time.sleep(interval_s)

def main():
    try:
        if len(sys.argv) == 1:
            target, threshold, interval = interactive_wizard()
            if target:
                start_monitoring(target, threshold, interval)
        else:
            args = parse_args()
            start_monitoring(args.target, args.threshold, args.interval)
    except KeyboardInterrupt:
        clear_screen(full=True)
        print(f"{CLEAR_LINE}[INFO] Monitoring terminated by user. Exiting...")
        sys.exit(0)


def interactive_wizard():
    """
    Scans for processes containing '3dsmax' or 'max_simulator' and prompts user for configuration.
    """
    clear_screen(full=True)
    print(f"{CLEAR_LINE}{CYAN}{'='*60}")
    print(f"{CLEAR_LINE}{'V I T A L S   I N T E R A C T I V E   W I Z A R D':^60}")
    print(f"{CLEAR_LINE}{'='*60}{RESET}\n")


    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            name = proc.info.get('name', '').lower()
            cmdline = proc.info.get('cmdline', [])
            
            # Check by process name directly first
            if '3dsmax' in name or 'max_simulator' in name:
                processes.append(proc.info)
            # Check if it's a python process and if the target script is in its cmdline
            elif 'python' in name and cmdline:
                if any('3dsmax' in arg.lower() or 'max_simulator' in arg.lower() for arg in cmdline):
                    # For python processes, use the script name for display if possible
                    # We'll just use the first argument that matches
                    for arg in cmdline:
                        if '3dsmax' in arg.lower() or 'max_simulator' in arg.lower():
                            proc.info['name'] = os.path.basename(arg)
                            break
                    processes.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not processes:
        print(f"{CLEAR_LINE}{YELLOW}[!] No matching processes found (3dsmax or max_simulator).{RESET}")
        return None, None, None

    if len(processes) == 1:
        proc = processes[0]
        print(f"{CLEAR_LINE}{CYAN}[INFO] Only one instance found: {proc['name']} (PID: {proc['pid']}). Auto-selecting...{RESET}")
        target_name = proc['name']
    else:
        print(f"{CLEAR_LINE}{GREEN}Found the following processes:{RESET}")
        for i, proc in enumerate(processes, 1):
            print(f"{CLEAR_LINE}  {CYAN}{i}.{RESET} {proc['name']} (PID: {proc['pid']})")
        
        print(f"{CLEAR_LINE}")
        try:
            selection = input(f"{CLEAR_LINE}{GREEN}Select process number: {RESET}").strip()
            if not selection:
                print(f"{CLEAR_LINE}{YELLOW}No selection made. Exiting.{RESET}")
                return None, None, None
            
            idx = int(selection) - 1
            if idx < 0 or idx >= len(processes):
                print(f"{CLEAR_LINE}{RED_BLINK}Invalid selection.{RESET}")
                return None, None, None
                
            target_name = processes[idx]['name']
        except (ValueError, KeyboardInterrupt, EOFError):
            print(f"{CLEAR_LINE}\n{YELLOW}Wizard cancelled or invalid input.{RESET}")
            return None, None, None

    try:
        threshold_input = input(f"{CLEAR_LINE}{GREEN}Memory threshold (GB) [Default 0.10]: {RESET}").strip()
        threshold = float(threshold_input) if threshold_input else 0.10
        
        interval_input = input(f"{CLEAR_LINE}{GREEN}Refresh interval (sec) [Default 0.5]: {RESET}").strip()
        interval = float(interval_input) if interval_input else 0.5
        
        return target_name, threshold, interval
        
    except (ValueError, KeyboardInterrupt, EOFError):
        print(f"{CLEAR_LINE}\n{YELLOW}Wizard cancelled or invalid input.{RESET}")
        return None, None, None

if __name__ == "__main__":
    main()
