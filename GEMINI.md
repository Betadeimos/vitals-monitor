# GEMINI.md - Vitals Project Mandates

## Project Goals
"Vitals" is a lightweight Windows terminal watchdog and time-tracker designed for 3ds Max and other performance-critical processes. Its primary purpose is to:
- **Real-time Monitoring:** Track CPU, RAM, VRAM, and Disk usage spikes in real-time.
- **Predictive Stability:** Analyze resource trends to predict and warn of potential crashes using a two-tier alert system (WARNING/CRITICAL).
- **Time-Tracking:** Accumulate persistent weekly time stats (Working, Hanging, Rendering, Waiting) for productivity analysis.
- **Resource Orchestration:** Dynamically manage OS process priorities (VIP Orchestration) during high RAM pressure to protect active renders.
- **User Experience:** Provide a non-intrusive, high-signal ASCII terminal dashboard for technical artists and developers.

## Strict Rules
All development on this project must adhere to the following principles:

1.  **Simple & Modular Code:** Prioritize readability and maintainability. Components (monitors, stats trackers, orchestrators) must be decoupled and independently testable.
2.  **Terminal-First Interface:** Focus exclusively on ASCII/terminal-based visualizations and text output. No graphical user interfaces (GUIs) are to be implemented.
3.  **Test-Driven Development (TDD):** ALWAYS write tests before implementing a new feature. No feature is considered complete without corresponding unit and integration tests (100% pass rate required).
4.  **Resource Efficiency:** As a watchdog tool, "vitals" itself must have a negligible performance footprint (avoiding expensive per-tick operations) to avoid interfering with 3ds Max.
5.  **Windows-First Architecture:** Leverage Windows APIs (ctypes) for low-level process and window management, while using mocks to ensure testability on other platforms.

## Core Architectural Patterns

### Alert Tiers & States
The system operates as a state machine with the following tiers:
- **NORMAL:** Baseline operation.
- **WARNING:** Triggered by RAM spikes or high CPU usage.
- **CRITICAL:** Triggered by extreme system RAM pressure (>90%); prompts user intervention.
- **HANGING:** Detected via `IsHungAppWindow` for the target process.

### VIP Orchestration
When system RAM exceeds 80%:
- Target process (e.g., foreground Max) is set to **HIGH** priority.
- Background noise (browsers, other instances) is set to **IDLE** priority and their working sets are flushed.
- Priorities are restored once RAM pressure subsides.

### Data Persistence
- Weekly stats are stored in `vitals_stats.json` (gitignored).
- The dashboard displays current week bars and an all-time aggregate.
