import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from vitals_stats import SessionTracker, _current_week_start


class TestSessionTracker(unittest.TestCase):

    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.unlink(self.path)
        self.tracker = SessionTracker(stats_file=self.path)

    def tearDown(self):
        if os.path.exists(self.path):
            os.unlink(self.path)

    def test_starts_empty(self):
        s = self.tracker.summary()
        self.assertEqual(s["working_s"], 0.0)
        self.assertEqual(s["hanging_s"], 0.0)
        self.assertEqual(s["rendering_s"], 0.0)
        self.assertEqual(s["idle_s"], 0.0)
        self.assertEqual(s["billable_s"], 0.0)
        self.assertEqual(s["total_s"], 0.0)
        self.assertEqual(s["crash_count"], 0)
        self.assertEqual(s["session_count"], 0)

    def test_record_tick_normal(self):
        self.tracker.record_tick("NORMAL", False, 0.5)
        self.assertAlmostEqual(self.tracker.summary()["working_s"], 0.5)

    def test_warning_counts_as_working(self):
        self.tracker.record_tick("WARNING", False, 1.0)
        self.assertAlmostEqual(self.tracker.summary()["working_s"], 1.0)

    def test_critical_counts_as_working(self):
        self.tracker.record_tick("CRITICAL", False, 1.0)
        self.assertAlmostEqual(self.tracker.summary()["working_s"], 1.0)

    def test_record_tick_hung(self):
        self.tracker.record_tick("HUNG", False, 1.0)
        s = self.tracker.summary()
        self.assertAlmostEqual(s["hanging_s"], 1.0)
        self.assertEqual(s["working_s"], 0.0)

    def test_hung_takes_precedence_over_render(self):
        self.tracker.record_tick("HUNG", True, 1.0)
        s = self.tracker.summary()
        self.assertAlmostEqual(s["hanging_s"], 1.0)
        self.assertEqual(s["rendering_s"], 0.0)

    def test_hung_takes_precedence_over_render_and_idle(self):
        self.tracker.record_tick("HUNG", True, 2.0, is_idle=True)
        s = self.tracker.summary()
        self.assertAlmostEqual(s["hanging_s"], 2.0)
        self.assertEqual(s["rendering_s"], 0.0)
        self.assertEqual(s["idle_s"], 0.0)

    def test_record_tick_rendering(self):
        self.tracker.record_tick("NORMAL", True, 2.0)
        s = self.tracker.summary()
        self.assertAlmostEqual(s["rendering_s"], 2.0)
        self.assertEqual(s["working_s"], 0.0)

    def test_idle_swallows_normal(self):
        self.tracker.record_tick("NORMAL", False, 5.0, is_idle=True)
        s = self.tracker.summary()
        self.assertAlmostEqual(s["idle_s"], 5.0)
        self.assertEqual(s["working_s"], 0.0)

    def test_hung_beats_idle(self):
        self.tracker.record_tick("HUNG", False, 5.0, is_idle=True)
        s = self.tracker.summary()
        self.assertAlmostEqual(s["hanging_s"], 5.0)
        self.assertEqual(s["idle_s"], 0.0)

    def test_render_takes_precedence_over_idle(self):
        self.tracker.record_tick("NORMAL", True, 3.0, is_idle=True)
        s = self.tracker.summary()
        self.assertAlmostEqual(s["rendering_s"], 3.0)
        self.assertEqual(s["idle_s"], 0.0)

    def test_billable_excludes_render_and_idle(self):
        self.tracker.record_tick("NORMAL", False, 10.0)
        self.tracker.record_tick("HUNG", False, 5.0)
        self.tracker.record_tick("NORMAL", True, 3.0)
        self.tracker.record_tick("NORMAL", False, 8.0, is_idle=True)
        s = self.tracker.summary()
        self.assertAlmostEqual(s["billable_s"], 15.0)
        self.assertAlmostEqual(s["active_s"], 18.0)
        self.assertAlmostEqual(s["total_s"], 26.0)

    def test_exit_hung_counts_as_crash(self):
        self.tracker.record_exit("HUNG")
        self.assertEqual(self.tracker.summary()["crash_count"], 1)

    def test_exit_critical_counts_as_crash(self):
        self.tracker.record_exit("CRITICAL")
        self.assertEqual(self.tracker.summary()["crash_count"], 1)

    def test_exit_normal_does_not_count_as_crash(self):
        self.tracker.record_exit("NORMAL")
        self.assertEqual(self.tracker.summary()["crash_count"], 0)

    def test_exit_warning_does_not_count_as_crash(self):
        self.tracker.record_exit("WARNING")
        self.assertEqual(self.tracker.summary()["crash_count"], 0)

    def test_record_session_start(self):
        self.tracker.record_session_start()
        self.tracker.record_session_start()
        self.assertEqual(self.tracker.summary()["session_count"], 2)

    def test_persistence(self):
        self.tracker.record_tick("HUNG", False, 60.0)
        self.tracker.record_tick("NORMAL", False, 10.0, is_idle=True)
        self.tracker.record_exit("HUNG")
        self.tracker.save()
        t2 = SessionTracker(stats_file=self.path)
        s = t2.summary()
        self.assertAlmostEqual(s["hanging_s"], 60.0)
        self.assertAlmostEqual(s["idle_s"], 10.0)
        self.assertEqual(s["crash_count"], 1)

    def test_new_week_creates_fresh_entry_preserving_old(self):
        old = {
            "weeks": {
                "2020-01-06": {
                    "working_seconds": 9999.0,
                    "hanging_seconds": 500.0,
                    "rendering_seconds": 0.0,
                    "idle_seconds": 1000.0,
                    "crash_count": 10,
                    "session_count": 5,
                }
            }
        }
        with open(self.path, "w") as f:
            json.dump(old, f)
        t = SessionTracker(stats_file=self.path)
        # Current week starts fresh
        s = t.summary()
        self.assertEqual(s["working_s"], 0.0)
        self.assertEqual(s["crash_count"], 0)
        self.assertEqual(s["week_start"], _current_week_start())
        # Old week is still there
        all_w = t.all_weeks()
        old_week = next((w for w in all_w if w["week_start"] == "2020-01-06"), None)
        self.assertIsNotNone(old_week)
        self.assertAlmostEqual(old_week["working_s"], 9999.0)

    def test_migrates_old_flat_format(self):
        old_flat = {
            "week_start": "2020-01-06",
            "working_seconds": 100.0,
            "hanging_seconds": 50.0,
            "rendering_seconds": 0.0,
            "idle_seconds": 0.0,
            "crash_count": 2,
            "session_count": 3,
        }
        with open(self.path, "w") as f:
            json.dump(old_flat, f)
        t = SessionTracker(stats_file=self.path)
        all_w = t.all_weeks()
        # Old data preserved after migration (excluding empty current week)
        old_week = next((w for w in all_w if w["week_start"] == "2020-01-06"), None)
        self.assertIsNotNone(old_week)
        self.assertAlmostEqual(old_week["working_s"], 100.0)
        self.assertEqual(old_week["crash_count"], 2)

    def test_all_weeks_skips_empty(self):
        # Only add data for current week
        self.tracker.record_tick("NORMAL", False, 10.0)
        self.tracker.save()
        weeks = self.tracker.all_weeks()
        self.assertEqual(len(weeks), 1)

    def test_accumulates_across_ticks(self):
        for _ in range(10):
            self.tracker.record_tick("NORMAL", False, 0.5)
        self.assertAlmostEqual(self.tracker.summary()["working_s"], 5.0)


if __name__ == "__main__":
    unittest.main()
