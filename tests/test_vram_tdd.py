import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Add the root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from vitals import draw_stacked_vram_bar, draw_gpu_bar, WHITE, GREEN, YELLOW, RED_BLINK, RESET, NORMAL, WARNING, CRITICAL
import vitals_core

class TestVRAMTDD(unittest.TestCase):
    def strip_ansi(self, text):
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    @patch('subprocess.check_output')
    @patch('os.name', 'nt')
    def test_get_vram_metrics_robust(self, mock_output):
        # Mock nvidia-smi GPU info (1st), typeperf (2nd), nvidia-smi apps (3rd)
        mock_output.side_effect = [
            b"1024, 8192\n", # 1st call: nvidia-smi
            b"(PDH-CSV 4.0)\n\\HOST\\Counter\n\"date time\",\"536870912.0\"\n", # 2nd call: typeperf (0.5 GB shared)
            b"123, 512\n456, 256\n" # 3rd call: nvidia-smi apps
        ]
        
        metrics = vitals_core.get_vram_metrics(pids=[123])
        
        self.assertEqual(metrics['used_gb'], 1.0)
        self.assertEqual(metrics['total_gb'], 8.0)
        self.assertEqual(metrics['shared_used_gb'], 0.5)
        self.assertEqual(metrics['per_pid_vram_gb'][123], 0.5) # 512 / 1024

    @patch('subprocess.check_output')
    def test_get_vram_metrics_no_pid(self, mock_output):
        mock_output.return_value = b"2048, 8192\n"
        
        metrics = vitals_core.get_vram_metrics(pids=None)
        
        self.assertEqual(metrics['used_gb'], 2.0)
        self.assertEqual(metrics['total_gb'], 8.0)
        self.assertEqual(metrics.get('per_pid_vram_gb'), {})

    def test_draw_stacked_vram_bar_formatting(self):
        vram_metrics = {
            'used_gb': 4.0,
            'total_gb': 10.0,
            'process_vram_gb': 1.0
        }
        # Total 4.0/10.0 = 40%
        # Process 1.0/10.0 = 10%
        # Other 3.0/10.0 = 30%
        # Bar length 40: Other 12 chars, Target 4 chars, Free 24 chars
        
        output = draw_stacked_vram_bar(vram_metrics, state=NORMAL)
        
        # Verify Label
        plain_output = self.strip_ansi(output)
        self.assertTrue(plain_output.startswith("VRAM [GPU]  "), f"Label incorrect: '{plain_output[:12]}'")
        self.assertEqual(plain_output[12], ' ', "Missing space after label")
        self.assertEqual(plain_output[13], '[', "Missing '[' at index 13")
        
        # Verify Characters
        # Other Apps: '■' (White), Target: '■' (Green)
        self.assertIn(f"{WHITE}{'■' * 12}{RESET}", output)
        self.assertIn(f"{GREEN}{'■' * 4}{RESET}", output)
        
        # Verify Bar Length (40 chars between [ and ])
        # Find the bracket that starts the bar (after the label)
        bar_start_idx = plain_output.find('[', 12)
        bar_end_idx = plain_output.find(']', bar_start_idx)
        bar_content = plain_output[bar_start_idx+1 : bar_end_idx]
        self.assertEqual(len(bar_content), 40)
        self.assertEqual(bar_content, '■' * 12 + '■' * 4 + '-' * 24)

    def test_draw_stacked_vram_bar_alignment(self):
        """Ensure it aligns with other bars (12 char label padding)."""
        vram_metrics = {'used_gb': 1.0, 'total_gb': 10.0, 'process_vram_gb': 0.5}
        output = draw_stacked_vram_bar(vram_metrics)
        plain = self.strip_ansi(output)
        self.assertEqual(plain[12], ' ')
        self.assertEqual(plain[13], '[')

class TestDrawGPUBar(unittest.TestCase):
    def strip_ansi(self, text):
        import re
        return re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])').sub('', text)

    def _bar_content(self, raw_output):
        """Extract the 40-char content between [ and ] of the bar."""
        plain = self.strip_ansi(raw_output)
        start = plain.index('[', 12)
        end = plain.index(']', start)
        return plain[start + 1:end]

    def test_bar_length_always_40(self):
        """Bar content must be exactly 40 chars in all cases."""
        cases = [
            {'used_gb': 4.0, 'total_gb': 8.0, 'shared_used_gb': 0.0},
            {'used_gb': 4.0, 'total_gb': 8.0, 'shared_used_gb': 1.5},
            {'used_gb': 7.9, 'total_gb': 8.0, 'shared_used_gb': 2.0},
            {'used_gb': 0.0, 'total_gb': 8.0, 'shared_used_gb': 0.0},
        ]
        for m in cases:
            with self.subTest(metrics=m):
                out = draw_gpu_bar(m, process_gb=1.0)
                self.assertEqual(len(self._bar_content(out)), 40)

    def test_label_alignment(self):
        """Label is 12 chars and '[' appears at index 13 of plain text."""
        m = {'used_gb': 2.0, 'total_gb': 8.0, 'shared_used_gb': 0.0}
        plain = self.strip_ansi(draw_gpu_bar(m))
        self.assertEqual(plain[12], ' ')
        self.assertEqual(plain[13], '[')

    def test_label_text(self):
        m = {'used_gb': 2.0, 'total_gb': 8.0, 'shared_used_gb': 0.0}
        plain = self.strip_ansi(draw_gpu_bar(m))
        self.assertTrue(plain.startswith('VRAM [GPU]'))

    def test_no_shared_no_red_blocks(self):
        """When shared = 0, no RED_BLINK segments appear in output."""
        m = {'used_gb': 4.0, 'total_gb': 8.0, 'shared_used_gb': 0.0}
        out = draw_gpu_bar(m, process_gb=1.0, state=NORMAL)
        self.assertNotIn(RED_BLINK, out)

    def test_shared_produces_red_blink(self):
        """When shared > 0, RED_BLINK segments appear in the bar."""
        m = {'used_gb': 4.0, 'total_gb': 8.0, 'shared_used_gb': 1.5}
        out = draw_gpu_bar(m, process_gb=1.0, state=NORMAL)
        self.assertIn(RED_BLINK, out)

    def test_shared_blocks_at_right_of_bar(self):
        """Shared blocks appear after free dashes (rightmost position)."""
        # used 4/8 = 50% dedicated, process 1/8, other 3/8, shared 1.5/8
        # other_chars = int(40*3/8) = 15, proc_chars = int(40*1/8) = 5
        # available = 20, shared_chars = int(40*1.5/8) = 7, free = 13
        m = {'used_gb': 4.0, 'total_gb': 8.0, 'shared_used_gb': 1.5}
        content = self._bar_content(draw_gpu_bar(m, process_gb=1.0, state=NORMAL))
        # Dashes must come before the end (shared fills rightmost)
        dash_pos = content.rfind('-')
        block_pos = content.rfind('■')
        self.assertGreater(block_pos, dash_pos, "Shared blocks should be rightmost")

    def test_suffix_shows_percent(self):
        """Suffix always contains the dedicated VRAM percentage."""
        m = {'used_gb': 4.0, 'total_gb': 8.0, 'shared_used_gb': 0.0}
        plain = self.strip_ansi(draw_gpu_bar(m))
        self.assertIn('50.0%', plain)

    def test_suffix_shows_shared_when_nonzero(self):
        """When shared > 0, suffix includes the shared GB figure."""
        m = {'used_gb': 4.0, 'total_gb': 8.0, 'shared_used_gb': 1.5}
        plain = self.strip_ansi(draw_gpu_bar(m))
        self.assertIn('+1.5GB', plain)

    def test_no_suffix_annotation_when_shared_zero(self):
        """When shared = 0, suffix has no '+' annotation."""
        m = {'used_gb': 4.0, 'total_gb': 8.0, 'shared_used_gb': 0.0}
        plain = self.strip_ansi(draw_gpu_bar(m))
        self.assertNotIn('+', plain)

    def test_no_nvidia_fallback(self):
        """When total_gb = 0, bar shows N/A."""
        m = {'used_gb': 0.0, 'total_gb': 0.0, 'shared_used_gb': 0.0}
        plain = self.strip_ansi(draw_gpu_bar(m))
        self.assertIn('N/A', plain)

    def test_state_warning_colors_process_segment(self):
        """WARNING state colors process segment YELLOW."""
        m = {'used_gb': 4.0, 'total_gb': 8.0, 'shared_used_gb': 0.0}
        out = draw_gpu_bar(m, process_gb=1.0, state=WARNING)
        self.assertIn(YELLOW + '■', out)

    def test_state_critical_colors_process_segment(self):
        """CRITICAL state colors process segment RED_BLINK."""
        m = {'used_gb': 4.0, 'total_gb': 8.0, 'shared_used_gb': 0.0}
        out = draw_gpu_bar(m, process_gb=1.0, state=CRITICAL)
        self.assertIn(RED_BLINK + '■', out)

    def test_other_apps_white(self):
        """Other apps' VRAM is shown in WHITE."""
        m = {'used_gb': 4.0, 'total_gb': 8.0, 'shared_used_gb': 0.0}
        out = draw_gpu_bar(m, process_gb=1.0, state=NORMAL)
        self.assertIn(WHITE + '■', out)

    def test_overflow_caps_at_bar_length(self):
        """Even with heavy overcommit (dedicated + shared > total), bar stays 40 chars."""
        m = {'used_gb': 7.9, 'total_gb': 8.0, 'shared_used_gb': 3.0}
        content = self._bar_content(draw_gpu_bar(m, process_gb=3.0, state=NORMAL))
        self.assertEqual(len(content), 40)

    def test_none_process_gb_treated_as_zero(self):
        """process_gb=None is treated as 0.0 without error."""
        m = {'used_gb': 4.0, 'total_gb': 8.0, 'shared_used_gb': 0.0}
        out = draw_gpu_bar(m, process_gb=None, state=NORMAL)
        self.assertIsNotNone(out)
        content = self._bar_content(out)
        self.assertEqual(len(content), 40)


if __name__ == '__main__':
    unittest.main()
