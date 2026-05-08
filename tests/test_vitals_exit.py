import unittest
import os
import sys
from unittest.mock import patch, MagicMock

# Add the root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from vitals import main

class TestVitalsExit(unittest.TestCase):
    @patch('vitals.start_monitoring')
    @patch('vitals.clear_screen')
    @patch('sys.exit')
    @patch('builtins.print')
    def test_keyboard_interrupt_handling(self, mock_print, mock_exit, mock_clear, mock_start):
        # Setup: start_monitoring raises KeyboardInterrupt
        mock_start.side_effect = KeyboardInterrupt()
        
        # We need to mock sys.argv to avoid reading actual args
        with patch('sys.argv', ['vitals.py', 'max_simulator']):
            main()
        
        # Verify: clear_screen(full=True) called
        mock_clear.assert_called_with(full=True)
        
        # Verify: Info message printed
        import vitals
        mock_print.assert_any_call(f"{vitals.CLEAR_LINE}[INFO] Monitoring terminated by user. Exiting...")
        
        # Verify: sys.exit(0) called
        mock_exit.assert_called_with(0)

if __name__ == '__main__':
    unittest.main()
