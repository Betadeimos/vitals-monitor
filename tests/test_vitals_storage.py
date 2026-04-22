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
    @patch('time.perf_counter')
    @patch('time.sleep')
    def test_get_storage_metrics(self, mock_sleep, mock_perf, mock_io_counters):
        # High precision sub-sampling logic:
        # t1 = perf_counter(), io1 = counters()
        # sleep(0.1)
        # t2 = perf_counter(), io2 = counters()
        
        mock_perf.side_effect = [1000.0, 1000.1] # dt_s = 0.1
        
        # Counter values
        c1 = MagicMock(read_time=100, write_time=50, read_bytes=1000, write_bytes=500)
        c2 = MagicMock(read_time=110, write_time=60, read_bytes=1100, write_bytes=600) # delta_busy = 20ms
        
        # psutil returns a dict with 'perdisk=True'
        mock_io_counters.side_effect = [
            {'C:': c1, 'D:': c1},
            {'C:': c2, 'D:': c2}
        ]

        metrics = vitals_core.get_storage_metrics()
        
        # util = (20ms / (0.1s * 1000)) * 100 = (20 / 100) * 100 = 20.0%
        self.assertEqual(metrics['C']['utilization_percent'], 20.0)
        self.assertEqual(metrics['D']['utilization_percent'], 20.0)

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
