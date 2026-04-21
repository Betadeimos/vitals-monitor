import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import subprocess

# Adding the root directory to sys.path to import vitals_core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import vitals_core

class TestVitalsStorage(unittest.TestCase):

    @patch('psutil.disk_usage')
    def test_get_storage_metrics(self, mock_disk_usage):
        # Mock disk usage for C: and D:
        # psutil.disk_usage returns a namedtuple (total, used, free, percent)
        mock_c = MagicMock()
        mock_c.total = 500 * (1024 ** 3)
        mock_c.used = 250 * (1024 ** 3)
        
        mock_d = MagicMock()
        mock_d.total = 1000 * (1024 ** 3)
        mock_d.used = 100 * (1024 ** 3)
        
        def side_effect(path):
            if path == 'C:':
                return mock_c
            if path == 'D:':
                return mock_d
            raise FileNotFoundError()
            
        mock_disk_usage.side_effect = side_effect
        
        metrics = vitals_core.get_storage_metrics()
        
        self.assertEqual(metrics['C']['used_gb'], 250.0)
        self.assertEqual(metrics['C']['total_gb'], 500.0)
        self.assertEqual(metrics['D']['used_gb'], 100.0)
        self.assertEqual(metrics['D']['total_gb'], 1000.0)

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
