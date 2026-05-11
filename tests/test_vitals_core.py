import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Adding the root directory to sys.path to import vitals_core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import vitals_core

class TestVitalsCore(unittest.TestCase):

    @patch('psutil.process_iter')
    def test_find_process_found(self, mock_process_iter):
        # Create a mock process
        mock_process = MagicMock()
        mock_process.info = {
            'name': 'python.exe',
            'cmdline': ['python', 'max_simulator.py']
        }
        
        mock_process_iter.return_value = [mock_process]
        
        process = vitals_core.find_process('max_simulator.py')
        self.assertIsNotNone(process)
        self.assertEqual(process, mock_process)

    @patch('psutil.process_iter')
    def test_find_process_not_found(self, mock_process_iter):
        # Mocking no matching process
        mock_process = MagicMock()
        mock_process.info = {
            'name': 'other_process.exe',
            'cmdline': ['other_process.exe']
        }
        
        mock_process_iter.return_value = [mock_process]
        
        process = vitals_core.find_process('max_simulator.py')
        self.assertIsNone(process)

    @patch('psutil.cpu_count')
    def test_get_process_metrics(self, mock_cpu_count):
        mock_cpu_count.return_value = 1
        mock_process = MagicMock()
        # Mock memory_info to return rss in bytes (e.g., 1 GB = 1024 * 1024 * 1024)
        mock_process.memory_info.return_value.rss = 1 * 1024 * 1024 * 1024
        # Mock cpu_percent
        mock_process.cpu_percent.return_value = 15.5

        metrics = vitals_core.get_process_metrics(mock_process)
        self.assertEqual(metrics['memory_gb'], 1.0)
        self.assertEqual(metrics['cpu_percent'], 15.5)

    @patch('psutil.cpu_count')
    def test_get_process_metrics_cpu_normalization_4_cores(self, mock_cpu_count):
        mock_cpu_count.return_value = 4
        mock_process = MagicMock()
        mock_process.cpu_percent.return_value = 400.0
        mock_process.memory_info.return_value.rss = 1024 * 1024 * 1024

        metrics = vitals_core.get_process_metrics(mock_process)
        self.assertEqual(metrics['cpu_percent'], 100.0)
        self.assertEqual(metrics['memory_gb'], 1.0)

    @patch('psutil.cpu_count')
    def test_get_process_metrics_cpu_normalization_2_cores(self, mock_cpu_count):
        mock_cpu_count.return_value = 2
        mock_process = MagicMock()
        mock_process.cpu_percent.return_value = 50.0
        mock_process.memory_info.return_value.rss = 512 * 1024 * 1024

        metrics = vitals_core.get_process_metrics(mock_process)
        self.assertEqual(metrics['cpu_percent'], 25.0)
        self.assertEqual(metrics['memory_gb'], 0.5)

    @patch('psutil.cpu_count')
    def test_get_process_metrics_priority_and_affinity(self, mock_cpu_count):
        mock_cpu_count.return_value = 4
        mock_process = MagicMock()
        mock_process.cpu_percent.return_value = 100.0
        mock_process.memory_info.return_value.rss = 1024 * 1024 * 1024
        mock_process.nice.return_value = 32
        mock_process.cpu_affinity.return_value = [0, 1, 2, 3]

        metrics = vitals_core.get_process_metrics(mock_process)
        self.assertEqual(metrics['cpu_percent'], 25.0)
        self.assertEqual(metrics['memory_gb'], 1.0)
        self.assertEqual(metrics['priority'], 32)
        self.assertEqual(metrics['cpu_affinity'], [0, 1, 2, 3])

    def test_get_last_input_tick_returns_int(self):
        tick = vitals_core.get_last_input_tick()
        self.assertIsInstance(tick, int)

    @patch('os.name', 'nt')
    def test_get_last_input_tick_windows_success(self):
        mock_user32 = MagicMock()
        mock_user32.GetLastInputInfo.side_effect = lambda ptr: (
            setattr(ptr._obj, 'dwTime', 12345) or True
        )
        with patch.object(vitals_core.ctypes, 'windll', create=True) as mock_windll:
            mock_windll.user32 = mock_user32
            # Just confirm it returns an int without raising
            result = vitals_core.get_last_input_tick()
            self.assertIsInstance(result, int)

    @patch('os.name', 'posix')
    def test_get_last_input_tick_nonwindows_returns_zero(self):
        self.assertEqual(vitals_core.get_last_input_tick(), 0)

if __name__ == '__main__':
    unittest.main()
