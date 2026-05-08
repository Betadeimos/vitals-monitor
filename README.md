# Vitals Monitor

A lightweight terminal watchdog for 3ds Max (and other processes) to monitor CPU, RAM, VRAM, and Disk usage with a focus on crash prediction and system stability.

## Key Features

- **ASCII/ANSI Terminal Interface:** Zero-flicker UI for real-time monitoring.
- **Two-tier Safety Net:** 
    - **Yellow (Stabilize):** Alerts when thresholds are breached.
    - **Red (Kill Switch):** Immediate action for critical system states.
- **"Life Support" Mode:** Automatically throttles CPU affinity and priority for hung processes.
- **Windows API Integration:** Native "Not Responding" detection.
- **Interactive Startup Wizard:** Easy process selection and configuration.
- **Stacked Visual Bars:** Compare system vs. process resource usage at a glance.
- **Global CLI Installation:** Run from anywhere on your system.

## Installation

To install Vitals Monitor in editable mode, run:

```bash
pip install -e .
```

## Usage

You can launch the monitor using the `vitals` command:

```bash
# Launch with the interactive wizard
vitals

# Target a specific process directly
vitals <process_name>
```

## Architecture

Vitals Monitor is built with a modular design and a Test-Driven Development (TDD) approach:

- **`vitals_core.py`:** Handles metric collection, resource monitoring, and process management.
- **`vitals.py`:** Manages the terminal UI, user interaction logic, and the startup wizard.

The project maintains a comprehensive suite of tests to ensure reliability and stability across different system environments.
