import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Adding the root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import vitals_core

class TestVitalsCoreV2(unittest.TestCase):

    @patch('psutil.cpu_count')
    def test_get_process_metrics_cpu_normalization(self, mock_cpu_count):
        # Mock 4 cores
        mock_cpu_count.return_value = 4
        
        mock_process = MagicMock()
        # Mock 400% CPU usage (which means 100% of all cores)
        mock_process.cpu_percent.return_value = 400.0
        mock_process.memory_info.return_value.rss = 1024 * 1024 * 1024 # 1GB
        
        metrics = vitals_core.get_process_metrics(mock_process)
        
        # Expected: 400.0 / 4 = 100.0
        self.assertEqual(metrics['cpu_percent'], 100.0)
        self.assertEqual(metrics['memory_gb'], 1.0)

    @patch('psutil.cpu_count')
    def test_get_process_metrics_cpu_normalization_2_cores(self, mock_cpu_count):
        # Mock 2 cores
        mock_cpu_count.return_value = 2
        
        mock_process = MagicMock()
        # Mock 50% CPU usage (which means 25% of all cores)
        mock_process.cpu_percent.return_value = 50.0
        mock_process.memory_info.return_value.rss = 512 * 1024 * 1024 # 0.5GB
        
        metrics = vitals_core.get_process_metrics(mock_process)
        
        # Expected: 50.0 / 2 = 25.0
        self.assertEqual(metrics['cpu_percent'], 25.0)
        self.assertEqual(metrics['memory_gb'], 0.5)

if __name__ == '__main__':
    unittest.main()
