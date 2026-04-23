import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Adding the root directory to sys.path to import vitals_core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import vitals_core

class TestVIPDetection(unittest.TestCase):

    @patch('os.name', 'posix')
    @patch('vitals_core.ctypes', None)
    def test_get_foreground_pid_non_windows(self):
        # Should return None on non-Windows platforms
        self.assertIsNone(vitals_core.get_foreground_pid())

    @patch('os.name', 'nt')
    @patch('vitals_core.ctypes', create=True)
    def test_get_foreground_pid_windows(self, mock_ctypes):
        mock_user32 = mock_ctypes.windll.user32
        
        # Mock GetForegroundWindow to return a handle
        mock_user32.GetForegroundWindow.return_value = 12345
        
        # Mock c_ulong and byref for GetWindowThreadProcessId
        mock_pid_obj = MagicMock()
        mock_pid_obj.value = 6789
        mock_ctypes.c_ulong.return_value = mock_pid_obj
        mock_ctypes.byref.side_effect = lambda x: x
        
        pid = vitals_core.get_foreground_pid()
        
        self.assertEqual(pid, 6789)
        mock_user32.GetForegroundWindow.assert_called_once()
        mock_user32.GetWindowThreadProcessId.assert_called_once_with(12345, mock_pid_obj)

    @patch('os.name', 'nt')
    @patch('vitals_core.ctypes', create=True)
    def test_get_foreground_pid_no_foreground(self, mock_ctypes):
        mock_user32 = mock_ctypes.windll.user32
        
        # Mock GetForegroundWindow to return NULL
        mock_user32.GetForegroundWindow.return_value = 0
        
        pid = vitals_core.get_foreground_pid()
        
        self.assertIsNone(pid)
        mock_user32.GetWindowThreadProcessId.assert_not_called()

if __name__ == '__main__':
    unittest.main()
