import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Adding the root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import vitals

class TestVitalsUIV3(unittest.TestCase):
    def setUp(self):
        self.RESET = "\033[0m"
        self.CYAN = "\033[36m"
        self.GREEN = "\033[32m"
        self.YELLOW = "\033[33m"
        self.RED_BLINK = "\033[1;5;31m"
        self.WHITE = "\033[37m"
        self.CLEAR_LINE = "\033[K"

    @patch('psutil.cpu_percent')
    def test_draw_stacked_cpu_bar(self, mock_cpu_percent):
        # System CPU: 50%
        # Target CPU: 10%
        # Other Apps: 50 - 10 = 40%
        # Idle: 100 - 50 = 50%
        
        # Bar length 40:
        # Other Apps ('#', WHITE): 40% of 40 = 16 chars
        # Target ('#', GREEN): 10% of 40 = 4 chars
        # Idle ('-'): 50% of 40 = 20 chars
        
        mock_cpu_percent.return_value = 50.0
        
        bar = vitals.draw_stacked_cpu_bar(10.0, state=vitals.NORMAL)
        
        self.assertIn(f"{self.WHITE}{'■' * 16}{self.RESET}", bar)
        self.assertIn(f"{self.GREEN}{'■' * 4}{self.RESET}", bar)
        self.assertIn('-' * 20, bar)

    @patch('psutil.cpu_count')
    def test_render_ui_status_matrix(self, mock_cpu_count):
        mock_cpu_count.return_value = 8
        metrics = {
            'cpu_percent': 10.0,
            'memory_gb': 1.0,
            'priority': 32,
            'cpu_affinity': [2, 3, 4, 5]
        }
        
        output = vitals.render_ui(metrics, state=vitals.NORMAL)
        
        # Verify status matrix presence and formatting
        # 32 -> Normal
        # [2, 3, 4, 5] -> 4 cores out of 8
        self.assertIn("[ PRIORITY: Normal       ]", output)
        self.assertIn("[ CORES: 4/8   ]", output)

    @patch('psutil.cpu_count')
    def test_render_ui_status_matrix_idle(self, mock_cpu_count):
        mock_cpu_count.return_value = 16
        metrics = {
            'cpu_percent': 1.0,
            'memory_gb': 0.5,
            'priority': 64,
            'cpu_affinity': [0, 1]
        }
        
        output = vitals.render_ui(metrics, state=vitals.NORMAL)
        
        # 64 -> Idle
        # [0, 1] -> 2 cores out of 16
        self.assertIn("[ PRIORITY: Idle         ]", output)
        self.assertIn("[ CORES: 2/16  ]", output)

if __name__ == '__main__':
    unittest.main()
