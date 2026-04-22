import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Adding the root directory to sys.path to import vitals_core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import vitals_core

class TestVitalsWinAPI(unittest.TestCase):

    @patch('os.name', 'posix')
    @patch('vitals_core.ctypes', None)
    def test_is_process_responding_non_windows(self):
        # Should return True on non-Windows platforms
        self.assertTrue(vitals_core.is_process_responding(1234))

    @patch('os.name', 'nt')
    @patch('vitals_core.ctypes', create=True)
    def test_is_process_responding_windows_responding(self, mock_ctypes):
        # Mocking ctypes structures and functions
        mock_user32 = mock_ctypes.windll.user32
        
        # Mock c_ulong and byref
        mock_pid_obj = MagicMock()
        mock_pid_obj.value = 1234
        mock_ctypes.c_ulong.return_value = mock_pid_obj
        mock_ctypes.byref.side_effect = lambda x: x
        
        # Mock WINFUNCTYPE to return the callback itself
        mock_ctypes.WINFUNCTYPE.return_value = lambda x: x
        
        # Mock GetWindowThreadProcessId to set the PID (already done via mock_pid_obj.value)
        # In the real code, it would be:
        # lp_pid = ctypes.c_ulong()
        # GetWindowThreadProcessId(hwnd, byref(lp_pid))
        
        # Simulate EnumWindows calling the callback
        def side_effect_enum(callback, lparam):
            callback(100, lparam) # hwnd=100
            return True
        
        mock_user32.EnumWindows.side_effect = side_effect_enum
        mock_user32.IsHungAppWindow.return_value = False # NOT hung
        
        self.assertTrue(vitals_core.is_process_responding(1234))
        mock_user32.IsHungAppWindow.assert_called_with(100)

    @patch('os.name', 'nt')
    @patch('vitals_core.ctypes', create=True)
    def test_is_process_responding_windows_hung(self, mock_ctypes):
        # Mocking ctypes structures and functions
        mock_user32 = mock_ctypes.windll.user32
        
        # Mock c_ulong and byref
        mock_pid_obj = MagicMock()
        mock_pid_obj.value = 1234
        mock_ctypes.c_ulong.return_value = mock_pid_obj
        mock_ctypes.byref.side_effect = lambda x: x
        
        # Mock WINFUNCTYPE to return the callback itself
        mock_ctypes.WINFUNCTYPE.return_value = lambda x: x
        
        # Simulate EnumWindows calling the callback
        def side_effect_enum(callback, lparam):
            callback(100, lparam) # hwnd=100
            return True
        
        mock_user32.EnumWindows.side_effect = side_effect_enum
        mock_user32.IsHungAppWindow.return_value = True # HUNG
        
        self.assertFalse(vitals_core.is_process_responding(1234))
        mock_user32.IsHungAppWindow.assert_called_with(100)

    @patch('os.name', 'nt')
    @patch('vitals_core.ctypes', create=True)
    def test_is_process_responding_mismatched_pid(self, mock_ctypes):
        # Mocking ctypes structures and functions
        mock_user32 = mock_ctypes.windll.user32
        
        # Mock c_ulong and byref
        mock_pid_obj = MagicMock()
        mock_pid_obj.value = 9999 # Different PID
        mock_ctypes.c_ulong.return_value = mock_pid_obj
        mock_ctypes.byref.side_effect = lambda x: x
        
        # Mock WINFUNCTYPE to return the callback itself
        mock_ctypes.WINFUNCTYPE.return_value = lambda x: x
        
        # Simulate EnumWindows calling the callback
        def side_effect_enum(callback, lparam):
            callback(100, lparam)
            return True
        
        mock_user32.EnumWindows.side_effect = side_effect_enum
        
        self.assertTrue(vitals_core.is_process_responding(1234))
        mock_user32.IsHungAppWindow.assert_not_called()

    @patch('os.name', 'nt')
    @patch('vitals_core.ctypes', create=True)
    def test_is_process_responding_windows_ignore_hidden_hung_window(self, mock_ctypes):
        # Mocking ctypes structures and functions
        mock_user32 = mock_ctypes.windll.user32
        
        # Mock c_ulong and byref
        mock_pid_obj = MagicMock()
        mock_pid_obj.value = 1234
        mock_ctypes.c_ulong.return_value = mock_pid_obj
        mock_ctypes.byref.side_effect = lambda x: x
        
        # Mock WINFUNCTYPE to return the callback itself
        mock_ctypes.WINFUNCTYPE.return_value = lambda x: x
        
        # Simulate EnumWindows calling the callback with two windows
        # Window 101: Visible, NOT hung
        # Window 102: Hidden, Hung
        def side_effect_enum(callback, lparam):
            callback(101, lparam)
            callback(102, lparam)
            return True
        
        mock_user32.EnumWindows.side_effect = side_effect_enum
        
        def side_effect_is_visible(hwnd):
            if hwnd == 101: return True
            if hwnd == 102: return False
            return False
            
        mock_user32.IsWindowVisible.side_effect = side_effect_is_visible
        
        def side_effect_is_hung(hwnd):
            if hwnd == 101: return False
            if hwnd == 102: return True
            return False
            
        mock_user32.IsHungAppWindow.side_effect = side_effect_is_hung
        
        # Should be True because the visible window (101) is not hung
        self.assertTrue(vitals_core.is_process_responding(1234))
        
        # Should have checked visibility for both, but hung state only for the visible one
        mock_user32.IsWindowVisible.assert_any_call(101)
        mock_user32.IsWindowVisible.assert_any_call(102)
        mock_user32.IsHungAppWindow.assert_called_once_with(101)

    @patch('os.name', 'nt')
    @patch('vitals_core.ctypes', create=True)
    def test_get_main_window_handle_windows(self, mock_ctypes):
        mock_user32 = mock_ctypes.windll.user32
        mock_pid_obj = MagicMock()
        mock_pid_obj.value = 1234
        mock_ctypes.c_ulong.return_value = mock_pid_obj
        mock_ctypes.byref.side_effect = lambda x: x
        mock_ctypes.WINFUNCTYPE.return_value = lambda x: x
        
        def side_effect_enum(callback, lparam):
            callback(100, lparam)
            return True
        
        mock_user32.EnumWindows.side_effect = side_effect_enum
        mock_user32.IsWindowVisible.return_value = True
        
        hwnd = vitals_core.get_main_window_handle(1234)
        self.assertEqual(hwnd, 100)

    @patch('os.name', 'nt')
    @patch('vitals_core.ctypes', create=True)
    def test_attempt_rescue_windows(self, mock_ctypes):
        mock_user32 = mock_ctypes.windll.user32
        
        # Mock get_main_window_handle to return 100
        with patch('vitals_core.get_main_window_handle', return_value=100):
            success = vitals_core.attempt_rescue(1234)
            
            self.assertTrue(success)
            # WM_KEYDOWN = 0x0100, VK_ESCAPE = 0x1B
            mock_user32.PostMessageW.assert_called_with(100, 0x0100, 0x1B, 0)

if __name__ == '__main__':
    unittest.main()
