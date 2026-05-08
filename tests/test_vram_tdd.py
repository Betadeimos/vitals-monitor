import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Add the root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from vitals import draw_stacked_vram_bar, WHITE, GREEN, RESET, NORMAL
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

if __name__ == '__main__':
    unittest.main()
