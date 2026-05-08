# GEMINI.md - Vitals Project Mandates

## Project Goals
"Vitals" is a lightweight terminal watchdog tool designed for 3ds Max. Its primary purpose is to:
- Monitor memory and CPU usage spikes in real-time.
- Analyze resource trends to predict and warn of potential 3ds Max crashes.
- Provide a non-intrusive, high-signal monitoring experience for technical artists and developers.

## Strict Rules
All development on this project must adhere to the following principles:

1.  **Simple & Modular Code:** Prioritize readability and maintainability. Components (monitors, loggers, predictors) should be decoupled and independently testable.
2.  **Terminal-First Interface:** Focus on ASCII/terminal-based visualizations and text output. No graphical user interfaces (GUIs) are to be implemented unless explicitly requested.
3.  **Test-Driven Development (TDD):** ALWAYS write tests before implementing a new feature. No feature is considered complete without corresponding unit and integration tests.
4.  **Resource Efficiency:** As a watchdog tool, "vitals" itself must have a negligible performance footprint to avoid interfering with 3ds Max operations.
