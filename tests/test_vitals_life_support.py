import unittest
from unittest.mock import MagicMock, patch
import psutil
import os
import sys

# Add the parent directory to sys.path to import vitals
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import vitals

class TestVitalsLifeSupport(unittest.TestCase):
    def setUp(self):
        self.mock_proc = MagicMock(spec=psutil.Process)
        self.mock_proc.pid = 1234
        
        # Ensure priority constants exist for testing
        if not hasattr(psutil, 'IDLE_PRIORITY_CLASS'):
            psutil.IDLE_PRIORITY_CLASS = 0x00000040
        if not hasattr(psutil, 'NORMAL_PRIORITY_CLASS'):
            psutil.NORMAL_PRIORITY_CLASS = 0x00000020

    @patch('os.name', 'nt')
    @patch('psutil.cpu_count', return_value=8)
    def test_apply_life_support(self, mock_cpu_count):
        """
        Verify that apply_life_support saves original values and sets throttled values.
        """
        original_affinity = [0, 1, 2, 3, 4, 5, 6, 7]
        original_priority = psutil.NORMAL_PRIORITY_CLASS
        
        self.mock_proc.cpu_affinity.return_value = original_affinity
        self.mock_proc.nice.return_value = original_priority
        
        saved_context = {'affinity': None, 'priority': None}
        
        with patch('vitals.print'):
            vitals.apply_life_support(self.mock_proc, saved_context)
        
        # Verify original values were saved
        self.assertEqual(saved_context['affinity'], original_affinity)
        self.assertEqual(saved_context['priority'], original_priority)
        
        # Verify new values were set
        # Cores 0 and 1 removed from [0..7] -> [2, 3, 4, 5, 6, 7]
        expected_affinity = [2, 3, 4, 5, 6, 7]
        self.mock_proc.cpu_affinity.assert_called_with(expected_affinity)
        self.mock_proc.nice.assert_called_with(psutil.IDLE_PRIORITY_CLASS)

    @patch('os.name', 'nt')
    def test_restore_life_support(self):
        """
        Verify that restore_life_support restores original values and clears context.
        """
        original_affinity = [0, 1, 2, 3, 4, 5, 6, 7]
        original_priority = psutil.NORMAL_PRIORITY_CLASS
        
        saved_context = {
            'affinity': original_affinity,
            'priority': original_priority
        }
        
        with patch('vitals.print'):
            vitals.restore_life_support(self.mock_proc, saved_context)
        
        # Verify values were restored
        self.mock_proc.cpu_affinity.assert_called_with(original_affinity)
        self.mock_proc.nice.assert_called_with(original_priority)
        
        # Verify context was cleared
        self.assertIsNone(saved_context['affinity'])
        self.assertIsNone(saved_context['priority'])

    @patch('os.name', 'nt')
    @patch('psutil.cpu_count', return_value=2)
    def test_apply_life_support_limited_cores(self, mock_cpu_count):
        """
        Verify that affinity stripping handles cases with few cores (keeps at least one).
        """
        original_affinity = [0, 1]
        original_priority = psutil.NORMAL_PRIORITY_CLASS
        
        self.mock_proc.cpu_affinity.return_value = original_affinity
        self.mock_proc.nice.return_value = original_priority
        
        saved_context = {'affinity': None, 'priority': None}
        
        with patch('vitals.print'):
            vitals.apply_life_support(self.mock_proc, saved_context)
            
        # If only [0, 1] available, and we strip [0, 1], we must keep at least one.
        # Let's assume the logic keeps the last remaining or core 0 if all stripped.
        # Actually, let's see how I implement it. If I use a list comprehension:
        # [c for c in all_cores if c not in [0, 1]]
        # If it's empty, I'll fallback to [0] or something.
        
        self.mock_proc.cpu_affinity.assert_called()
        call_args = self.mock_proc.cpu_affinity.call_args[0][0]
        self.assertTrue(len(call_args) > 0, "Should never set an empty affinity list")

    def test_life_support_handles_access_denied(self):
        """
        Verify that AccessDenied is handled gracefully during life support application.
        """
        self.mock_proc.cpu_affinity.side_effect = psutil.AccessDenied()
        
        saved_context = {'affinity': None, 'priority': None}
        
        # Should not raise exception
        with patch('vitals.print'):
            vitals.apply_life_support(self.mock_proc, saved_context)

if __name__ == '__main__':
    unittest.main()
