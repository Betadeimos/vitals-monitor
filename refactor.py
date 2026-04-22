import sys
import re

with open('vitals.py', 'r', encoding='utf-8') as f:
    content = f.read()

# We can find `def render_ui(...)` and `def parse_args():` to extract the function body.
pattern_render = re.compile(r'def render_ui\(.*?\):\n(?:(?:    .*?\n|\n)*?)(?=def parse_args\(\):)', re.MULTILINE)

new_render_ui = '''def render_ui(metrics=None, storage_metrics=None, vram_metrics=None, system_cpu=None, state=NORMAL, warning_msg="", instances=None):
    lines = []
    border_line = f"{CYAN}{'='*60}{RESET}"
    
    # Header
    header_text = "V I T A L S   M O N I T O R"
    lines.append(border_line)
    lines.append(f"{CYAN}{header_text:^60}{RESET}")
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

        if i_pid is not None:
            title_str = f" [{i_title}]" if i_title else ""
            inst_header = f"INSTANCE: PID {i_pid}{title_str}"
            lines.append(f"{CYAN}{inst_header:^60}{RESET}")
        
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
        padding_matrix = max(0, (60 - len(status_matrix.replace(CYAN, "").replace(RESET, ""))) // 2)
        lines.append(f"{' ' * padding_matrix}{status_matrix}")
        
        # CPU (Stacked)
        cpu_str = draw_stacked_cpu_bar(i_metrics['cpu_percent'], system_cpu_percent=system_cpu, state=i_state)
        lines.append(cpu_str)
        
        # RAM (Stacked)
        ram_str = draw_stacked_ram_bar(i_metrics['memory_gb'], state=i_state)
        lines.append(ram_str)
        
        # System Metrics (Storage & VRAM)
        if storage_metrics or i_vram is not None or (metrics is not None and vram_metrics is None):
            lines.append(f"{CYAN}{'-' * 60}{RESET}")
            
            if idx == 0 and storage_metrics:
                for drive in sorted(storage_metrics.keys()):
                    data = storage_metrics[drive]
                    lines.append(draw_bar(f"DISK {drive}", data['utilization_percent'], 100, state=NORMAL))
            
            if i_vram is not None:
                vram_state = NORMAL
                if i_vram['total_gb'] > 0 and (i_vram['used_gb'] / i_vram['total_gb']) > 0.9:
                    vram_state = LIFE_SUPPORT # ORANGE
                lines.append(draw_stacked_vram_bar(i_vram, state=vram_state))
            else:
                lines.append(f"{YELLOW}{'VRAM':<12} [VRAM: NVIDIA DRIVER NOT FOUND]{RESET}")

        lines.append(f"{CYAN}{'-' * 60}{RESET}")
        
        # Message Line
        if i_state == CRITICAL:
            msg_line = f"{RED_BLINK}!!! CRITICAL: SYSTEM RAM EXHAUSTED !!!{RESET}"
            detail_line = f"{RED_BLINK}{i_msg[:60]:<60}{RESET}"
        elif i_state == LIFE_SUPPORT:
            msg_line = f"{ORANGE}!!! LIFE SUPPORT: THROTTLING CORES & PRIORITY !!!{RESET}"
            detail_line = f"{ORANGE}{i_msg[:60]:<60}{RESET}"
        elif i_state == HUNG:
            msg_line = f"{RED_BLINK}!!! PROCESS HUNG (NOT RESPONDING) !!!{RESET}"
            detail_line = f"{RED_BLINK}{i_msg[:60]:<60}{RESET}"
        elif i_state == WARNING:
            msg_line = f"{YELLOW}--- WARNING: STABILIZING RESOURCES ---{RESET}"
            detail_line = f"{YELLOW}{i_msg[:60]:<60}{RESET}"
        else:
            msg_line = f"{GREEN}[ STATUS: MONITORING ACTIVE ]{RESET}"
            detail_line = ""
        
        lines.append(f"{msg_line:^60}")
        lines.append(f"{detail_line:^60}")
        
        lines.append(border_line)
        
    return "\\n".join([line + CLEAR_LINE for line in lines])

'''

content = pattern_render.sub(new_render_ui, content)


pattern_start = re.compile(r'def start_monitoring\(.*?\):\n(?:(?:    .*?\n|\n)*?)(?=def main\(\):)', re.MULTILINE)

new_start_monitoring = '''def start_monitoring(target_script_name="max_simulator", threshold_gb=None, interval_s=None):
    if threshold_gb is None:
        threshold_gb = CONFIG["tier1"]["ram_spike_threshold_gb"]
    if interval_s is None:
        interval_s = CONFIG["monitoring"]["refresh_interval_seconds"]

    # Clear screen initially
    clear_screen(full=True)
    print(f"{CLEAR_LINE}{CYAN}Starting Vitals Watchdog. Searching for '{target_script_name}'...{RESET}")
    
    active_instances = {} # pid -> dict
    
    try:
        while True:
            # 1. Scan for new instances
            current_procs = vitals_core.find_processes(target_script_name)
            for proc in current_procs:
                if proc.pid not in active_instances:
                    vram_monitor = VRAMMonitor()
                    vram_monitor.set_target_pid(proc.pid)
                    active_instances[proc.pid] = {
                        'proc': proc,
                        'tracker': MemoryTracker(),
                        'state': NORMAL,
                        'ls_context': {'affinity': None, 'priority': None},
                        'vram_monitor': vram_monitor,
                        'title': vitals_core.get_window_title(proc.pid)
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
                print(f"{CLEAR_LINE}{CYAN}'{target_script_name}' not found. Waiting...{RESET}")
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
                    apply_life_support(proc, ls_context)
                elif current_state == LIFE_SUPPORT and state != LIFE_SUPPORT:
                    restore_life_support(proc, ls_context)

                # Update priority if state changed
                set_priority(proc, state, current_state)
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
                    'warning_msg': msg
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
                        print(f"\\n{CLEAR_LINE}{GREEN}Process {critical_proc.pid} terminated.{RESET}")
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                    critical_ctx['vram_monitor'].stop()
                    if critical_proc.pid in active_instances:
                        del active_instances[critical_proc.pid]
                    time.sleep(2)
                    continue
                elif choice == 'N':
                    print(f"\\n{CLEAR_LINE}{CYAN}Resuming monitoring. Spike history cleared for PID {critical_proc.pid}.{RESET}")
                    critical_ctx['tracker'] = MemoryTracker()
            else:
                # Ensure the line below the UI is clear when not in CRITICAL
                print(f"{CLEAR_LINE}", end="", flush=True)
                
            time.sleep(interval_s)
    finally:
        for ctx in active_instances.values():
            ctx['vram_monitor'].stop()

'''

content = pattern_start.sub(new_start_monitoring, content)

with open('vitals.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Replaced!")
