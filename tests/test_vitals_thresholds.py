import unittest
import os
import sys

# Add the root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from vitals import MemoryTracker

class TestVitalsThresholds(unittest.TestCase):
    def setUp(self):
        # We need at least a 2-second window for Tier 1
        self.tracker = MemoryTracker(window_size_seconds=5)

    def test_tier1_warning_spike(self):
        """
        Tier 1 (Warning): Detect a rapid memory increase.
        > 0.1GB increase over 2 seconds.
        """
        # Start at 1.0GB
        self.tracker.add_reading(memory_gb=1.0, timestamp=1.0)
        self.tracker.add_reading(memory_gb=1.0, timestamp=2.0)
        
        # Increase by 0.11GB in 1 second (which is <= 2 seconds)
        self.tracker.add_reading(memory_gb=1.11, timestamp=3.0)
        
        # Check if Tier 1 (Yellow) is triggered: > 0.1GB in 2s
        self.assertTrue(self.tracker.check_threshold(threshold_gb=0.1, window_seconds=2, current_time=3.0))

    def test_no_spike_below_threshold(self):
        """
        Ensure it doesn't trigger if below 0.1GB.
        """
        self.tracker.add_reading(memory_gb=1.0, timestamp=1.0)
        self.tracker.add_reading(memory_gb=1.05, timestamp=3.0) # 0.05GB in 2s
        
        self.assertFalse(self.tracker.check_threshold(threshold_gb=0.1, window_seconds=2, current_time=3.0))

    def test_no_spike_outside_window(self):
        """
        Ensure it doesn't trigger if the increase happens over more than 2s.
        """
        self.tracker.add_reading(memory_gb=1.0, timestamp=1.0)
        self.tracker.add_reading(memory_gb=1.11, timestamp=4.0) # 0.11GB in 3s
        
        self.assertFalse(self.tracker.check_threshold(threshold_gb=0.1, window_seconds=2, current_time=4.0))

if __name__ == '__main__':
    unittest.main()
