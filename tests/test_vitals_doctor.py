import unittest
import os
import sys
import psutil
from unittest.mock import patch, MagicMock

# Add root to path to import vitals_doctor
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import vitals_doctor

class TestVitalsDoctor(unittest.TestCase):
    
    @patch('subprocess.check_output')
    def test_measure_nvidia_smi_time(self, mock_check_output):
        mock_check_output.return_value = b"some output"
        elapsed_ms = vitals_doctor.measure_nvidia_smi_time()
        self.assertIsInstance(elapsed_ms, (int, float))
        self.assertGreaterEqual(elapsed_ms, 0)

    def test_measure_process_iteration_time(self):
        elapsed_ms, count = vitals_doctor.measure_process_iteration_time()
        self.assertIsInstance(elapsed_ms, (int, float))
        self.assertIsInstance(count, int)
        self.assertGreaterEqual(count, 0)

    def test_check_admin_affinity_permission(self):
        # This test might vary depending on whether the test is run as admin
        # We can mock psutil.Process to simulate success or failure
        with patch('psutil.Process') as mock_proc_class:
            mock_proc = MagicMock()
            mock_proc_class.return_value = mock_proc
            
            # Case 1: Success
            mock_proc.cpu_affinity.return_value = None # setting affinity usually returns None or updated affinity
            result = vitals_doctor.check_admin_affinity_permission()
            self.assertIsInstance(result, bool)

            # Case 2: Access Denied
            mock_proc.cpu_affinity.side_effect = psutil.AccessDenied()
            result = vitals_doctor.check_admin_affinity_permission()
            self.assertFalse(result)

if __name__ == '__main__':
    unittest.main()
