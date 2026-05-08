import unittest
import os
import sys
from unittest.mock import patch

# Add the root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from vitals import draw_bar, draw_stacked_ram_bar, draw_stacked_cpu_bar, render_ui, clear_screen

class TestVitalsUI(unittest.TestCase):
    def setUp(self):
        self.RESET = "\033[0m"
        self.CYAN = "\033[36m"
        self.GREEN = "\033[32m"
        self.YELLOW = "\033[33m"
        self.ORANGE = "\033[38;5;208m"
        self.RED = "\033[31m"
        self.RED_BLINK = "\033[1;31m"

    def test_get_usage_color(self):
        from vitals import get_usage_color
        self.assertEqual(get_usage_color(0), self.GREEN)
        self.assertEqual(get_usage_color(50), self.GREEN)
        self.assertEqual(get_usage_color(51), self.YELLOW)
        self.assertEqual(get_usage_color(75), self.YELLOW)
        self.assertEqual(get_usage_color(76), self.ORANGE)
        self.assertEqual(get_usage_color(90), self.ORANGE)
        self.assertEqual(get_usage_color(91), self.RED_BLINK)

    def test_draw_shared_vram_bar(self):
        from vitals import draw_shared_vram_bar
        # 0 GB -> GREEN label
        output_0 = draw_shared_vram_bar(0.0)
        self.assertIn(self.GREEN + "SHARED GPU", output_0)
        self.assertIn(self.GREEN + "-" * 40, output_0)
        
        # > 0 GB -> RED label
        output_1 = draw_shared_vram_bar(0.5)
        self.assertIn(self.RED + "SHARED GPU", output_1)
        # 0.5 GB should show 1 block (int(0.5 * 2) = 1)
        self.assertIn(self.RED + "■" + "-" * 39, output_1)

    def test_dynamic_label_colors(self):
        from vitals import draw_bar, draw_stacked_ram_bar, draw_stacked_cpu_bar, draw_stacked_vram_bar
        # CPU 95% -> RED_BLINK label
        with patch('psutil.cpu_percent', return_value=95.0):
            output = draw_stacked_cpu_bar(10.0)
            self.assertIn(self.RED_BLINK + "CPU", output)
            
        # RAM 60% -> YELLOW label
        with patch('psutil.virtual_memory') as mock_vm:
            mock_vm.return_value.total = 100
            mock_vm.return_value.used = 60
            output = draw_stacked_ram_bar(10.0)
            self.assertIn(self.YELLOW + "RAM", output)
            
        # DISK 80% -> ORANGE label
        output = draw_bar("DISK C", 80, 100)
        self.assertIn(self.ORANGE + "DISK C", output)

    def test_render_ui_cyan_borders(self):
        from vitals import NORMAL
        metrics = {'cpu_percent': 10.0, 'memory_gb': 1.0}
        output = render_ui(metrics, state=NORMAL)
        # Every line should have CYAN | or CYAN +
        lines = output.split('\n')
        found_cyan = False
        for line in lines:
            if not line.strip(): continue
            if self.CYAN in line:
                found_cyan = True
            if '|' in line:
                self.assertIn(self.CYAN + "|", line)
            if '+' in line:
                self.assertIn(self.CYAN + "+", line)
        self.assertTrue(found_cyan)

    def test_render_ui_shared_gpu_line(self):
        """Shared GPU spillage appears in the unified GPU bar, not a separate bar."""
        from vitals import NORMAL
        metrics = {'cpu_percent': 10.0, 'memory_gb': 1.0}
        vram_metrics = {
            'used_gb': 2.0,
            'total_gb': 8.0,
            'shared_used_gb': 0.5
        }
        output = render_ui(metrics, vram_metrics=vram_metrics, state=NORMAL)
        # Unified bar is present
        self.assertIn("VRAM [GPU]", output)
        # Shared annotation shown in suffix
        self.assertIn("+0.5GB", output)
        # Overflow warning line still fires
        self.assertIn("!!! GPU MEMORY OVERFLOW INTO SYSTEM RAM !!!", output)
        self.assertIn(self.RED_BLINK, output)
        # Old separate bar no longer rendered
        self.assertNotIn("SHARED GPU", output)

    @patch('os.system')
    @patch('sys.stdout.write')
    def test_clear_screen_uses_ansi(self, mock_write, mock_os_system):
        # We need to ensure sys.stdout.isatty() returns True for the test
        with patch('sys.stdout.isatty', return_value=True):
            clear_screen()
            
            # Verify os.system was NOT called
            mock_os_system.assert_not_called()
            
            # Verify ANSI code was written to stdout. 
            # It should use \033[H to move cursor to top-left.
            # We also check for \033[J if we decide to use it for initial clear,
            # but for the main loop move_cursor is preferred.
            
            # Since I'll be renaming/refactoring, I'll expect \033[H for now.
            calls = [call[0][0] for call in mock_write.call_args_list]
            self.assertTrue(any("\033[H" in call for call in calls), f"ANSI escape code \\033[H not found in stdout writes: {calls}")

    def test_draw_bar_normal(self):
        # Normal status: Green bar, Cyan borders
        from vitals import NORMAL
        output = draw_bar("CPU", 50, 100, bar_length=10, char='|', state=NORMAL)
        self.assertIn(self.CYAN + "[", output)
        self.assertIn("]" + self.RESET, output)
        self.assertIn(self.GREEN + "|||||-----", output)
        self.assertIn("CPU", output)
        self.assertIn(self.GREEN, output)

    def test_draw_bar_warning(self):
        # Warning status: Yellow bar, Cyan borders
        from vitals import WARNING
        output = draw_bar("CPU", 50, 100, bar_length=10, char='|', state=WARNING)
        self.assertIn(self.YELLOW + "|||||-----", output)
        self.assertIn(self.YELLOW, output)

    def test_draw_bar_critical(self):
        # Critical status: Red Blink bar, Cyan borders
        from vitals import CRITICAL
        output = draw_bar("RAM", 5000, 8192, bar_length=10, char='■', state=CRITICAL)
        self.assertIn(self.CYAN + "[", output)
        self.assertIn("]" + self.RESET, output)
        self.assertIn(self.RED_BLINK + "■■■■■■----", output)
        self.assertIn("RAM", output)
        self.assertIn(self.RED_BLINK, output)

    def test_render_ui_normal(self):
        from vitals import NORMAL
        metrics = {'cpu_percent': 10.0, 'memory_gb': 1.0}
        output = render_ui(metrics, state=NORMAL)

        # Check for borders
        self.assertIn(self.CYAN, output)
        # Check for normal status
        self.assertIn("[ ~ ]  monitoring active", output)
        # Should not have spike warning
        self.assertNotIn("!!! CRITICAL: RUNAWAY MEMORY LEAK !!!", output)

    def test_render_ui_warning(self):
        from vitals import WARNING
        metrics = {'cpu_percent': 10.0, 'memory_gb': 2.0}
        # Pass a message that contains the RAM spike trigger phrase
        output = render_ui(metrics, state=WARNING, warning_msg="Memory spike detected (>0.1GB in 2.0s)")

        # Honest message: no "STABILIZING" claim
        self.assertNotIn("STABILIZING RESOURCES", output)
        # Trigger-derived label present
        self.assertIn(self.YELLOW + "[ ! ] WARNING:", output)
        self.assertIn("RAM spike", output)
        self.assertIn(self.YELLOW, output)

    def test_render_ui_critical(self):
        from vitals import CRITICAL
        metrics = {'cpu_percent': 10.0, 'memory_gb': 2.0}
        output = render_ui(metrics, state=CRITICAL, warning_msg="Runaway leak!")
        
        # Check for critical warning in bold red
        self.assertIn(self.RED_BLINK + "[ x ]  CRITICAL: system RAM exhausted", output)
        self.assertIn(self.RED_BLINK, output)

    def test_render_ui_dynamic_cores(self):
        from vitals import NORMAL
        # Mock 16 cores system
        with patch('psutil.cpu_count', return_value=16):
            metrics = {
                'cpu_percent': 10.0, 
                'memory_gb': 1.0, 
                'priority': 32, 
                'cpu_affinity': [2, 3] # Using 2 cores
            }
            output = render_ui(metrics, state=NORMAL)
            self.assertIn("cores  2/16", output)

            # Change affinity to 4 cores
            metrics['cpu_affinity'] = [0, 1, 2, 3]
            output = render_ui(metrics, state=NORMAL)
            self.assertIn("cores  4/16", output)

    def test_render_ui_ghosting_fix(self):
        """Verify that every line ends with the ANSI clear-line code \033[K."""
        from vitals import NORMAL
        metrics = {'cpu_percent': 10.0, 'memory_gb': 1.0}
        output = render_ui(metrics, state=NORMAL)
        
        lines = output.split('\n')
        clear_line_code = "\033[K"
        for i, line in enumerate(lines):
            self.assertTrue(line.endswith(clear_line_code), f"Line {i} does not end with {clear_line_code!r}: {line!r}")

    def strip_ansi(self, text):
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    def test_ui_alignment(self):
        """Verify that all labels are 12 chars and [ is at same index."""
        from vitals import NORMAL
        metrics = {
            'cpu_percent': 10.0,
            'memory_gb': 1.5,
            'priority': 32,
            'cpu_affinity': [0, 1]
        }
        storage_metrics = {
            'C': {'utilization_percent': 20.0}
        }
        vram_metrics = {
            'used_gb': 2.0,
            'total_gb': 8.0
        }
        output = render_ui(
            metrics, 
            storage_metrics=storage_metrics, 
            vram_metrics=vram_metrics, 
            state=NORMAL
        )
        
        lines = output.split('\n')
        # Filter for lines that contain a bar (indicated by '[')
        bar_lines = [line for line in lines if '[' in line and ']' in line and ('CPU' in line or 'RAM' in line or 'DISK' in line or 'VRAM' in line)]
        
        self.assertTrue(len(bar_lines) >= 4, f"Expected at least 4 bar lines, found {len(bar_lines)}")
        
        for line in bar_lines:
            plain_line = self.strip_ansi(line)
            # Find the bracket that starts the bar.
            # It should be at index 15 because border is 2 chars, label is 12 chars + 1 space.
            idx = 15
            self.assertEqual(plain_line[idx], '[', f"Line '{plain_line}' does not have '[' at index {idx}")
            
            # Verify the label part is 12 chars
            label_part = plain_line[2:14]
            self.assertEqual(len(label_part), 12, f"Label part '{label_part}' is not 12 chars")

    def test_simplified_borders(self):
        """Verify header border has VITALS title; bottom border is solid = line."""
        from vitals import NORMAL
        metrics = {'cpu_percent': 10.0, 'memory_gb': 1.0}
        output = render_ui(metrics, state=NORMAL)
        lines = output.split('\n')
        plain_lines = [self.strip_ansi(line).strip() for line in lines if line.strip()]

        top_border = plain_lines[0]
        self.assertTrue(top_border.startswith('+'), f"Top border must start with +: {top_border}")
        self.assertTrue(top_border.endswith('+'), f"Top border must end with +: {top_border}")
        self.assertIn('VITALS', top_border, f"Top border must contain VITALS: {top_border}")

        # The action footer is the last line; find the last actual border line
        border_lines = [l for l in plain_lines if l.startswith('+') and l.endswith('+')]
        self.assertTrue(len(border_lines) >= 1, "No border lines found")
        self.assertTrue(all(c == '=' for c in border_lines[-1][1:-1]), f"Bottom border malformed: {border_lines[-1]}")

    def test_status_matrix_color(self):
        from vitals import NORMAL
        metrics = {
            'priority': 32, 
            'cpu_affinity': [0, 1], 
            'cpu_percent': 10.0, 
            'memory_gb': 1.0
        }
        with patch('psutil.cpu_count', return_value=8):
            output = render_ui(metrics, state=NORMAL)
            # 32 -> Normal, 2 cores out of 8 -> 2/8
            expected_matrix = f"{self.CYAN}priority  {'Normal':<12}  cores  {'2/8':<7}        {self.RESET}"
            self.assertIn(expected_matrix, output)

    def test_status_matrix_fixed_width(self):
        from vitals import NORMAL
        metrics1 = {'priority': 32, 'cpu_affinity': [0, 1], 'cpu_percent': 10.0, 'memory_gb': 1.0}
        metrics2 = {'priority': 16384, 'cpu_affinity': [0, 1, 2, 3, 4, 5, 6, 7], 'cpu_percent': 10.0, 'memory_gb': 1.0}
        
        output1 = render_ui(metrics1, state=NORMAL)
        output2 = render_ui(metrics2, state=NORMAL)
        
        matrix1 = [self.strip_ansi(line) for line in output1.split('\n') if 'priority  ' in self.strip_ansi(line)][0]
        matrix2 = [self.strip_ansi(line) for line in output2.split('\n') if 'priority  ' in self.strip_ansi(line)][0]

        self.assertEqual(matrix1.find('cores  '), matrix2.find('cores  '))
        self.assertEqual(len(matrix1), len(matrix2))

    def test_vertical_stabilization_line_count(self):
        from vitals import NORMAL, WARNING, CRITICAL
        metrics = {'cpu_percent': 10.0, 'memory_gb': 1.0}
        
        out_normal = render_ui(metrics, state=NORMAL)
        out_warning = render_ui(metrics, state=WARNING, warning_msg="CPU High")
        out_critical = render_ui(metrics, state=CRITICAL, warning_msg="OOM")
        
        lines_normal = len(out_normal.split('\n'))
        lines_warning = len(out_warning.split('\n'))
        lines_critical = len(out_critical.split('\n'))
        
        self.assertEqual(lines_normal, lines_warning)
        self.assertEqual(lines_normal, lines_critical)

    def test_stacked_bars_exact_length(self):
        from vitals import draw_stacked_ram_bar, draw_stacked_cpu_bar
        bar1 = self.strip_ansi(draw_stacked_ram_bar(1.0))
        bar2 = self.strip_ansi(draw_stacked_ram_bar(15.5))
        self.assertEqual(bar1.index(']') - bar1.index('[') - 1, 40)
        self.assertEqual(bar2.index(']') - bar2.index('[') - 1, 40)
        
        bar3 = self.strip_ansi(draw_stacked_cpu_bar(10.0))
        bar4 = self.strip_ansi(draw_stacked_cpu_bar(99.9))
        self.assertEqual(bar3.index(']') - bar3.index('[') - 1, 40)
        self.assertEqual(bar4.index(']') - bar4.index('[') - 1, 40)

    def test_stacked_bars_visuals(self):
        from vitals import draw_stacked_ram_bar, draw_stacked_cpu_bar, WHITE, RESET
        # We need to mock psutil.virtual_memory to get predictable results
        with patch('psutil.virtual_memory') as mock_vm:
            # Total 100GB, Used 50GB. Target uses 10GB.
            # Other = 50 - 10 = 40GB.
            # other_ratio = 40/100 = 0.4. target_ratio = 10/100 = 0.1.
            # bar_length = 40.
            # other_chars = 16. target_chars = 4. free_chars = 20.
            mock_vm.return_value.total = 100 * (1024**3)
            mock_vm.return_value.used = 50 * (1024**3)
            
            output = draw_stacked_ram_bar(10.0)
            
            # Check for WHITE '■' for Other Apps
            self.assertIn(f"{WHITE}{'■' * 16}{RESET}", output)
            
        with patch('psutil.cpu_percent', return_value=50.0):
            # Total 50%, Target 10%. Other 40%.
            # other_ratio = 0.4. target_ratio = 0.1.
            # other_chars = 16. target_chars = 4. idle_chars = 20.
            output = draw_stacked_cpu_bar(10.0)
            
            # Check for WHITE '■' for Other Apps
            self.assertIn(f"{WHITE}{'■' * 16}{RESET}", output)

    def test_draw_stacked_vram_bar(self):
        from vitals import draw_stacked_vram_bar, WHITE, GREEN, RESET
        vram_metrics = {
            'used_gb': 4.0,
            'total_gb': 10.0,
            'process_vram_gb': 1.0
        }
        # Total 40%, Target 10%, Other 30%
        # Bar length 40: Other 12 chars, Target 4 chars, Free 24 chars
        output = draw_stacked_vram_bar(vram_metrics)
        self.assertIn(f"{WHITE}{'■' * 12}{RESET}", output)
        self.assertIn(f"{GREEN}{'■' * 4}{RESET}", output)
        self.assertIn('-' * 24, output)
        self.assertIn("40.0%", output)
        self.assertIn("VRAM [GPU]", output)

    def test_draw_stacked_vram_bar_fallback(self):
        from vitals import draw_stacked_vram_bar, WHITE, RESET
        vram_metrics = {
            'used_gb': 4.0,
            'total_gb': 10.0,
            'process_vram_gb': None
        }
        output = draw_stacked_vram_bar(vram_metrics)
        # Should treat None as 0.0 process VRAM
        # Total 40%, Target 0%, Other 40%
        # Bar length 40: Other 16 chars, Target 0 chars, Free 24 chars
        self.assertIn(f"{WHITE}{'■' * 16}{RESET}", output)
        self.assertIn('-' * 24, output)
        self.assertIn("40.0%", output)

    def test_render_ui_vram_spillage_warning(self):
        from vitals import NORMAL, RED_BLINK, RESET
        metrics = {'cpu_percent': 10.0, 'memory_gb': 1.0}
        # 95% usage + 0.5 GB shared
        vram_metrics = {
            'used_gb': 9.5,
            'total_gb': 10.0,
            'process_vram_gb': 2.0,
            'shared_used_gb': 0.5
        }
        output = render_ui(metrics, vram_metrics=vram_metrics, state=NORMAL)

        # Unified overflow warning in RED_BLINK
        expected_warning = f"{RED_BLINK}!!! GPU MEMORY OVERFLOW INTO SYSTEM RAM !!!{RESET}"
        self.assertIn(expected_warning, output)

    def test_global_metrics_section(self):
        from vitals import NORMAL
        metrics = {'cpu_percent': 10.0, 'memory_gb': 1.0}
        storage_metrics = {'C': {'utilization_percent': 20.0}}
        output = render_ui(metrics, storage_metrics=storage_metrics, state=NORMAL)
        
        # DISK C should be present
        self.assertIn("DISK C", output)

        # Disk section must appear before the process CPU bar
        disk_idx = output.find("DISK C")
        cpu_idx  = output.find("CPU")
        self.assertLess(disk_idx, cpu_idx,
                        f"DISK must come before CPU: Disk({disk_idx}) < CPU({cpu_idx})")

    def test_render_ui_instance_symmetry(self):
        from vitals import NORMAL
        instances = [
            {'pid': 123, 'title': 'App 1', 'metrics': {'cpu_percent': 10.0, 'memory_gb': 1.0}, 'state': NORMAL},
            {'pid': 456, 'title': 'App 2', 'metrics': {'cpu_percent': 20.0, 'memory_gb': 2.0}, 'state': NORMAL}
        ]
        storage_metrics = {'C': {'utilization_percent': 20.0}}
        output = render_ui(storage_metrics=storage_metrics, instances=instances)
        
        # Count occurrences of "DISK C" - should be 1
        self.assertEqual(output.count("DISK C"), 1)
        # Count occurrences of "CPU" - should be 2
        self.assertEqual(output.count("CPU"), 2)

    def test_ui_width_80(self):
        from vitals import NORMAL
        metrics = {'cpu_percent': 10.0, 'memory_gb': 1.0}
        storage_metrics = {'C': {'utilization_percent': 20.0}}
        output = render_ui(metrics, storage_metrics=storage_metrics, state=NORMAL)
        
        for line in output.split('\n'):
            plain_line = self.strip_ansi(line)
            if plain_line:
                self.assertEqual(len(plain_line), 80, f"Line width is not 80: '{plain_line}' (len={len(plain_line)})")

class TestBarSuffixes(unittest.TestCase):
    """Verify that bar suffix lines show the right numbers for quick-glance reading."""

    def strip_ansi(self, text):
        import re
        return re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])').sub('', text)

    def test_ram_bar_shows_process_gb(self):
        """RAM bar suffix includes the process GB so artist can see 3ds Max's footprint."""
        with patch('psutil.virtual_memory') as mock_vm:
            mock_vm.return_value.total = 16 * 1024 ** 3
            mock_vm.return_value.used = 10 * 1024 ** 3
            plain = self.strip_ansi(draw_stacked_ram_bar(8.0))
        # target_gb=8.0 and total_gb=16.0 should appear in the suffix
        self.assertIn('8.0', plain)
        self.assertIn('16', plain)
        self.assertIn('GB', plain)

    def test_ram_bar_suffix_fits_width(self):
        """RAM bar visible length stays within 76 chars (enforced by format_line)."""
        with patch('psutil.virtual_memory') as mock_vm:
            mock_vm.return_value.total = 256 * 1024 ** 3
            mock_vm.return_value.used = 200 * 1024 ** 3
            plain = self.strip_ansi(draw_stacked_ram_bar(180.0))
        self.assertLessEqual(len(plain), 76)

    def test_cpu_bar_shows_process_percent(self):
        """CPU bar suffix shows both process % and system % to eliminate ambiguity."""
        plain = self.strip_ansi(draw_stacked_cpu_bar(12.5, system_cpu_percent=45.0))
        self.assertIn('12.5', plain)
        self.assertIn('45.0', plain)

    def test_cpu_bar_suffix_fits_width(self):
        plain = self.strip_ansi(draw_stacked_cpu_bar(99.9, system_cpu_percent=99.9))
        self.assertLessEqual(len(plain), 76)

    def test_disk_bar_shows_mb_s(self):
        """Disk section in render_ui shows MB/s throughput when metric is present."""
        from vitals import NORMAL
        metrics = {'cpu_percent': 10.0, 'memory_gb': 1.0}
        storage_metrics = {'C': {'utilization_percent': 20.0, 'mb_s': 23.4}}
        output = render_ui(metrics, storage_metrics=storage_metrics, state=NORMAL)
        self.assertIn('23.4', output)
        self.assertIn('MB/s', output)

    def test_disk_bar_zero_mb_s_fallback(self):
        """Disk bar renders without mb_s key (backward compat with old metric dict)."""
        from vitals import NORMAL
        metrics = {'cpu_percent': 10.0, 'memory_gb': 1.0}
        storage_metrics = {'C': {'utilization_percent': 20.0}}
        output = render_ui(metrics, storage_metrics=storage_metrics, state=NORMAL)
        self.assertIn('MB/s', output)  # header always present
        self.assertIn('DISK C', output)


class TestActionFooter(unittest.TestCase):
    def strip_ansi(self, text):
        import re
        return re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])').sub('', text)

    def test_footer_present_in_render_ui(self):
        """render_ui always outputs an action footer as its last line."""
        from vitals import NORMAL
        metrics = {'cpu_percent': 10.0, 'memory_gb': 1.0}
        output = render_ui(metrics, state=NORMAL)
        plain_lines = [self.strip_ansi(l) for l in output.split('\n') if self.strip_ansi(l).strip()]
        last = plain_lines[-1]
        # Footer contains key hints
        self.assertIn('F:', last)
        self.assertIn('B:', last)
        self.assertIn('Q:', last)

    def test_footer_width_80(self):
        """Footer line is exactly 80 visible characters wide."""
        from vitals import NORMAL
        metrics = {'cpu_percent': 10.0, 'memory_gb': 1.0}
        output = render_ui(metrics, state=NORMAL)
        plain_lines = [self.strip_ansi(l) for l in output.split('\n') if self.strip_ansi(l).strip()]
        self.assertEqual(len(plain_lines[-1]), 80)

    def test_footer_shows_feedback_when_provided(self):
        """When a feedback_msg is passed, it replaces the default footer text."""
        from vitals import NORMAL
        metrics = {'cpu_percent': 10.0, 'memory_gb': 1.0}
        output = render_ui(metrics, state=NORMAL, feedback_msg="[ACTION] Flushed 1.4 GB")
        self.assertIn("Flushed 1.4 GB", output)

    def test_ghosting_still_cleared(self):
        """Every line (including new footer) ends with the ANSI clear-line code."""
        from vitals import NORMAL
        metrics = {'cpu_percent': 10.0, 'memory_gb': 1.0}
        output = render_ui(metrics, state=NORMAL)
        for i, line in enumerate(output.split('\n')):
            self.assertTrue(line.endswith("\033[K"), f"Line {i} missing clear-line: {line!r}")


if __name__ == '__main__':
    unittest.main()
