import unittest
import os
import sys
from unittest.mock import patch, MagicMock

# Add the root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from vitals import render_ui, NORMAL, WARNING, CRITICAL, LIFE_SUPPORT

class TestTaskRequirements(unittest.TestCase):
    def strip_ansi(self, text):
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    def test_title_truncation_and_suffix_stripping(self):
        # Long title with 3ds Max suffix
        long_title = "My Very Long Scene Name That Goes On And On - Autodesk 3ds Max 2024"
        # Expected: "My Very Long Scene Name That Goes On And..." (truncated to 40)
        # Suffix " - Autodesk 3ds Max 2024" should be stripped first.
        # "My Very Long Scene Name That Goes On And On" is 44 chars.
        # Truncated to 40: "My Very Long Scene Name That Goes On And" + "..." = 43 chars? 
        # The requirement says "hard maximum character limit (e.g., 40 characters) for the displayed title."
        # If I truncate to 40 INCLUDING ellipsis: "My Very Long Scene Name That Goes On ..." (40 chars)
        
        instances = [{
            'pid': 1234,
            'title': long_title,
            'metrics': {'cpu_percent': 10.0, 'memory_gb': 1.0, 'priority': 32, 'cpu_affinity': [0,1]},
            'state': NORMAL
        }]
        
        output = render_ui(instances=instances)
        plain_output = self.strip_ansi(output)
        
        # Find the instance header line
        header_line = [line for line in plain_output.split('\n') if "INSTANCE: PID 1234" in line][0]
        
        # Check if suffix is stripped
        self.assertNotIn("Autodesk 3ds Max 2024", header_line)
        self.assertNotIn("3ds Max", header_line)
        
        # Check for ellipsis
        self.assertIn("...", header_line)
        
        # Check overall line length
        self.assertEqual(len(header_line.strip()), 80)
        
        # Extract title from header_line: "| INSTANCE: PID 1234 [Title] |"
        # PID 1234 is 4 digits. "INSTANCE: PID " is 14 chars. 
        # Total "INSTANCE: PID 1234 [" is 20 chars.
        title_start = header_line.find("[") + 1
        title_end = header_line.rfind("]")
        title = header_line[title_start:title_end]
        
        self.assertLessEqual(len(title), 40)

    def test_status_msg_routing(self):
        # Test that status_msg is displayed in the UI instead of defaulting to MONITORING ACTIVE
        instances = [{
            'pid': 1234,
            'title': "Test",
            'metrics': {'cpu_percent': 10.0, 'memory_gb': 1.0, 'priority': 32, 'cpu_affinity': [0,1]},
            'state': WARNING,
            'status_msg': "Throttling..."
        }]
        
        output = render_ui(instances=instances)
        self.assertIn("Throttling...", output)
        self.assertNotIn("[ STATUS: MONITORING ACTIVE ]", output)

    def test_default_status_msg(self):
        # Test that default status is MONITORING ACTIVE
        instances = [{
            'pid': 1234,
            'title': "Test",
            'metrics': {'cpu_percent': 10.0, 'memory_gb': 1.0, 'priority': 32, 'cpu_affinity': [0,1]},
            'state': NORMAL,
            'status_msg': None
        }]
        
        output = render_ui(instances=instances)
        self.assertIn("[ STATUS: MONITORING ACTIVE ]", output)

if __name__ == '__main__':
    unittest.main()
