# Rocket Flight Computer

Flight computer software for a model rocket on Raspberry Pi Zero.

## Components

- **Flight Controller** - Sensor readout, data logging, flight state machine, parachute deployment
- **Dashboard** - Web-based avionics cockpit UI for monitoring and configuration

## Hardware

- Raspberry Pi Zero
- Adafruit PowerBoost 500 + 3.7V LiPo
- BME280 (pressure, temperature, humidity)
- BNO055 (9-DOF orientation)

## Quick Start (Raspberry Pi)

    git clone <your-repo-url> /opt/rocket
    cd /opt/rocket
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    bash scripts/deploy.sh

Dashboard: http://<pi-hostname>.local:8080

## Development (PC)

    pip install -r requirements.txt
    python -m pytest tests/ -v

## Deploy

    # On your PC:
    git push origin main

    # SSH into Pi:
    ssh pi@rocket.local
    cd /opt/rocket && bash scripts/deploy.sh
