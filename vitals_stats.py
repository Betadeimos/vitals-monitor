import json
import os
import time
from datetime import date, timedelta


def _current_week_start():
    today = date.today()
    return (today - timedelta(days=today.weekday())).isoformat()


def _blank_week():
    return {
        "working_seconds": 0.0,
        "hanging_seconds": 0.0,
        "rendering_seconds": 0.0,
        "idle_seconds": 0.0,
        "crash_count": 0,
        "session_count": 0,
    }


class SessionTracker:
    def __init__(self, stats_file="vitals_stats.json"):
        self.stats_file = stats_file
        self._store = self._load()
        self._week = self._current_week_dict()
        self._last_save = time.monotonic()

    # ── persistence ───────────────────────────────────────────────────────────

    def _load(self):
        try:
            with open(self.stats_file) as f:
                data = json.load(f)
            if "weeks" not in data:
                # Migrate old flat format — preserve whatever was there
                old_key = data.get("week_start")
                old_data = {k: data[k] for k in _blank_week() if k in data}
                weeks = {old_key: old_data} if old_key else {}
                return {"weeks": weeks}
            return data
        except (FileNotFoundError, json.JSONDecodeError):
            return {"weeks": {}}

    def _current_week_dict(self):
        key = _current_week_start()
        if key not in self._store["weeks"]:
            self._store["weeks"][key] = _blank_week()
        else:
            for k, v in _blank_week().items():
                self._store["weeks"][key].setdefault(k, v)
        return self._store["weeks"][key]

    def save(self):
        try:
            with open(self.stats_file, "w") as f:
                json.dump(self._store, f, indent=2)
            self._last_save = time.monotonic()
        except OSError:
            pass

    # ── recording ─────────────────────────────────────────────────────────────

    def record_session_start(self):
        self._week["session_count"] += 1
        self.save()

    def record_tick(self, state, is_rendering, interval_s, is_idle=False):
        if state == "HUNG":
            self._week["hanging_seconds"] += interval_s
        elif is_rendering:
            self._week["rendering_seconds"] += interval_s
        elif is_idle:
            self._week["idle_seconds"] += interval_s
        else:
            self._week["working_seconds"] += interval_s
        if time.monotonic() - self._last_save >= 30:
            self.save()

    def record_exit(self, last_state):
        """Count as a crash only if Max was already hung or critically unstable."""
        if last_state in ("HUNG", "CRITICAL"):
            self._week["crash_count"] += 1
            self.save()

    # ── querying ──────────────────────────────────────────────────────────────

    def _summarise_week(self, week_data, week_start):
        billable = week_data["working_seconds"] + week_data["hanging_seconds"]
        active   = billable + week_data["rendering_seconds"]
        total    = active + week_data.get("idle_seconds", 0.0)
        return {
            "week_start":    week_start,
            "working_s":     week_data["working_seconds"],
            "hanging_s":     week_data["hanging_seconds"],
            "rendering_s":   week_data["rendering_seconds"],
            "idle_s":        week_data.get("idle_seconds", 0.0),
            "billable_s":    billable,
            "active_s":      active,
            "total_s":       total,
            "crash_count":   week_data["crash_count"],
            "session_count": week_data["session_count"],
        }

    def summary(self):
        """Current week + all-time totals, for the live UI."""
        s = self._summarise_week(self._week, _current_week_start())
        totals = {"working_s": 0.0, "hanging_s": 0.0, "rendering_s": 0.0,
                  "idle_s": 0.0, "crash_count": 0, "session_count": 0}
        for data in self._store["weeks"].values():
            for k, v in _blank_week().items():
                data.setdefault(k, v)
            totals["working_s"]    += data["working_seconds"]
            totals["hanging_s"]    += data["hanging_seconds"]
            totals["rendering_s"]  += data["rendering_seconds"]
            totals["idle_s"]       += data["idle_seconds"]
            totals["crash_count"]  += data["crash_count"]
            totals["session_count"]+= data["session_count"]
        totals["billable_s"] = totals["working_s"] + totals["hanging_s"]
        totals["active_s"]   = totals["billable_s"] + totals["rendering_s"]
        totals["total_s"]    = totals["active_s"] + totals["idle_s"]
        s["all_time"] = totals
        return s

    def all_weeks(self):
        """All weeks with data, sorted oldest-first."""
        result = []
        for ws, data in self._store["weeks"].items():
            s = self._summarise_week(data, ws)
            if s["total_s"] == 0 and s["crash_count"] == 0 and s["session_count"] == 0:
                continue
            result.append(s)
        result.sort(key=lambda x: x["week_start"])
        return result
