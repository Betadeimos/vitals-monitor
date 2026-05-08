import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Adding the root directory to sys.path to import vitals_core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import vitals_core

class TestVitalsStorageMapping(unittest.TestCase):

    @patch('vitals_core.get_physical_drive_name')
    @patch('psutil.disk_io_counters')
    @patch('time.perf_counter')
    @patch('time.sleep')
    def test_get_storage_metrics_physical_mapping(self, mock_sleep, mock_perf, mock_io_counters, mock_get_drive_name):
        # Mock the mapping: C: -> PhysicalDrive1, D: -> PhysicalDrive0
        mock_get_drive_name.side_effect = lambda dl: "PhysicalDrive1" if "C" in dl else "PhysicalDrive0"

        mock_perf.side_effect = [1000.0, 1000.1] # dt_s = 0.1
        
        c1 = MagicMock(read_time=100, write_time=50, read_bytes=1000, write_bytes=500)
        c2 = MagicMock(read_time=110, write_time=60, read_bytes=1100, write_bytes=600) # delta_busy = 20ms
        
        mock_io_counters.side_effect = [
            {'PhysicalDrive1': c1, 'PhysicalDrive0': c1},
            {'PhysicalDrive1': c2, 'PhysicalDrive0': c2}
        ]

        metrics = vitals_core.get_storage_metrics()
        
        # util = (20ms / (0.1s * 1000)) * 100 = 20.0%
        self.assertEqual(metrics['C']['utilization_percent'], 20.0)
        self.assertEqual(metrics['D']['utilization_percent'], 20.0)

    def test_get_physical_drive_name_real(self):
        # On Windows, we should get something like PhysicalDriveX
        if os.name == 'nt':
            name_c = vitals_core.get_physical_drive_name("C:")
            name_d = vitals_core.get_physical_drive_name("D:")
            self.assertTrue(name_c.startswith("PhysicalDrive"), f"Expected PhysicalDrive for C:, got {name_c}")
            self.assertTrue(name_d.startswith("PhysicalDrive"), f"Expected PhysicalDrive for D:, got {name_d}")
        else:
            name_c = vitals_core.get_physical_drive_name("C:")
            self.assertEqual(name_c, "C:")

if __name__ == '__main__':
    unittest.main()
