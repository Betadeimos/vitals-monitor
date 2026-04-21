import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Adding the root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import vitals

class TestVitalsUIV2(unittest.TestCase):
    def setUp(self):
        self.RESET = "\033[0m"
        self.CYAN = "\033[36m"
        self.GREEN = "\033[32m"
        self.YELLOW = "\033[33m"
        self.RED_BLINK = "\033[1;5;31m"
        self.CLEAR_LINE = "\033[K"

    @patch('psutil.virtual_memory')
    def test_stacked_ram_bar_math(self, mock_virtual_memory):
        # 16GB Total, 10GB Used by system, 2GB Used by Target
        # Other Apps = 10 - 2 = 8GB
        # Free = 16 - 10 = 6GB
        mock_virtual_memory.return_value.total = 16 * (1024**3)
        mock_virtual_memory.return_value.used = 10 * (1024**3)
        
        metrics = {'cpu_percent': 10.0, 'memory_gb': 2.0}
        
        # Test drawing the RAM bar
        # Other Apps: 8/16 = 50%
        # Target: 2/16 = 12.5%
        # Free: 6/16 = 37.5%
        # Bar length 40:
        # Other Apps: 20 chars (.)
        # Target: 5 chars (#)
        # Free: 15 chars (-)
        
        # I'll need to check if render_ui calls some draw function with these.
        # Let's assume render_ui will contain this logic.
        output = vitals.render_ui(metrics, state=vitals.NORMAL)
        
        # Check for white characters (Other Apps) and '#' characters (Target)
        # Assuming white characters are represented as '.'
        expected_other = '.' * 20
        expected_target = '#' * 5
        
        self.assertIn(expected_other, output)
        self.assertIn(expected_target, output)
        self.assertIn('-' * 15, output)

    @patch('sys.stdout.write')
    def test_ghosting_fix_prepended_clear_line(self, mock_write):
        # The prompt says to prepend \033[K to print statements outside the main block.
        # Like info messages or kill prompts.
        
        # Let's test set_priority
        mock_proc = MagicMock()
        vitals.set_priority(mock_proc, vitals.WARNING, vitals.NORMAL)
        
        # Verify that \033[K was printed before the message
        calls = [call[0][0] for call in mock_write.call_args_list]
        found = False
        for call in calls:
            # print() calls write with the string then usually with \n
            if self.CLEAR_LINE in call and "[INFO]" in call:
                if call.startswith(self.CLEAR_LINE):
                    found = True
                    break
        
        self.assertTrue(found, f"CLEAR_LINE code not found prepended to INFO message in: {calls}")

if __name__ == '__main__':
    unittest.main()
