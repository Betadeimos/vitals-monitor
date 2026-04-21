import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Add the root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import vitals

class TestVitalsProcessTermination(unittest.TestCase):
    @patch('vitals.psutil.virtual_memory')
    @patch('vitals.vitals_core.find_process')
    @patch('vitals.vitals_core.get_process_metrics')
    @patch('vitals.input')
    @patch('vitals.time.sleep')
    @patch('vitals.clear_screen')
    def test_spike_detection_and_termination(self, mock_clear, mock_sleep, mock_input, mock_metrics, mock_find, mock_vm):
        # Setup mocks
        mock_vm.return_value.percent = 95.0 # Trigger CRITICAL
        mock_vm.return_value.total = 16 * (1024 ** 3)
        mock_vm.return_value.used = 15 * (1024 ** 3)
        mock_proc = MagicMock()
        mock_proc.pid = 1234
        mock_find.return_value = mock_proc
        
        mock_metrics.return_value = {'cpu_percent': 10, 'memory_gb': 0.4}
        
        # User chooses 'Y' to terminate
        mock_input.return_value = 'Y'
        
        # Stop after one iteration
        mock_sleep.side_effect = StopIteration
        
        try:
            vitals.start_monitoring("test_process")
        except StopIteration:
            pass
            
        # Verify terminate was called
        mock_proc.terminate.assert_called_once()
        # Verify input was called with the correct prompt
        expected_prompt = f"{vitals.CLEAR_LINE}{vitals.RED_BLINK}CRITICAL! Forcefully kill target process? [Y/N]: {vitals.RESET}"
        mock_input.assert_called_with(expected_prompt)

    @patch('vitals.psutil.virtual_memory')
    @patch('vitals.vitals_core.find_process')
    @patch('vitals.vitals_core.get_process_metrics')
    @patch('vitals.input')
    @patch('vitals.time.sleep')
    @patch('vitals.clear_screen')
    def test_spike_detection_and_no_termination(self, mock_clear, mock_sleep, mock_input, mock_metrics, mock_find, mock_vm):
        # Setup mocks
        mock_vm.return_value.percent = 95.0 # Trigger CRITICAL
        mock_vm.return_value.total = 16 * (1024 ** 3)
        mock_vm.return_value.used = 15 * (1024 ** 3)
        mock_proc = MagicMock()
        mock_proc.pid = 1234
        mock_find.return_value = mock_proc
        
        mock_metrics.return_value = {'cpu_percent': 10, 'memory_gb': 0.4}
        
        # User chooses 'N' to NOT terminate
        mock_input.return_value = 'N'
        
        # Stop after one iteration
        mock_sleep.side_effect = StopIteration
        
        try:
            vitals.start_monitoring("test_process")
        except StopIteration:
            pass
            
        # Verify terminate was NOT called
        mock_proc.terminate.assert_not_called()
        # Verify input was called
        self.assertTrue(mock_input.called)

if __name__ == '__main__':
    unittest.main()
