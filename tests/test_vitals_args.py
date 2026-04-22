import unittest
from unittest.mock import patch
import sys
import os

# Add the root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from vitals import parse_args

class TestVitalsArgs(unittest.TestCase):
    def test_default_args(self):
        with patch.object(sys, 'argv', ['vitals.py']):
            args = parse_args()
            self.assertIsNone(args.target)
            self.assertEqual(args.threshold, 0.1)
            self.assertEqual(args.interval, 0.5)

    def test_positional_target(self):
        with patch.object(sys, 'argv', ['vitals.py', 'my_process']):
            args = parse_args()
            self.assertEqual(args.target, 'my_process')
            self.assertEqual(args.threshold, 0.1)
            self.assertEqual(args.interval, 0.5)

    def test_optional_target(self):
        # Testing if it also works as an optional argument if requested
        # The prompt says "Add a positional or optional argument for the target process name"
        # I'll implement it as a positional argument that can also be specified via --target if I want, 
        # but let's stick to the prompt's ambiguity or pick one.
        # Usually, if it's "positional or optional", it means one or the other.
        # Let's try positional first as it's common for the main target.
        with patch.object(sys, 'argv', ['vitals.py', 'custom_target']):
            args = parse_args()
            self.assertEqual(args.target, 'custom_target')

    def test_threshold_arg(self):
        with patch.object(sys, 'argv', ['vitals.py', '--threshold', '250']):
            args = parse_args()
            self.assertEqual(args.threshold, 250)

    def test_interval_arg(self):
        with patch.object(sys, 'argv', ['vitals.py', '--interval', '1.5']):
            args = parse_args()
            self.assertEqual(args.interval, 1.5)

    def test_all_args(self):
        with patch.object(sys, 'argv', ['vitals.py', '3dsmax', '--threshold', '500', '--interval', '2.0']):
            args = parse_args()
            self.assertEqual(args.target, '3dsmax')
            self.assertEqual(args.threshold, 500)
            self.assertEqual(args.interval, 2.0)

    def test_short_flags(self):
        # Adding some common short flags for better UX
        with patch.object(sys, 'argv', ['vitals.py', '-t', '150', '-i', '0.1']):
            args = parse_args()
            self.assertEqual(args.threshold, 150)
            self.assertEqual(args.interval, 0.1)

if __name__ == '__main__':
    unittest.main()
