# Rocket Flight Computer

## Project

Model rocket flight computer running on Raspberry Pi Zero 2W with two independent processes:

- **Flight Controller** (`flight/`) – sensor readout, logging, flight logic, deployment
- **Dashboard Server** (`dashboard/`) – Flask web UI in avionics glass cockpit style

## Hardware

- **MCU**: Raspberry Pi Zero 2W
- **Power**: Adafruit PowerBoost 1000C + 3.7V LiPo
- **Pressure/Temperature**: BMP280 (I2C 0x77) – in `flight/sensors/bmp280.py`
- **IMU**: MPU-6050 (I2C 0x68) – in `flight/sensors/mpu6050.py`
- **Battery Monitor**: GPIO pin 4 (LBO) – in `flight/sensors/power.py`

## Tech Stack

- Python 3 (PEP 8, type hints)
- Flask (dashboard backend)
- Plain HTML/CSS/JS (no frameworks)
- Three.js r128 (3D visualization via WebGL 1.0)
- SQLite (shared data store between processes)
- systemd services for process management

## Design Spec

Full specification: `docs/superpowers/specs/2026-04-16-rocket-flight-computer-design.md`

## Conventions

- Code comments in English
- No auto-commits without confirmation
- Manual deployment only (git push + SSH)

## 3D Visualization (PRIMARY FLIGHT DISPLAY)

### Overview

The PRIMARY FLIGHT DISPLAY now includes a real-time 3D rocket visualization powered by Three.js. The 3D model responds to sensor data (pitch, roll, yaw) from the MPU-6050 and displays acceleration indicators as directional arrows.

### Architecture

**Files:**

- `dashboard/static/js/rocket3d.js` – Main 3D module (Rocket3D class)
- `dashboard/templates/dashboard.html` – Updated to include 3D container
- `dashboard/static/js/main.js` – Integration and fallback logic
- `dashboard/static/css/cockpit.css` – 3D container styling

**Data Flow:**

1. Flight controller writes sensor readings to SQLite (pitch, roll, yaw, accel_x/y/z in m/s²)
2. Dashboard polls `/api/status` every 500ms (POLL_MS constant)
3. Frontend calls `rocket3d.update(roll, pitch, yaw)` to rotate mesh
4. Frontend calls `rocket3d.updateAcceleration(ax, ay, az)` to scale arrows
5. Three.js renders scene at browser frame rate (~60 FPS)

### Features

**3D Rocket Mesh:**

- Rectangular prism (BoxGeometry, L:W:H ratio 2:0.5:0.3)
- Cyan color (#00ccff) matching dashboard theme
- Phong material for realistic lighting
- Rotation order: YXZ (yaw, pitch, roll)

**Acceleration Arrows:**

- Three colored arrows (X=red, Y=green, Z=blue)
- Arrow length scaled by acceleration magnitude: `length = min(|accel| / 20, 2.0)`
- Arrows only visible when acceleration > 0.3 m/s²
- Dynamic direction based on acceleration sign

**Lighting:**

- Ambient light (0.6 intensity) for even base illumination
- Directional light (0.8 intensity) from (3, 4, 3) for depth perception
- Shadow mapping enabled (PCF shadow)

### Graceful Fallback

If 3D visualization fails to load or render:

1. Try/catch block in `initAttitude()` catches initialization errors
2. Falls back to 2D `AttitudeIndicator` (canvas-based)
3. WebGL context loss detected and triggers fallback
4. Fallback is automatic; user sees functional 2D display

### Performance Considerations

**Pi Zero 2W Optimization:**

- Uses Three.js built-in materials (Lambert/Phong), no custom shaders
- Minimal geometry (single BoxGeometry, three ArrowHelpers)
- No textures or complex models
- Scene memory footprint: <200 KB

**Update Frequency:**

- Data polling: 500ms (2 Hz)
- Scene rendering: Uncoupled from data polling (browser frame rate, typically 60 FPS)
- Smooth rotation between data updates via continuous requestAnimationFrame

**Fallback Performance:**

- 2D canvas rendering is lighter weight; preferred if 3D causes lag
- Set fallback by calling `fallbackTo2D()` in main.js

### Angle Convention

Sensor data from MPU-6050:

- **Roll** (deg): Rotation around forward axis (X), range ±180°
- **Pitch** (deg): Rotation around right-wing axis (Y), range ±90°
- **Yaw** (deg): Rotation around vertical axis (Z), range ±180° (currently always 0.0 without magnetometer)

Three.js applies rotations in order: Yaw → Pitch → Roll (Euler YXZ order).

### Testing

**Manual test:**

```javascript
// In browser console
rocket3d.update(30, 45, 0); // Pitch 30°, Roll 45°
rocket3d.updateAcceleration(5, 10, 20); // Accel X, Y, Z in m/s²
```

**Fallback test:**
Disable Three.js CDN or set `use3D = false` in console; 2D display should appear.
