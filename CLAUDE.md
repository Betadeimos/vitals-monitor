# CLAUDE.md

Guidance for Claude Code when working in this repo.

## Project overview

Vitals is a Windows terminal watchdog **and time-tracker** for 3ds Max (and other processes). It tracks CPU, RAM, VRAM, and Disk usage with a two-tier alert system, accumulates persistent weekly time stats (working / hung / rendering / idle), and orchestrates OS priorities under RAM pressure to protect an active render.

## Commands

```bash
# Install in editable mode
pip install -e .

# Run the monitor
vitals                    # Default: search for 3dsmax / max_simulator
vitals <process_name>     # Target a specific process

# Print weekly time report
vitals --report

# Run the test suite
python -m pytest tests/

# Run the diagnostic tool
python vitals_doctor.py
```

## Module map

- **`vitals.py`** — Terminal UI, main monitor loop, alert state machine (`determine_state`), orchestration (`manage_orchestration`), VRAM/Storage daemons, `MemoryTracker` (deque sliding window), `_render_stats_box` / `_render_time_box`, `print_report()`, `_is_work_hours()`, and the `vitals` console entry point.
- **`vitals_core.py`** — Windows API integration via ctypes. `find_processes`, `get_process_metrics`, `get_system_window_map` (single batch pass over all top-level windows), `is_process_responding` (`IsHungAppWindow`), `get_vram_metrics` (nvidia-smi + typeperf for shared-GPU bleed), `get_storage_metrics`, drive mapping, `get_foreground_pid`.
- **`vitals_stats.py`** — `SessionTracker`: weekly JSON persistence (`vitals_stats.json`), tick recording with bucket priority, exit-as-crash logic, week migration from old flat format, all-time aggregation in `summary()`.
- **`vitals_doctor.py`** — Standalone diagnostic that benchmarks nvidia-smi latency, process scan cost, and admin permissions.
- **`max_simulator.py`** — Synthetic Max-like workload for testing.

## Main loop data flow (default 500 ms tick)

1. `psutil.process_iter(['pid','name'])` → cheap list of all processes (no cmdline).
2. `vitals_core.get_system_window_map()` → one batch pass returning `{pid: {title, is_responding}}`.
3. `vitals_core.find_processes()` → filter for target (cmdline fetched lazily, only for Python processes).
4. For each active instance: `get_process_metrics` → `MemoryTracker.add_reading` → `determine_state`.
5. Async daemons supply VRAM (every 2 s) and disk I/O (every 1 s) without blocking the loop.
6. **VIP orchestration:** when system RAM > 80%, foreground Max → HIGH priority, background Max / Chrome / Edge → IDLE priority + working-set flush. Restored when pressure drops.
7. **Tick classification** (priority order — also the order of the `>` indicator in the UI):
   - HUNG (any instance not responding)
   - rendering (CPU > threshold, or title contains "rendering")
   - idle (no Max foreground for `idle_threshold_minutes`, OR outside work hours)
   - working
8. `stats_tracker.record_tick(...)` accumulates seconds into the current week's bucket.
9. `render_ui(...)` emits the stacked-bar dashboard, session tracker box, and time-breakdown box.
10. On CRITICAL (system RAM > 90%) → prompt to kill (Y) or clear spike history (N).
11. On process exit while last state was HUNG/CRITICAL → `record_exit` increments crash count.

## Alert tiers

| State    | Trigger                                                       |
|----------|---------------------------------------------------------------|
| NORMAL   | Baseline.                                                     |
| WARNING  | RAM spike (`tier1.ram_spike_threshold_gb` in window) OR CPU > `tier1.cpu_threshold_percent`. |
| CRITICAL | System RAM > `tier2.system_ram_threshold_percent`. Prompts the user. |
| HUNG     | `IsHungAppWindow` returns true for the main window.           |

## Configuration

`vitals_config.json` is auto-created on first run from `DEFAULT_CONFIG` in `vitals.py`. Sections:

- `tier1` — CPU and RAM-spike thresholds.
- `tier2` — system-RAM CRITICAL threshold and window.
- `tier3` — affinity cores to strip (legacy; not currently applied automatically).
- `monitoring` — `refresh_interval_seconds`, `vram_monitor_interval_seconds`, `memory_tracker_window_size_seconds`, `idle_threshold_minutes`.
- `schedule` — `enabled`, `work_start_weekday/hour`, `work_end_weekday/hour`. Outside this window, ticks count as idle.

## Stats persistence (`vitals_stats.json`)

Gitignored — it's user-specific accumulated data. Format:

```json
{
  "weeks": {
    "2026-05-11": {
      "working_seconds": 0.0,
      "hanging_seconds": 0.0,
      "rendering_seconds": 0.0,
      "idle_seconds": 0.0,
      "crash_count": 0,
      "session_count": 0
    }
  }
}
```

Keys are ISO Monday-of-week strings. Old weeks are **never** deleted — the UI surfaces the current week's bars and an **all-time** line aggregating every week. `SessionTracker._load` migrates legacy flat-format files transparently.

## Tests

Tests live in `tests/`. Some files have versioned siblings (`_v2`, `_v3`) — the highest-versioned is current for that module. Windows-only ctypes are mocked so the suite runs on any platform.

Current suite: 124 tests, all passing.

## Development mandates

1. **TDD** — write tests before features. No feature is complete without tests.
2. **Simple & modular** — components decoupled and independently testable.
3. **Terminal-first** — ASCII/ANSI only, no GUIs.
4. **Negligible footprint** — the watchdog must not be its own performance problem; avoid adding work to the per-tick path.
