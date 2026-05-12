# Vitals

A lightweight Windows terminal watchdog and time-tracker for 3ds Max.

Vitals does two things in one always-on dashboard:

1. **Live monitoring** — CPU, RAM, VRAM, disk I/O, and "Not Responding" detection for one or more Max instances.
2. **Persistent time tracking** — accumulates how long Max spent **working**, **hanging**, **rendering**, and **waiting**, week by week, and surfaces totals in the UI and via `vitals --report`.

When system RAM crosses 80%, Vitals also orchestrates the OS: it elevates the foreground Max instance to HIGH priority and demotes background Max / Chrome / Edge to IDLE priority to protect an active render.

## Install

```bash
pip install -e .
```

## Run

```bash
vitals                       # Watch for 3dsmax (and max_simulator) by default
vitals <process_name>        # Target any process name
vitals --report              # Print weekly time totals and exit
vitals --report --csv        # Same data as CSV (pipeable to a spreadsheet)
vitals --report --json       # Same data as JSON
```

Optional flags: `--threshold <GB>` (RAM spike sensitivity), `--interval <sec>` (refresh rate). Defaults are read from `vitals_config.json`, which is auto-created on first run.

## What you see

```
+==============================================================================+
|                          V I T A L S   M O N I T O R                         |
+==============================================================================+
|                       INSTANCE: PID 12345 [3ds Max]                          |
|                  [ PRIORITY: Normal       ] [ CORES: 16/16 ]                 |
| CPU          [■■■■■■■-------------------------------]  18.2%                 |
| RAM          [■■■■■■■■■■■■■■■-----------------------]  42.1%                 |
| VRAM [GPU]   [■■■■■-------------------------------- ]  12.4%                 |
| SHARED GPU   [---------------------------------------] 0.00 GB               |
|                       [ STATUS: MONITORING ACTIVE ]                          |
+==============================================================================+
+==============================================================================+
|                    S E S S I O N   T R A C K E R                             |
|                    week of Mon May 11  |  3 sessions                         |
|------------------------------------------------------------------------------|
| > WORKING  [■■■■■■■■■■■■■■■■■■■■■■■■■■■-----]  87.4%  2h 14m                 |
|   WAITING  [■■■---------------------------]   8.3%  12m 04s                  |
|   HANGING  [■■■---------------------------]   4.3%  6m 22s                   |
|------------------------------------------------------------------------------|
|   render: 8m 14s        crashes: 0        lifetime: 2h 41m                   |
|------------------------------------------------------------------------------|
|  all-time:  work 2h 35m  hanging 19m 22s  waiting 12m 04s  s 51  c 0         |
+==============================================================================+
```

The `>` marker shows which bucket the current tick is being recorded into. Priority order: **HANGING > rendering > waiting > working**. Categories are sorted dynamically by duration.


## How tracking works

| Bucket    | Trigger |
|-----------|---------|
| HANGING   | Windows reports the main window as "Not Responding". |
| rendering | Max CPU is above the configured threshold (default 80%), or the window title contains "rendering". |
| waiting   | No Max instance has been the foreground window for `waiting_threshold_seconds`, or it is outside the configured work hours. |
| working   | Anything else, while inside work hours. |

After `waiting_cutoff_seconds` (default 300 s) of continuous waiting, tracking pauses entirely ("away" state) — the dashboard shows a notice and no time is recorded until Max is focused again.

A crash is counted when a process exits while in HANGING or CRITICAL state.

Stats persist to `vitals_stats.json` (gitignored) keyed by week. Historical weeks are never reset; closed weeks just sit alongside the current one and roll into the **all-time** line.

## Work schedule

`vitals_config.json` has a `schedule` block. By default, time outside Mon 01:00 → Sat 00:00 is counted as waiting, regardless of whether Max is in the foreground. Set `"enabled": false` to track 24/7.

## Architecture

- `vitals.py` — terminal UI, main loop, alert state machine, orchestration, `--report` printer, and the `VRAMMonitor` / `StorageMonitor` / `MemoryTracker` helpers.
- `vitals_core.py` — Windows-API integration via ctypes. Process metrics, batch window scan (`get_system_window_map`), `IsHungAppWindow` detection, nvidia-smi + typeperf VRAM, drive-letter mapping.
- `vitals_stats.py` — `SessionTracker` class: weekly JSON store, tick recording with priority rules, week migration, all-time aggregation.
- `vitals_doctor.py` — standalone diagnostic that benchmarks nvidia-smi latency, process-scan cost, and admin permissions.
- `max_simulator.py` — synthetic Max-like process for development testing.

## Tests

```bash
python -m pytest tests/
```

The suite mocks Windows ctypes APIs so it runs on any platform.

## Development mandates

1. **TDD** — tests before implementation.
2. **Simple & modular** — components decoupled and independently testable.
3. **Terminal-first** — ASCII/ANSI only, no GUIs.
4. **Negligible footprint** — the watchdog must not be its own performance problem.
