import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import psutil

# Adding the root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import vitals

class TestRefinementTDD(unittest.TestCase):

    @patch('psutil.Process')
    @patch('psutil.process_iter')
    def test_collateral_hog_not_suspended_if_foreground(self, mock_process_iter, mock_process_class):
        # Setup: RAM is high, chrome is running and it IS the foreground process
        chrome_pid = 3000
        chrome_proc = MagicMock()
        chrome_proc.info = {'name': 'chrome.exe'}
        chrome_proc.status.return_value = 'running'
        chrome_proc.pid = chrome_pid
        
        mock_process_iter.return_value = [chrome_proc]
        
        active_instances = {} # No VIP instances for this test
        
        # High RAM (85%), Foreground is chrome
        vitals.manage_orchestration(active_instances, 85.0, chrome_pid)
        
        # Verify chrome was NOT suspended because it was foreground
        chrome_proc.suspend.assert_not_called()
        self.assertNotIn(chrome_pid, vitals._suspended_hogs)

    @patch('psutil.Process')
    def test_resume_all_cleanup(self, mock_process_class):
        # Setup: Some tracked instances are suspended, and some hogs are suspended
        
        # 1. Tracked instances
        pid1 = 1001
        proc1 = MagicMock()
        proc1.is_running.return_value = True
        proc1.status.return_value = 'stopped'
        
        active_instances = {
            pid1: {'proc': proc1}
        }
        
        # 2. Collateral hogs
        pid2 = 2002
        proc2 = MagicMock()
        proc2.is_running.return_value = True
        proc2.status.return_value = 'stopped'
        
        # Mock psutil.Process(pid2) to return proc2
        def side_effect(pid):
            if pid == pid2: return proc2
            raise psutil.NoSuchProcess(pid)
        mock_process_class.side_effect = side_effect
        
        vitals._suspended_hogs.add(pid2)
        
        # Call resume_all
        vitals.resume_all(active_instances)
        
        # Verify both were resumed
        proc1.resume.assert_called_once()
        proc2.resume.assert_called_once()
        
        # Verify _suspended_hogs is cleared
        self.assertEqual(len(vitals._suspended_hogs), 0)

if __name__ == '__main__':
    unittest.main()
