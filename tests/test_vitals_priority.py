import unittest
from unittest.mock import MagicMock, patch
import psutil
import os
import sys

# Add the parent directory to sys.path to import vitals
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import vitals

class TestVitalsPriority(unittest.TestCase):
    def setUp(self):
        self.mock_proc = MagicMock(spec=psutil.Process)
        # Ensure priority constants exist for testing
        if not hasattr(psutil, 'BELOW_NORMAL_PRIORITY_CLASS'):
            psutil.BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
        if not hasattr(psutil, 'NORMAL_PRIORITY_CLASS'):
            psutil.NORMAL_PRIORITY_CLASS = 0x00000020

    @patch('os.name', 'nt')
    def test_lower_priority_on_warning(self):
        """
        Verify that the process priority is lowered when entering WARNING state.
        """
        ctx = {'status_msg': None}
        vitals.set_priority(self.mock_proc, vitals.WARNING, ctx=ctx)

        self.mock_proc.nice.assert_called_with(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        self.assertEqual(ctx['status_msg'], "[INFO] Throttling process priority for stability...")

    @patch('os.name', 'nt')
    def test_restore_priority_on_normal(self):
        """
        Verify that the process priority is restored when returning to NORMAL state.
        """
        ctx = {'status_msg': None}
        # Transition from WARNING to NORMAL
        vitals.set_priority(self.mock_proc, vitals.NORMAL, current_state=vitals.WARNING, ctx=ctx)

        self.mock_proc.nice.assert_called_with(psutil.NORMAL_PRIORITY_CLASS)
        self.assertEqual(ctx['status_msg'], "[INFO] Restoring process priority.")

    def test_priority_handles_access_denied(self):
        """
        Verify that AccessDenied is handled gracefully.
        """
        self.mock_proc.nice.side_effect = psutil.AccessDenied()
        
        # Should not raise exception
        vitals.set_priority(self.mock_proc, vitals.WARNING)

if __name__ == '__main__':
    unittest.main()
