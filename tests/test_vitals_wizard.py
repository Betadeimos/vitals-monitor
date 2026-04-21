import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Add the root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import vitals

class TestVitalsWizard(unittest.TestCase):
    @patch('psutil.process_iter')
    @patch('builtins.input', side_effect=['1', '200', '1.0'])
    def test_interactive_wizard_selection(self, mock_input, mock_process_iter):
        # Mock processes
        mock_proc1 = MagicMock()
        mock_proc1.info = {'name': '3dsmax.exe', 'pid': 1234}
        mock_proc2 = MagicMock()
        mock_proc2.info = {'name': 'max_simulator.py', 'pid': 5678}
        
        mock_process_iter.return_value = [mock_proc1, mock_proc2]
        
        target, threshold, interval = vitals.interactive_wizard()
        
        self.assertEqual(target, '3dsmax.exe')
        self.assertEqual(threshold, 200)
        self.assertEqual(interval, 1.0)

    @patch('psutil.process_iter')
    @patch('builtins.input', side_effect=['2', '', '']) # Default values
    def test_interactive_wizard_defaults(self, mock_input, mock_process_iter):
        # Mock processes
        mock_proc1 = MagicMock()
        mock_proc1.info = {'name': '3dsmax.exe', 'pid': 1234}
        mock_proc2 = MagicMock()
        mock_proc2.info = {'name': 'max_simulator.py', 'pid': 5678}
        
        mock_process_iter.return_value = [mock_proc1, mock_proc2]
        
        target, threshold, interval = vitals.interactive_wizard()
        
        self.assertEqual(target, 'max_simulator.py')
        self.assertEqual(threshold, 0.1)
        self.assertEqual(interval, 0.5)

    @patch('psutil.process_iter')
    def test_interactive_wizard_no_processes(self, mock_process_iter):
        mock_process_iter.return_value = []
        
        with patch('builtins.print') as mock_print:
            result = vitals.interactive_wizard()
            self.assertEqual(result, (None, None, None))
            # Verify that some message about not finding processes was printed
            called_with_no_proc_msg = any("No matching processes found" in str(call) for call in mock_print.call_args_list)
            self.assertTrue(called_with_no_proc_msg)

    @patch('psutil.process_iter')
    @patch('builtins.input', side_effect=['0.2', '1.5'])
    def test_interactive_wizard_autoselect(self, mock_input, mock_process_iter):
        # Mock exactly one process
        mock_proc1 = MagicMock()
        mock_proc1.info = {'name': '3dsmax.exe', 'pid': 1234}
        mock_process_iter.return_value = [mock_proc1]
        
        target, threshold, interval = vitals.interactive_wizard()
        
        # Verify the target name is auto-selected
        self.assertEqual(target, '3dsmax.exe')
        self.assertEqual(threshold, 0.2)
        self.assertEqual(interval, 1.5)
        
        # Verify that only 2 inputs were requested (skipping selection)
        self.assertEqual(mock_input.call_count, 2)
        
        # Verify first prompt was for threshold
        first_call_prompt = mock_input.call_args_list[0][0][0]
        self.assertIn("Memory threshold", first_call_prompt)
        self.assertNotIn("Select process number", first_call_prompt)

if __name__ == '__main__':
    unittest.main()
