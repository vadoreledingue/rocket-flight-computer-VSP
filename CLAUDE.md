# Rocket Flight Computer

## Project

Model rocket flight computer running on Raspberry Pi Zero 2W with two independent processes:

- **Flight Controller** (`flight/`) – sensor readout, logging, flight logic, deployment
- **Dashboard Server** (`dashboard/`) – Flask web UI in avionics glass cockpit style

## Tech Stack

- Python 3 (PEP 8, type hints)
- Flask (dashboard backend)
- Plain HTML/CSS/JS (no frameworks)
- SQLite (shared data store between processes)
- systemd services for process management

## Design Spec

Full specification: `docs/superpowers/specs/2026-04-16-rocket-flight-computer-design.md`

## Conventions

- Code comments in English
- No auto-commits without confirmation
- Manual deployment only (git push + SSH)
