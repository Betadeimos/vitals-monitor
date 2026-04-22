import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Adding the root directory to sys.path to import vitals and vitals_core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import vitals_core
from vitals import MemoryTracker, draw_bar

class TestVitalsConversions(unittest.TestCase):

    def test_memory_conversion_to_gb(self):
        """
        Verify that bytes are correctly converted to GB and rounded to two decimal places.
        1 GB = 1024 * 1024 * 1024 bytes
        """
        mock_process = MagicMock()
        # 2 GB in bytes
        mock_process.memory_info.return_value.rss = 2 * 1024 * 1024 * 1024
        mock_process.cpu_percent.return_value = 10.0
        
        metrics = vitals_core.get_process_metrics(mock_process)
        # We expect 'memory_gb' instead of 'memory_mb'
        self.assertIn('memory_gb', metrics)
        self.assertEqual(metrics['memory_gb'], 2.00)
        
        # Test rounding: 1.556 GB -> 1.56 GB
        mock_process.memory_info.return_value.rss = int(1.556 * 1024 * 1024 * 1024)
        metrics = vitals_core.get_process_metrics(mock_process)
        self.assertEqual(metrics['memory_gb'], 1.56)

    @patch('psutil.virtual_memory')
    def test_ram_bar_max_value_scaling(self, mock_virtual_memory):
        """
        Verify that the RAM bar's maximum value is correctly derived from psutil.virtual_memory().total.
        """
        # Mock 16 GB total RAM
        total_ram_bytes = 16 * 1024 * 1024 * 1024
        mock_virtual_memory.return_value.total = total_ram_bytes
        
        # We need to check if vitals uses this value for the RAM bar.
        # Since vitals.py is mainly a script, we'll check if the logic in draw_bar 
        # works correctly when given the converted total RAM.
        
        total_ram_gb = total_ram_bytes / (1024 ** 3)
        current_usage_gb = 4.0
        
        # draw_bar(label, value, max_value, ...)
        bar_output = draw_bar("RAM", current_usage_gb, total_ram_gb)
        
        # Check if the ratio is correct (4/16 = 25%)
        # Bar length is 40 by default. 25% of 40 is 10.
        # [■■■■■■■■■■------------------------------]
        self.assertIn("■" * 10, bar_output)
        self.assertIn("-" * 30, bar_output)
        self.assertIn("25.0%", bar_output)

    def test_thresholds_handle_gb_values(self):
        """
        Ensure internal thresholds (e.g., spike detection) correctly handle GB values.
        """
        tracker = MemoryTracker(window_size_seconds=5)
        
        # Threshold of 0.10 GB (102.4 MB)
        threshold_gb = 0.10
        
        tracker.add_reading(memory_gb=1.0, timestamp=1.0)
        # Spike of 0.11 GB
        tracker.add_reading(memory_gb=1.11, timestamp=2.0)
        
        self.assertTrue(tracker.check_threshold(threshold_gb=threshold_gb, window_seconds=2, current_time=2.0))
        
        # Below threshold: 0.05 GB spike
        tracker2 = MemoryTracker(window_size_seconds=5)
        tracker2.add_reading(memory_gb=1.0, timestamp=1.0)
        tracker2.add_reading(memory_gb=1.05, timestamp=2.0)
        self.assertFalse(tracker2.check_threshold(threshold_gb=threshold_gb, window_seconds=2, current_time=2.0))

if __name__ == '__main__':
    unittest.main()
