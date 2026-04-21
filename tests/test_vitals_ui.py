import unittest
import os
import sys
from unittest.mock import patch

# Add the root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from vitals import draw_bar, render_ui, clear_screen

class TestVitalsUI(unittest.TestCase):
    def setUp(self):
        self.RESET = "\033[0m"
        self.CYAN = "\033[36m"
        self.GREEN = "\033[32m"
        self.YELLOW = "\033[33m"
        self.RED_BLINK = "\033[1;5;31m"

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
        output = draw_bar("RAM", 5000, 8192, bar_length=10, char='#', state=CRITICAL)
        self.assertIn(self.CYAN + "[", output)
        self.assertIn("]" + self.RESET, output)
        self.assertIn(self.RED_BLINK + "######----", output)
        self.assertIn("RAM", output)
        self.assertIn(self.RED_BLINK, output)

    def test_render_ui_normal(self):
        from vitals import NORMAL
        metrics = {'cpu_percent': 10.0, 'memory_gb': 1.0}
        output = render_ui(metrics, state=NORMAL)
        
        # Check for borders
        self.assertIn(self.CYAN, output)
        self.assertIn("=" * 60, output)
        # Check for normal status
        self.assertIn(self.GREEN + "Status: Normal", output)
        # Should not have spike warning
        self.assertNotIn("!!! CRITICAL: RUNAWAY MEMORY LEAK !!!", output)

    def test_render_ui_warning(self):
        from vitals import WARNING
        metrics = {'cpu_percent': 10.0, 'memory_gb': 2.0}
        output = render_ui(metrics, state=WARNING, warning_msg="Spike detected!")
        
        # Check for warning in Yellow
        self.assertIn(self.YELLOW + "--- WARNING: STABILIZING RESOURCES ---", output)
        self.assertIn("Spike detected!", output)
        self.assertIn(self.YELLOW, output)

    def test_render_ui_critical(self):
        from vitals import CRITICAL
        metrics = {'cpu_percent': 10.0, 'memory_gb': 2.0}
        output = render_ui(metrics, state=CRITICAL, warning_msg="Runaway leak!")
        
        # Check for critical warning in Red Blink
        self.assertIn(self.RED_BLINK + "!!! CRITICAL: SYSTEM RAM EXHAUSTED !!!", output)
        self.assertIn("Runaway leak!", output)
        self.assertIn(self.RED_BLINK, output)

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
            'C': {'used_gb': 100.0, 'total_gb': 500.0}
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
            # It should be at index 13 because label is 12 chars + 1 space.
            idx = 13
            self.assertEqual(plain_line[idx], '[', f"Line '{plain_line}' does not have '[' at index {idx}")
            
            # Verify the label part is 12 chars
            label_part = plain_line[:12]
            self.assertEqual(len(label_part), 12, f"Label part '{label_part}' is not 12 chars")

    def test_simplified_borders(self):
        """Verify that borders are simplified (single solid line)."""
        from vitals import NORMAL
        metrics = {'cpu_percent': 10.0, 'memory_gb': 1.0}
        output = render_ui(metrics, state=NORMAL)
        lines = output.split('\n')
        plain_lines = [self.strip_ansi(line).strip() for line in lines if line.strip()]
        
        top_border = plain_lines[0]
        bottom_border = plain_lines[-1]
        
        self.assertTrue(all(c == '=' for c in top_border), f"Top border is not simplified: {top_border}")
        self.assertTrue(all(c == '=' for c in bottom_border), f"Bottom border is not simplified: {bottom_border}")

    def test_status_matrix_fixed_width(self):
        from vitals import NORMAL
        metrics1 = {'priority': 32, 'cpu_affinity': [0, 1], 'cpu_percent': 10.0, 'memory_gb': 1.0}
        metrics2 = {'priority': 16384, 'cpu_affinity': [0, 1, 2, 3, 4, 5, 6, 7], 'cpu_percent': 10.0, 'memory_gb': 1.0}
        
        output1 = render_ui(metrics1, state=NORMAL)
        output2 = render_ui(metrics2, state=NORMAL)
        
        matrix1 = [self.strip_ansi(line) for line in output1.split('\n') if '[ PRIORITY:' in self.strip_ansi(line)][0]
        matrix2 = [self.strip_ansi(line) for line in output2.split('\n') if '[ PRIORITY:' in self.strip_ansi(line)][0]
        
        self.assertEqual(matrix1.find('] [ CORES:'), matrix2.find('] [ CORES:'))
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

if __name__ == '__main__':
    unittest.main()
