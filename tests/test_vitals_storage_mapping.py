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
    @patch('time.time')
    def test_get_storage_metrics_physical_mapping(self, mock_time, mock_io_counters, mock_get_drive_name):
        # Reset global state for test
        vitals_core._last_disk_io = {}
        vitals_core._last_disk_time = 0

        # Mock the mapping: C: -> PhysicalDrive1, D: -> PhysicalDrive0
        mock_get_drive_name.side_effect = lambda dl: "PhysicalDrive1" if "C" in dl else "PhysicalDrive0"

        # First call (baseline)
        mock_time.return_value = 1000.0
        mock_io_0 = {
            'PhysicalDrive1': MagicMock(read_time=100, write_time=50),
            'PhysicalDrive0': MagicMock(read_time=200, write_time=100)
        }
        mock_io_counters.return_value = mock_io_0
        
        metrics_1 = vitals_core.get_storage_metrics()
        self.assertIn('C', metrics_1)
        self.assertIn('D', metrics_1)
        self.assertEqual(metrics_1['C']['utilization_percent'], 0.0)

        # Second call (1 second later)
        mock_time.return_value = 1001.0 # delta = 1000ms
        mock_io_1 = {
            'PhysicalDrive1': MagicMock(read_time=200, write_time=150), # delta busy = 200ms
            'PhysicalDrive0': MagicMock(read_time=300, write_time=200)  # delta busy = 200ms
        }
        mock_io_counters.return_value = mock_io_1
        
        metrics_2 = vitals_core.get_storage_metrics()
        # utilization = (200 / 1000) * 100 = 20.0%
        self.assertEqual(metrics_2['C']['utilization_percent'], 20.0)
        self.assertEqual(metrics_2['D']['utilization_percent'], 20.0)

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
