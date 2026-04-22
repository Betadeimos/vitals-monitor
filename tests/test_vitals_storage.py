import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import subprocess

# Adding the root directory to sys.path to import vitals_core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import vitals_core

class TestVitalsStorage(unittest.TestCase):

    @patch('psutil.disk_io_counters')
    @patch('time.time')
    def test_get_storage_metrics(self, mock_time, mock_io_counters):
        # Reset global state for test
        vitals_core._last_disk_io = {}
        vitals_core._last_disk_time = 0

        # First call (baseline)
        mock_time.return_value = 1000.0
        mock_io_0 = {
            'C:': MagicMock(read_time=100, write_time=50),
            'D:': MagicMock(read_time=200, write_time=100)
        }
        mock_io_counters.return_value = mock_io_0
        
        metrics_1 = vitals_core.get_storage_metrics()
        self.assertIn('C', metrics_1)
        self.assertEqual(metrics_1['C']['utilization_percent'], 0.0)

        # Second call (1 second later)
        mock_time.return_value = 1001.0 # delta = 1000ms
        mock_io_1 = {
            'C:': MagicMock(read_time=200, write_time=150), # delta busy = (200-100) + (150-50) = 200ms
            'D:': MagicMock(read_time=300, write_time=200)  # delta busy = (300-200) + (200-100) = 200ms
        }
        mock_io_counters.return_value = mock_io_1
        
        metrics_2 = vitals_core.get_storage_metrics()
        # utilization = (200 / 1000) * 100 = 20.0%
        self.assertEqual(metrics_2['C']['utilization_percent'], 20.0)
        self.assertEqual(metrics_2['D']['utilization_percent'], 20.0)

    @patch('subprocess.check_output')
    def test_get_vram_metrics_success(self, mock_check_output):
        # nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits
        # Example output: "512, 8192\n"
        mock_check_output.return_value = b"512, 8192\n"
        
        metrics = vitals_core.get_vram_metrics()
        
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics['used_gb'], 0.5) # 512 / 1024
        self.assertEqual(metrics['total_gb'], 8.0) # 8192 / 1024

    @patch('subprocess.check_output')
    def test_get_vram_metrics_not_found(self, mock_check_output):
        mock_check_output.side_effect = FileNotFoundError()
        
        metrics = vitals_core.get_vram_metrics()
        self.assertIsNone(metrics)

    @patch('subprocess.check_output')
    def test_get_vram_metrics_error(self, mock_check_output):
        mock_check_output.side_effect = subprocess.CalledProcessError(1, 'nvidia-smi')
        
        metrics = vitals_core.get_vram_metrics()
        self.assertIsNone(metrics)

if __name__ == '__main__':
    unittest.main()
