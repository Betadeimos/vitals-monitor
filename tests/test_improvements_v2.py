"""
TDD tests for v2 improvements:
  - Boost lock (manual B overrides survive auto-orchestration)
  - Graduated orchestration (70% gentle, 85% aggressive)
  - Render-mode detection from sustained CPU
  - MemoryTracker.get_slope()
  - Action log in render_ui
  - RED_BLINK no longer blinks
"""
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from vitals import (
    RED_BLINK, MemoryTracker, manage_orchestration, _handle_key,
    render_ui, NORMAL, WARNING, CRITICAL,
)


# ---------------------------------------------------------------------------
# No blink
# ---------------------------------------------------------------------------

class TestNoBlink(unittest.TestCase):
    def test_red_blink_constant_has_no_blink_code(self):
        """ANSI blink attribute is SGR code 5.  It must not appear in RED_BLINK."""
        # Codes are separated by ; inside \033[...m
        # Bold-red without blink is \033[1;31m  (no 5 in the sequence)
        import re
        codes = re.findall(r'\033\[([0-9;]+)m', RED_BLINK)
        for code_str in codes:
            parts = code_str.split(';')
            self.assertNotIn('5', parts,
                msg=f"RED_BLINK still contains blink (SGR 5): {RED_BLINK!r}")


# ---------------------------------------------------------------------------
# MemoryTracker.get_slope
# ---------------------------------------------------------------------------

class TestRAMTrend(unittest.TestCase):
    def _tracker_with(self, readings, base_time=1000.0):
        """Build a MemoryTracker from a list of (offset_s, gb) pairs."""
        t = MemoryTracker(window_size_seconds=60)
        for offset, gb in readings:
            t.add_reading(gb, timestamp=base_time + offset)
        return t

    def test_slope_rising(self):
        t = self._tracker_with([(0, 4.0), (10, 4.5), (20, 5.0), (30, 5.5)])
        slope = t.get_slope(window_seconds=60)
        self.assertGreater(slope, 0.5,
            msg=f"Expected positive slope for rising data, got {slope}")

    def test_slope_stable(self):
        t = self._tracker_with([(0, 8.0), (10, 8.0), (20, 8.0), (30, 8.0)])
        slope = t.get_slope(window_seconds=60)
        self.assertAlmostEqual(slope, 0.0, places=3)

    def test_slope_falling(self):
        t = self._tracker_with([(0, 8.0), (10, 7.5), (20, 7.0), (30, 6.5)])
        slope = t.get_slope(window_seconds=60)
        self.assertLess(slope, -0.5,
            msg=f"Expected negative slope for falling data, got {slope}")

    def test_slope_insufficient_data_returns_zero(self):
        t = MemoryTracker()
        t.add_reading(5.0)
        self.assertEqual(t.get_slope(), 0.0)


# ---------------------------------------------------------------------------
# Boost lock — _handle_key and manage_orchestration
# ---------------------------------------------------------------------------

class TestBoostLock(unittest.TestCase):
    def _make_proc(self, nice_val=32):
        p = MagicMock()
        p.pid = 100
        p._nice = nice_val
        p.nice = MagicMock(side_effect=lambda v=None: p._nice if v is None else setattr(p, '_nice', v) or None)
        p.cpu_affinity = MagicMock(return_value=list(range(8)))
        return p

    def _make_ctx(self, proc):
        return {
            'proc': proc,
            'tracker': MemoryTracker(),
            'state': NORMAL,
            'status_msg': None,
            'warning_since': None,
            'priority_locked': False,
            'render_mode': False,
            'render_start': None,
            'high_cpu_since': None,
            'low_cpu_since': None,
        }

    def test_b_key_sets_priority_locked(self):
        proc = self._make_proc()
        ctx = self._make_ctx(proc)
        active = {proc.pid: ctx}
        HIGH = getattr(__import__('psutil'), 'HIGH_PRIORITY_CLASS', 128)

        _handle_key('B', active, foreground_pid=proc.pid)
        self.assertTrue(ctx['priority_locked'],
            "B key must set priority_locked=True on each instance")

    def test_r_key_clears_priority_locked(self):
        proc = self._make_proc(nice_val=128)
        ctx = self._make_ctx(proc)
        ctx['priority_locked'] = True
        active = {proc.pid: ctx}

        _handle_key('R', active, foreground_pid=proc.pid)
        self.assertFalse(ctx['priority_locked'],
            "R key must clear priority_locked on each instance")

    def test_orchestration_skips_locked_instance(self):
        """manage_orchestration must NOT touch a priority-locked instance."""
        proc = self._make_proc(nice_val=128)   # already at HIGH
        ctx = self._make_ctx(proc)
        ctx['priority_locked'] = True

        active = {proc.pid: ctx}
        all_procs = []

        # RAM at 90% — would normally force changes
        with patch('psutil.disk_io_counters', return_value={}):
            manage_orchestration(active, system_ram_percent=90.0,
                                 foreground_pid=proc.pid, all_procs=all_procs)

        # nice() setter must not have been called (the mock tracks calls)
        set_calls = [c for c in proc.nice.call_args_list if c.args]
        self.assertEqual(len(set_calls), 0,
            "Orchestration must not call proc.nice(value) on a locked instance")


# ---------------------------------------------------------------------------
# Graduated orchestration
# ---------------------------------------------------------------------------

class TestGraduatedOrchestration(unittest.TestCase):
    def _make_hog(self, name='chrome.exe', nice_val=32):
        p = MagicMock()
        p.pid = 200
        p.info = {'name': name}
        p._nice = nice_val
        p.nice = MagicMock(side_effect=lambda v=None: p._nice if v is None else setattr(p, '_nice', v) or None)
        return p

    def test_gentle_demotion_at_70_percent(self):
        """Between 70% and 85% RAM, hogs get BELOW_NORMAL, not IDLE."""
        import psutil
        BELOW_NORMAL = getattr(psutil, 'BELOW_NORMAL_PRIORITY_CLASS', 16384)
        IDLE = getattr(psutil, 'IDLE_PRIORITY_CLASS', 64)

        hog = self._make_hog()
        all_procs = [hog]

        with patch('vitals_core.empty_working_set', return_value=True):
            manage_orchestration({}, system_ram_percent=75.0,
                                 foreground_pid=None, all_procs=all_procs)

        set_calls = [c.args[0] for c in hog.nice.call_args_list if c.args]
        self.assertTrue(len(set_calls) > 0, "Expected a priority change call")
        # Must NOT have jumped straight to IDLE
        self.assertNotIn(IDLE, set_calls,
            "At 75% RAM, hog should get BELOW_NORMAL, not IDLE")
        self.assertIn(BELOW_NORMAL, set_calls,
            "At 75% RAM, hog should get BELOW_NORMAL")

    def test_aggressive_demotion_at_85_percent(self):
        """Above 85% RAM, hogs get IDLE."""
        import psutil
        IDLE = getattr(psutil, 'IDLE_PRIORITY_CLASS', 64)

        hog = self._make_hog()
        all_procs = [hog]

        with patch('vitals_core.empty_working_set', return_value=True):
            manage_orchestration({}, system_ram_percent=90.0,
                                 foreground_pid=None, all_procs=all_procs)

        set_calls = [c.args[0] for c in hog.nice.call_args_list if c.args]
        self.assertIn(IDLE, set_calls,
            "At 90% RAM, hog must be set to IDLE priority")


# ---------------------------------------------------------------------------
# Action log in render_ui
# ---------------------------------------------------------------------------

class TestActionLog(unittest.TestCase):
    def strip_ansi(self, text):
        import re
        return re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])').sub('', text)

    def test_action_log_entries_appear_in_output(self):
        metrics = {'cpu_percent': 10.0, 'memory_gb': 1.0}
        log = ['[auto] flushed 1.2 GB', '[B] boosted to HIGH']
        output = render_ui(metrics, state=NORMAL, action_log=log)
        self.assertIn('[auto] flushed 1.2 GB', output)
        self.assertIn('[B] boosted to HIGH', output)

    def test_no_action_log_leaves_stable_line_count(self):
        """render_ui with and without action_log must produce same line count."""
        metrics = {'cpu_percent': 10.0, 'memory_gb': 1.0}
        out_no_log = render_ui(metrics, state=NORMAL)
        out_with_log = render_ui(metrics, state=NORMAL,
                                 action_log=['entry1', 'entry2'])
        self.assertEqual(len(out_no_log.split('\n')),
                         len(out_with_log.split('\n')),
                         "Line count must be stable regardless of action_log content")


# ---------------------------------------------------------------------------
# Session timer appears in header
# ---------------------------------------------------------------------------

class TestSessionTimer(unittest.TestCase):
    def strip_ansi(self, text):
        import re
        return re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])').sub('', text)

    def test_session_timer_in_header(self):
        metrics = {'cpu_percent': 5.0, 'memory_gb': 1.0}
        output = render_ui(metrics, state=NORMAL, session_seconds=273)
        plain = self.strip_ansi(output)
        # 273s = 00:04:33
        self.assertIn('00:04:33', plain)

    def test_session_zero_shows_zeroes(self):
        metrics = {'cpu_percent': 5.0, 'memory_gb': 1.0}
        output = render_ui(metrics, state=NORMAL, session_seconds=0)
        plain = self.strip_ansi(output)
        self.assertIn('00:00:00', plain)


if __name__ == '__main__':
    unittest.main()
