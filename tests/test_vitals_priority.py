import unittest
from unittest.mock import MagicMock, patch
import psutil
import sys
import vitals

class TestVitalsPriority(unittest.TestCase):
    def setUp(self):
        self.mock_proc = MagicMock(spec=psutil.Process)
        # Mocking platform to be Windows for these tests as requested
        self.patcher_os_name = patch('os.name', 'nt')
        self.patcher_os_name.start()
        
        # Define priority constants if they don't exist in the environment where tests run
        if not hasattr(psutil, 'BELOW_NORMAL_PRIORITY_CLASS'):
            psutil.BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
        if not hasattr(psutil, 'NORMAL_PRIORITY_CLASS'):
            psutil.NORMAL_PRIORITY_CLASS = 0x00000020

    def tearDown(self):
        self.patcher_os_name.stop()

    def test_lower_priority_on_warning(self):
        """
        Verify that the process priority is lowered when entering WARNING state.
        """
        # In a real scenario, this would be called inside vitals.py
        # We need to implement a function or logic in vitals.py that we can test.
        # For now, we'll design how we expect it to be called.
        
        with patch('vitals.print') as mock_print:
            vitals.set_priority(self.mock_proc, vitals.WARNING)
            
            self.mock_proc.nice.assert_called_with(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            mock_print.assert_any_call(f"{vitals.CLEAR_LINE}{vitals.YELLOW}[INFO] Throttling process priority for stability...{vitals.RESET}")

    def test_restore_priority_on_normal(self):
        """
        Verify that the process priority is restored when returning to NORMAL state.
        """
        with patch('vitals.print') as mock_print:
            # Transition from WARNING to NORMAL
            vitals.set_priority(self.mock_proc, vitals.NORMAL, current_state=vitals.WARNING)
            
            self.mock_proc.nice.assert_called_with(psutil.NORMAL_PRIORITY_CLASS)
            mock_print.assert_any_call(f"{vitals.CLEAR_LINE}{vitals.CYAN}[INFO] Restoring process priority.{vitals.RESET}")

    def test_no_priority_change_if_state_unchanged(self):
        """
        Verify that priority is not set if the state hasn't changed.
        """
        vitals.set_priority(self.mock_proc, vitals.NORMAL, current_state=vitals.NORMAL)
        self.mock_proc.nice.assert_not_called()

    def test_handle_access_denied(self):
        """
        Verify that psutil.AccessDenied is handled gracefully.
        """
        self.mock_proc.nice.side_effect = psutil.AccessDenied()
        
        with patch('vitals.print') as mock_print:
            # This should not raise an exception
            vitals.set_priority(self.mock_proc, vitals.WARNING)
            
            self.mock_proc.nice.assert_called()
            # It might be good to log that it failed, but the requirement says "gracefully"
            # which usually means don't crash.

if __name__ == '__main__':
    unittest.main()
