import re

def render_ui_new(metrics=None, storage_metrics=None, vram_metrics=None, system_cpu=None, state='NORMAL', warning_msg="", instances=None):
    from vitals import (
        WHITE, CYAN, RESET, PRIORITY_MAP, draw_stacked_cpu_bar, draw_stacked_ram_bar,
        draw_bar, draw_stacked_vram_bar, CRITICAL, LIFE_SUPPORT, HUNG, WARNING, NORMAL,
        RED_BLINK, ORANGE, YELLOW, GREEN, CLEAR_LINE, ANSI_ESCAPE
    )
    
    WIDTH = 80
    border_line = f"{WHITE}+{'='*(WIDTH-2)}+{RESET}"
    separator_line = f"{WHITE}| {'-'*(WIDTH-4)} |{RESET}"
    
    def format_line(content, align='left'):
        vis_len = len(ANSI_ESCAPE.sub('', content))
        pad = max(0, (WIDTH - 4) - vis_len)
        if align == 'center':
            left = pad // 2
            right = pad - left
            return f"{WHITE}| {RESET}{' ' * left}{content}{' ' * right}{WHITE} |{RESET}"
        else:
            return f"{WHITE}| {RESET}{content}{' ' * pad}{WHITE} |{RESET}"
            
    lines = []
    
    # Header
    header_text = "V I T A L S   M O N I T O R"
    lines.append(border_line)
    lines.append(format_line(f"{WHITE}{header_text}{RESET}", align='center'))
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
            lines.append(format_line(f"{WHITE}{inst_header}{RESET}", align='center'))
        
        if not i_metrics:
            continue
            
        # Status Matrix
        priority_raw = i_metrics.get('priority', 'N/A')
        priority_val = PRIORITY_MAP.get(priority_raw, str(priority_raw))
        
        affinity_list = i_metrics.get('cpu_affinity')
        if isinstance(affinity_list, list):
            allowed_cores = len(affinity_list)
            total_cores = __import__('psutil').cpu_count() or 1
            affinity_val = f"{allowed_cores}/{total_cores}"
        else:
            affinity_val = 'N/A'
            
        status_matrix = f"{WHITE}[ PRIORITY: {priority_val:<12} ] [ CORES: {affinity_val:<5} ]{RESET}"
        lines.append(format_line(status_matrix, align='center'))
        
        # CPU (Stacked)
        cpu_str = draw_stacked_cpu_bar(i_metrics['cpu_percent'], system_cpu_percent=system_cpu, state=i_state)
        lines.append(format_line(cpu_str))
        
        # RAM (Stacked)
        ram_str = draw_stacked_ram_bar(i_metrics['memory_gb'], state=i_state)
        lines.append(format_line(ram_str))
        
        # System Metrics (Storage & VRAM)
        if storage_metrics or i_vram is not None or (metrics is not None and vram_metrics is None):
            lines.append(separator_line)
            
            if idx == 0 and storage_metrics:
                for drive in sorted(storage_metrics.keys()):
                    data = storage_metrics[drive]
                    lines.append(format_line(draw_bar(f"DISK {drive}", data['utilization_percent'], 100, state=NORMAL)))
            
            if i_vram is not None:
                vram_state = NORMAL
                if i_vram['total_gb'] > 0 and (i_vram['used_gb'] / i_vram['total_gb']) > 0.9:
                    vram_state = LIFE_SUPPORT # ORANGE
                lines.append(format_line(draw_stacked_vram_bar(i_vram, state=vram_state)))
            else:
                lines.append(format_line(f"{YELLOW}{'VRAM':<12} [VRAM: NVIDIA DRIVER NOT FOUND]{RESET}"))

        lines.append(separator_line)
        
        # Message Line
        if i_state == CRITICAL:
            msg_line = f"{RED_BLINK}!!! CRITICAL: SYSTEM RAM EXHAUSTED !!!{RESET}"
            detail_line = f"{RED_BLINK}{i_msg[:70]:<70}{RESET}"
        elif i_state == LIFE_SUPPORT:
            msg_line = f"{ORANGE}!!! LIFE SUPPORT: THROTTLING CORES & PRIORITY !!!{RESET}"
            detail_line = f"{ORANGE}{i_msg[:70]:<70}{RESET}"
        elif i_state == HUNG:
            msg_line = f"{RED_BLINK}!!! PROCESS HUNG (NOT RESPONDING) !!!{RESET}"
            detail_line = f"{RED_BLINK}{i_msg[:70]:<70}{RESET}"
        elif i_state == WARNING:
            msg_line = f"{YELLOW}--- WARNING: STABILIZING RESOURCES ---{RESET}"
            detail_line = f"{YELLOW}{i_msg[:70]:<70}{RESET}"
        else:
            msg_line = f"{GREEN}[ STATUS: MONITORING ACTIVE ]{RESET}"
            detail_line = ""
        
        lines.append(format_line(msg_line, align='center'))
        lines.append(format_line(detail_line, align='center'))
        
        lines.append(border_line)
        
    return "\n".join([line + CLEAR_LINE for line in lines])

def replace_in_file():
    with open('vitals.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Find where render_ui starts
    start_str = "def render_ui(metrics=None, storage_metrics=None, vram_metrics=None, system_cpu=None, state=NORMAL, warning_msg=\"\", instances=None):"
    
    # We'll regex the body out up to parse_args
    pattern = re.compile(r'def render_ui\(.*?\):\n(?:(?:    .*?\n|\n)*?)(?=def parse_args\(\):)', re.MULTILINE)
    
    new_code = """def render_ui(metrics=None, storage_metrics=None, vram_metrics=None, system_cpu=None, state=NORMAL, warning_msg="", instances=None):
    WIDTH = 80
    border_line = f"{WHITE}+{'='*(WIDTH-2)}+{RESET}"
    separator_line = f"{WHITE}| {'-'*(WIDTH-4)} |{RESET}"
    
    def format_line(content, align='left'):
        vis_len = len(ANSI_ESCAPE.sub('', content))
        pad = max(0, (WIDTH - 4) - vis_len)
        if align == 'center':
            left = pad // 2
            right = pad - left
            return f"{WHITE}| {RESET}{' ' * left}{content}{' ' * right}{WHITE} |{RESET}"
        else:
            return f"{WHITE}| {RESET}{content}{' ' * pad}{WHITE} |{RESET}"
            
    lines = []
    
    # Header
    header_text = "V I T A L S   M O N I T O R"
    lines.append(border_line)
    lines.append(format_line(f"{WHITE}{header_text}{RESET}", align='center'))
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
            
        status_matrix = f"{WHITE}[ PRIORITY: {priority_val:<12} ] [ CORES: {affinity_val:<5} ]{RESET}"
        lines.append(format_line(status_matrix, align='center'))
        
        # CPU (Stacked)
        cpu_str = draw_stacked_cpu_bar(i_metrics['cpu_percent'], system_cpu_percent=system_cpu, state=i_state)
        lines.append(format_line(cpu_str))
        
        # RAM (Stacked)
        ram_str = draw_stacked_ram_bar(i_metrics['memory_gb'], state=i_state)
        lines.append(format_line(ram_str))
        
        # System Metrics (Storage & VRAM)
        if storage_metrics or i_vram is not None or (metrics is not None and vram_metrics is None):
            lines.append(separator_line)
            
            if idx == 0 and storage_metrics:
                for drive in sorted(storage_metrics.keys()):
                    data = storage_metrics[drive]
                    lines.append(format_line(draw_bar(f"DISK {drive}", data['utilization_percent'], 100, state=NORMAL)))
            
            if i_vram is not None:
                vram_state = NORMAL
                if i_vram['total_gb'] > 0 and (i_vram['used_gb'] / i_vram['total_gb']) > 0.9:
                    vram_state = LIFE_SUPPORT # ORANGE
                lines.append(format_line(draw_stacked_vram_bar(i_vram, state=vram_state)))
            else:
                lines.append(format_line(f"{YELLOW}{'VRAM':<12} [VRAM: NVIDIA DRIVER NOT FOUND]{RESET}"))

        lines.append(separator_line)
        
        # Message Line
        if i_state == CRITICAL:
            msg_line = f"{RED_BLINK}!!! CRITICAL: SYSTEM RAM EXHAUSTED !!!{RESET}"
            detail_line = f"{RED_BLINK}{i_msg[:70]:<70}{RESET}"
        elif i_state == LIFE_SUPPORT:
            msg_line = f"{ORANGE}!!! LIFE SUPPORT: THROTTLING CORES & PRIORITY !!!{RESET}"
            detail_line = f"{ORANGE}{i_msg[:70]:<70}{RESET}"
        elif i_state == HUNG:
            msg_line = f"{RED_BLINK}!!! PROCESS HUNG (NOT RESPONDING) !!!{RESET}"
            detail_line = f"{RED_BLINK}{i_msg[:70]:<70}{RESET}"
        elif i_state == WARNING:
            msg_line = f"{YELLOW}--- WARNING: STABILIZING RESOURCES ---{RESET}"
            detail_line = f"{YELLOW}{i_msg[:70]:<70}{RESET}"
        else:
            msg_line = f"{GREEN}[ STATUS: MONITORING ACTIVE ]{RESET}"
            detail_line = ""
        
        lines.append(format_line(msg_line, align='center'))
        if detail_line:
            lines.append(format_line(detail_line, align='center'))
        else:
            lines.append(format_line("", align='center'))
        
        lines.append(border_line)
        
    return "\\n".join([line + CLEAR_LINE for line in lines])
"""
    
    new_content = pattern.sub(new_code, content)
    with open('vitals.py', 'w', encoding='utf-8') as f:
        f.write(new_content)

if __name__ == '__main__':
    replace_in_file()
