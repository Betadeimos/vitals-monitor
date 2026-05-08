# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vitals is a lightweight terminal watchdog for monitoring 3ds Max (and other processes) on Windows. It tracks CPU, RAM, VRAM, and Disk usage with crash prediction via a two-tier alert system and automatic process management.

## Commands

```bash
# Install in editable mode
pip install -e .

# Run the monitor
vitals                    # Interactive wizard mode
vitals <process_name>     # Target a specific process directly

# Run all tests
python -m pytest tests/

# Run a single test file
python -m pytest tests/test_vitals_core.py

# Run the diagnostic tool
python vitals_doctor.py
```

## Architecture

**Entry point:** `vitals.py:main()` → `start_monitoring()` (line 901)

### Module responsibilities

- **`vitals.py`** — Terminal UI, user interaction, startup wizard, and the main monitoring loop. Contains the `VRAMMonitor` and `StorageMonitor` daemon threads, `MemoryTracker` (deque-based sliding window spike detection), `determine_state()`, `render_ui()`, and `manage_orchestration()`.
- **`vitals_core.py`** — Windows API integration (ctypes), process metrics collection, drive mapping, and system diagnostics. Contains `find_processes()`, `get_process_metrics()`, `get_system_window_map()`, `is_process_responding()`, `attempt_rescue()`, `get_vram_metrics()`, and `get_storage_metrics()`.
- **`vitals_doctor.py`** — Standalone diagnostic tool that benchmarks nvidia-smi latency, process scan cost, and admin permission availability.

### Main loop data flow (500 ms refresh)

1. `psutil.process_iter()` → all processes
2. `get_system_window_map()` → single batch pass for `IsHungAppWindow` state
3. `find_processes()` → lazy-filter for target (cmdline fetched only for Python processes)
4. Per-process: `get_process_metrics()` → `MemoryTracker.add_reading()` → `determine_state()`
5. Async daemon threads supply VRAM (every 2 s) and disk I/O (every 1 s)
6. `render_ui()` → ANSI stacked bars output
7. `manage_orchestration()` (`vitals.py:535`) → demote background tasks when foreground render is active
8. On HUNG/CRITICAL state → prompt user to kill (Y) or clear spike history and continue (N)

### Alert tiers

| State    | Trigger |
|----------|---------|
| NORMAL   | Baseline |
| WARNING  | RAM spike OR CPU > threshold |
| CRITICAL | System RAM > 90% (forces user decision) |
| HUNG     | Windows "Not Responding" detected |

### Configuration (`vitals_config.json`)

Loaded at startup; missing file is auto-created with defaults. Key sections: `tier1` (CPU/RAM spike thresholds), `tier2` (system RAM %), `tier3` (cores to strip from affinity), `monitoring` (refresh intervals).

### Test organization

Tests live in `tests/`. Many test files have versioned siblings (e.g., `test_vitals_core.py`, `test_vitals_core_v2.py`, `test_vitals_core_v3.py`) — the highest-versioned file is the current suite for that module. Tests mock Windows-only ctypes APIs via `@patch('vitals_core.ctypes', ...)` to run on any platform.

## Development Mandates (from GEMINI.md)

1. **TDD:** Always write tests before implementing a feature. No feature is complete without tests.
2. **Simple & Modular:** Components must be decoupled and independently testable.
3. **Terminal-First:** No GUIs. ASCII/ANSI output only.
4. **Resource Efficiency:** The watchdog must have negligible performance footprint — avoid introducing overhead to the monitoring loop.
