import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Adding the root directory to sys.path to import vitals_core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import vitals_core

class TestWindowTitles(unittest.TestCase):

    @patch('os.name', 'nt')
    @patch('vitals_core.ctypes', create=True)
    def test_get_window_title_prioritizes_3dsmax(self, mock_ctypes):
        mock_user32 = mock_ctypes.windll.user32
        
        # Mocking PIDs
        target_pid = 1234
        
        # We need to mock how GetWindowThreadProcessId works.
        # It takes a pointer to a DWORD.
        def side_effect_get_pid(hwnd, pid_ptr):
            if hwnd in [101, 102, 103]:
                pid_ptr.contents.value = target_pid
            else:
                pid_ptr.contents.value = 9999
            return 0

        # Mock c_ulong and byref
        mock_ctypes.c_ulong = MagicMock
        # We need to simulate the .value attribute on the object passed to byref
        
        # A more robust way to mock the PID retrieval:
        class MockDWORD:
            def __init__(self, value=0):
                self.value = value
        
        mock_pids = {101: 1234, 102: 1234, 103: 1234, 104: 9999}
        
        def mock_get_window_thread_process_id(hwnd, pid_ref):
            pid_ref.value = mock_pids.get(hwnd, 0)
            return 0
            
        mock_user32.GetWindowThreadProcessId.side_effect = mock_get_window_thread_process_id
        mock_ctypes.byref = lambda x: x
        mock_ctypes.WINFUNCTYPE.return_value = lambda x: x
        
        # 3 windows for our PID:
        # 101: "Slate Material Editor"
        # 102: "untitled - 3ds Max 2024"
        # 103: "C:\Scenes\Project_A.max - 3ds Max 2024" (Longer title)
        
        def side_effect_enum(callback, lparam):
            if not callback(101, lparam): return False
            if not callback(102, lparam): return False
            if not callback(103, lparam): return False
            if not callback(104, lparam): return False
            return True
        
        mock_user32.EnumWindows.side_effect = side_effect_enum
        mock_user32.IsWindowVisible.return_value = True
        
        def side_effect_get_text_length(hwnd):
            titles = {
                101: len("Slate Material Editor"),
                102: len("untitled - 3ds Max 2024"),
                103: len("C:\\Scenes\\Project_A.max - 3ds Max 2024")
            }
            return titles.get(hwnd, 0)
            
        mock_user32.GetWindowTextLengthW.side_effect = side_effect_get_text_length
        
        def side_effect_get_text(hwnd, buff, max_len):
            titles = {
                101: "Slate Material Editor",
                102: "untitled - 3ds Max 2024",
                103: "C:\\Scenes\\Project_A.max - 3ds Max 2024"
            }
            title = titles.get(hwnd, "")
            buff.value = title
            return len(title)
            
        mock_user32.GetWindowTextW.side_effect = side_effect_get_text
        
        # The test: it should pick the longest title containing "3ds Max"
        title = vitals_core.get_window_title(target_pid)
        self.assertEqual(title, "C:\\Scenes\\Project_A.max - 3ds Max 2024")

    @patch('os.name', 'nt')
    @patch('vitals_core.ctypes', create=True)
    def test_get_window_title_fallback(self, mock_ctypes):
        mock_user32 = mock_ctypes.windll.user32
        target_pid = 1234
        
        mock_pids = {101: 1234}
        mock_user32.GetWindowThreadProcessId.side_effect = lambda hwnd, pid_ref: setattr(pid_ref, 'value', mock_pids.get(hwnd, 0))
        mock_ctypes.byref = lambda x: x
        mock_ctypes.WINFUNCTYPE.return_value = lambda x: x
        
        def side_effect_enum(callback, lparam):
            callback(101, lparam)
            return True
        
        mock_user32.EnumWindows.side_effect = side_effect_enum
        mock_user32.IsWindowVisible.return_value = True
        
        mock_user32.GetWindowTextLengthW.return_value = len("Some Other Window")
        def side_effect_get_text(hwnd, buff, max_len):
            buff.value = "Some Other Window"
            return len(buff.value)
        mock_user32.GetWindowTextW.side_effect = side_effect_get_text
        
        # Should fallback to the only visible window even if it doesn't contain "3ds Max"
        title = vitals_core.get_window_title(target_pid)
        self.assertEqual(title, "Some Other Window")

if __name__ == '__main__':
    unittest.main()
