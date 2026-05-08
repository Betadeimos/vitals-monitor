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
    def test_collateral_hog_not_demoted_if_foreground(self, mock_process_iter, mock_process_class):
        # Setup: RAM is high, chrome is running and it IS the foreground process
        chrome_pid = 3000
        chrome_proc = MagicMock()
        chrome_proc.info = {'name': 'chrome.exe'}
        chrome_proc.nice.return_value = psutil.NORMAL_PRIORITY_CLASS
        chrome_proc.pid = chrome_pid
        
        mock_process_iter.return_value = [chrome_proc]
        
        active_instances = {} # No VIP instances for this test
        
        # High RAM (85%), Foreground is chrome
        all_procs = [chrome_proc]
        vitals.manage_orchestration(active_instances, 85.0, chrome_pid, all_procs)
        
        # Verify chrome was NOT demoted because it was foreground
        chrome_proc.nice.assert_not_called()
        self.assertNotIn(chrome_proc, vitals._demoted_hogs)

    @patch('psutil.Process')
    def test_restore_all_cleanup(self, mock_process_class):
        # Setup: Some tracked instances are demoted, and some hogs are demoted
        
        # 1. Tracked instances
        pid1 = 1001
        proc1 = MagicMock()
        proc1.is_running.return_value = True
        proc1.nice.return_value = psutil.IDLE_PRIORITY_CLASS
        
        active_instances = {
            pid1: {'proc': proc1}
        }
        
        # 2. Collateral hogs
        pid2 = 2002
        proc2 = MagicMock()
        proc2.is_running.return_value = True
        proc2.nice.return_value = psutil.IDLE_PRIORITY_CLASS
        
        # Mock psutil.Process(pid2) to return proc2
        def side_effect(pid):
            if pid == pid2: return proc2
            raise psutil.NoSuchProcess(pid)
        mock_process_class.side_effect = side_effect
        
        vitals._demoted_hogs.add(proc2)
        
        # Call restore_all
        vitals.restore_all(active_instances)
        
        # Verify both were restored
        proc1.nice.assert_called_with(psutil.NORMAL_PRIORITY_CLASS)
        proc2.nice.assert_called_with(psutil.NORMAL_PRIORITY_CLASS)
        
        # Verify _demoted_hogs is cleared
        self.assertEqual(len(vitals._demoted_hogs), 0)

if __name__ == '__main__':
    unittest.main()
