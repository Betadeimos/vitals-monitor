import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import time

# Adding the root directory to sys.path to import max_simulator
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import max_simulator

class TestMaxSimulator(unittest.TestCase):

    def setUp(self):
        # Clear the leak data before each test to ensure isolation
        max_simulator._leak_data = []

    @patch('max_simulator.time.time')
    def test_heavy_calculation(self, mock_time):
        """Test that heavy_calculation logs correctly and exits based on time."""
        # Mocking time.time() to return:
        # 1. 100.0 (logging first info)
        # 2. 101.0 (end_time calculation)
        # 3. 107.0 (loop check: 107.0 < 101.0 + 5 is False)
        # 4. 108.0 (logging second info)
        mock_time.side_effect = [100.0, 101.0, 107.0, 108.0] 
        
        with self.assertLogs('root', level='INFO') as cm:
            # Using small RAM for testing to avoid actual memory pressure in CI
            max_simulator.heavy_calculation(ram_mb=1, duration=5)
            
        output = "\n".join(cm.output)
        self.assertIn("[BUSY] Performing heavy calculation...", output)
        self.assertIn("Heavy calculation concluded.", output)

    @patch('max_simulator.time.sleep')
    def test_fatal_memory_leak(self, mock_sleep):
        """Test that fatal_memory_leak logs correctly for a set number of iterations."""
        with self.assertLogs('root', level='INFO') as cm:
            # Run for 2 iterations
            max_simulator.fatal_memory_leak(chunk_mb=1, interval=0.1, iterations=2)
            
        output = "\n".join(cm.output)
        self.assertIn("[CRITICAL] Memory leak initiated!", output)
        self.assertIn("Allocating 1MB...", output)
        self.assertIn("Total leak approximately 2MB", output)
        
        # Verify sleep was called for each iteration
        self.assertEqual(mock_sleep.call_count, 2)
        # Verify memory chunks were added to global list
        self.assertEqual(len(max_simulator._leak_data), 2)

if __name__ == '__main__':
    unittest.main()
