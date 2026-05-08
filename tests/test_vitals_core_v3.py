import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Adding the root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import vitals_core

class TestVitalsCoreV3(unittest.TestCase):

    @patch('psutil.cpu_count')
    def test_get_process_metrics_priority_and_affinity(self, mock_cpu_count):
        mock_cpu_count.return_value = 4
        
        mock_process = MagicMock()
        mock_process.cpu_percent.return_value = 100.0
        mock_process.memory_info.return_value.rss = 1024 * 1024 * 1024 # 1GB
        
        # Mocking priority and affinity
        mock_process.nice.return_value = 32 # NORMAL_PRIORITY_CLASS on Windows
        mock_process.cpu_affinity.return_value = [0, 1, 2, 3]
        
        metrics = vitals_core.get_process_metrics(mock_process)
        
        self.assertEqual(metrics['cpu_percent'], 25.0)
        self.assertEqual(metrics['memory_gb'], 1.0)
        self.assertEqual(metrics['priority'], 32)
        self.assertEqual(metrics['cpu_affinity'], [0, 1, 2, 3])

if __name__ == '__main__':
    unittest.main()
