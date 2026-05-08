import unittest
from unittest.mock import patch, MagicMock
import sys
import vitals

class TestEntryPoint(unittest.TestCase):
    @patch('vitals.start_monitoring')
    def test_main_no_args_starts_instantly(self, mock_start):
        """Test that calling main with no arguments starts monitoring instantly."""
        with patch.object(sys, 'argv', ['vitals']):
            vitals.main()
        mock_start.assert_called_once_with(None, 0.1, 0.5)

    @patch('vitals.parse_args')
    @patch('vitals.start_monitoring')
    def test_main_with_args_calls_start_monitoring(self, mock_start, mock_parse):
        """Test that calling main with arguments bypasses the wizard and starts monitoring."""
        mock_args = MagicMock()
        mock_args.target = "custom_proc"
        mock_args.threshold = 200
        mock_args.interval = 1.0
        mock_parse.return_value = mock_args
        
        with patch.object(sys, 'argv', ['vitals', 'custom_proc']):
            vitals.main()
            
        mock_parse.assert_called_once()
        mock_start.assert_called_once_with("custom_proc", 200, 1.0)

if __name__ == '__main__':
    unittest.main()
