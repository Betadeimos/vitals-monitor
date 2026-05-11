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

if __name__ == '__main__':
    unittest.main()
