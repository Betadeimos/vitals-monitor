import unittest
from unittest.mock import patch, MagicMock
import time
import os
import sys

# Add the parent directory to sys.path to import vitals
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import vitals

class TestVRAMMonitor(unittest.TestCase):
    @patch('vitals_core.get_vram_metrics')
    def test_vram_monitor_caching(self, mock_get_vram):
        """
        Verify that VRAMMonitor caches results and doesn't block.
        """
        mock_metrics = {'used_gb': 1.0, 'total_gb': 8.0}
        mock_get_vram.return_value = mock_metrics
        
        # Use a very short interval for testing
        monitor = vitals.VRAMMonitor(interval=0.1)
        
        try:
            # Wait a bit for the thread to run
            time.sleep(0.3)
            
            metrics = monitor.get_metrics()
            self.assertEqual(metrics, mock_metrics)
            
            # Update mock value
            new_metrics = {'used_gb': 2.0, 'total_gb': 8.0}
            mock_get_vram.return_value = new_metrics
            
            # Wait for next update
            time.sleep(0.3)
            
            metrics = monitor.get_metrics()
            self.assertEqual(metrics, new_metrics)
            
            # Verify it's called multiple times (it's in a loop)
            self.assertTrue(mock_get_vram.call_count >= 2)
            
        finally:
            monitor.stop()

    @patch('vitals_core.get_vram_metrics')
    def test_vram_monitor_handles_none(self, mock_get_vram):
        """
        Verify that VRAMMonitor handles None from vitals_core.
        """
        mock_get_vram.return_value = None
        
        monitor = vitals.VRAMMonitor(interval=0.1)
        
        try:
            time.sleep(0.2)
            self.assertIsNone(monitor.get_metrics())
        finally:
            monitor.stop()

if __name__ == '__main__':
    unittest.main()
