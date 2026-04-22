import unittest
from unittest.mock import MagicMock
import os
import sys

# Add the root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import vitals

class TestVitalsLogic(unittest.TestCase):
    def setUp(self):
        self.tracker = vitals.MemoryTracker(window_size_seconds=5)

    def test_determine_state_normal(self):
        metrics = {'cpu_percent': 10.0, 'memory_gb': 1.0}
        system_ram_percent = 50.0
        # No spike
        self.tracker.add_reading(1.0, timestamp=1.0)
        
        state, msg = vitals.determine_state(metrics, system_ram_percent, self.tracker, threshold_gb=0.1)
        self.assertEqual(state, vitals.NORMAL)

    def test_determine_state_tier1_cpu(self):
        metrics = {'cpu_percent': 85.0, 'memory_gb': 1.0}
        system_ram_percent = 50.0
        
        state, msg = vitals.determine_state(metrics, system_ram_percent, self.tracker, threshold_gb=0.1)
        self.assertEqual(state, vitals.WARNING)
        self.assertIn("High CPU usage", msg)

    def test_determine_state_tier1_spike(self):
        metrics = {'cpu_percent': 10.0, 'memory_gb': 1.11}
        system_ram_percent = 50.0
        self.tracker.add_reading(1.0, timestamp=1.0)
        self.tracker.add_reading(1.11, timestamp=2.0)
        
        state, msg = vitals.determine_state(metrics, system_ram_percent, self.tracker, threshold_gb=0.1)
        self.assertEqual(state, vitals.WARNING)
        self.assertIn("Memory spike detected", msg)

    def test_determine_state_tier2_ram(self):
        metrics = {'cpu_percent': 10.0, 'memory_gb': 1.0}
        system_ram_percent = 95.0
        
        state, msg = vitals.determine_state(metrics, system_ram_percent, self.tracker, threshold_gb=0.1)
        self.assertEqual(state, vitals.CRITICAL)
        self.assertIn(f"System RAM > {vitals.CONFIG['tier2']['system_ram_threshold_percent']}%", msg)

    def test_tier2_overrides_tier1(self):
        # Both high CPU and high RAM
        metrics = {'cpu_percent': 85.0, 'memory_gb': 1.0}
        system_ram_percent = 95.0
        
        state, msg = vitals.determine_state(metrics, system_ram_percent, self.tracker, threshold_gb=0.1)
        self.assertEqual(state, vitals.CRITICAL)
        self.assertIn(f"System RAM > {vitals.CONFIG['tier2']['system_ram_threshold_percent']}%", msg)

    def test_determine_state_life_support(self):
        metrics = {'cpu_percent': 10.0, 'memory_gb': 1.0}
        system_ram_percent = 50.0
        
        state, msg = vitals.determine_state(metrics, system_ram_percent, self.tracker, threshold_gb=0.1, is_responding=False)
        self.assertEqual(state, vitals.LIFE_SUPPORT)
        self.assertIn("NOT RESPONDING", msg)

if __name__ == '__main__':
    unittest.main()
