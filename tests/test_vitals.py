import unittest
import os
import sys

# Add the root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from vitals import MemoryTracker

class TestVitals(unittest.TestCase):
    def test_memory_spike_detection(self):
        tracker = MemoryTracker(window_size_seconds=5)
        
        # Add normal readings
        tracker.add_reading(memory_gb=0.100, timestamp=1.0)
        tracker.add_reading(memory_gb=0.105, timestamp=2.0)
        tracker.add_reading(memory_gb=0.102, timestamp=3.0)
        tracker.add_reading(memory_gb=0.108, timestamp=4.0)
        tracker.add_reading(memory_gb=0.110, timestamp=5.0)
        
        # Threshold is 0.05GB increase within 5 seconds
        self.assertFalse(tracker.check_threshold(threshold_gb=0.05, window_seconds=5))
        
        # Add a spike reading at 6.0
        tracker.add_reading(memory_gb=0.160, timestamp=6.0)
        # Within the last 5 seconds [2.0 to 6.0], min is 0.102 (at 3.0), max is 0.160 (at 6.0) => 0.058 GB increase
        self.assertTrue(tracker.check_threshold(threshold_gb=0.05, window_seconds=5))

    def test_memory_no_spike_if_gradual(self):
        tracker = MemoryTracker(window_size_seconds=5)
        
        # Gradual increase, but over a longer period
        tracker.add_reading(memory_gb=0.100, timestamp=1.0)
        tracker.add_reading(memory_gb=0.120, timestamp=4.0)
        tracker.add_reading(memory_gb=0.140, timestamp=8.0) # 8.0 - 5 = 3.0. Window is [4.0, 8.0]. Min=0.120, Max=0.140. Diff=0.02.
        
        self.assertFalse(tracker.check_threshold(threshold_gb=0.03, window_seconds=5))

    def test_memory_spike_eviction(self):
        tracker = MemoryTracker(window_size_seconds=5)
        
        tracker.add_reading(memory_gb=0.100, timestamp=1.0)
        tracker.add_reading(memory_gb=0.200, timestamp=2.0) # Spike here
        self.assertTrue(tracker.check_threshold(threshold_gb=0.05, window_seconds=5))
        
        # Fast forward past the window
        tracker.add_reading(memory_gb=0.200, timestamp=10.0) # Window is [5.0, 10.0]
        self.assertFalse(tracker.check_threshold(threshold_gb=0.05, window_seconds=5))

if __name__ == '__main__':
    unittest.main()
