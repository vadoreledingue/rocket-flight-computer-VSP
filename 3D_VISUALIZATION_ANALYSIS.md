# 3D Rocket Visualization Component - Phase 1-3 Analysis

## Phase 1: Code Exploration Summary

### Dashboard Architecture

**Data Flow:**

1. Flight controller (flight/main.py) samples sensors at high frequency (100+ Hz during flight)
2. Data persisted to SQLite via `insert_reading()` with Unix epoch timestamps
3. Dashboard frontend polls `/api/status` **every 500ms** (POLL_MS constant in main.js)
4. Single latest reading returned as JSON
5. Frontend updates via vanilla JavaScript (no framework)

**Current Attitude Display:**

- Located in `#attitude-container` (PRIMARY FLIGHT DISPLAY, center panel)
- Currently: 2D canvas element (300px × 300px) with `AttitudeIndicator` class
- Displays: Pitch and Roll only (rotation via canvas 2D transforms)
- Yaw: Not currently displayed (always 0.0 in sensor data)
- Rendering: Lightweight 2D canvas with SVG-like shapes (horizon lines, pitch markers)

**Real-time Update Mechanism:**

- **Polling, not WebSockets**: Frontend uses `fetch()` polling at 500ms intervals
- **No live push**: Changes driven entirely by client-side polling
- **Pro**: Simple, stateless, works on low-bandwidth networks
- **Con**: 500ms update latency (acceptable for flight display)

**API Endpoints Used:**

- `/api/status` → Latest single reading (roll, pitch, yaw, accel_x/y/z, altitude, vspeed, etc.)
- `/api/history?seconds=60` → 60-second history for charts
- No dedicated 3D endpoint needed (use existing `/api/status`)

---

### Sensor Data Format & Precision

**MPU-6050 (6-Axis IMU):**

- **Roll/Pitch**: Computed from accelerometer via `atan2()`, returned in **degrees** (-90 to +90 range for pitch, -180 to +180 for roll)
  - Calculation: `pitch = atan2(ax_g, sqrt(ay_g² + az_g²))` where `ax_g = ax / 9.81`
  - Formula file: `flight/sensors/mpu6050.py` lines 47-62
- **Yaw**: Always **0.0** (gyro integration not implemented; no magnetometer)
- **Accelerations**: X/Y/Z in **m/s²** (±2g scale with 16384 LSB/g)
  - Conversion: raw_counts / 16384.0 = m/s²
  - Real-time data includes gravity (9.81 m/s² on Z when level)
- **Update Frequency**: Sensor read every frame of flight controller tick (appears to be ~50-100 Hz based on "100+ rows/sec")
- **Precision**: Float values, typically 2-4 decimal places in database

**BMP-280 (Pressure/Temp):**

- Pressure (hPa), Temperature (°C)
- Not needed for 3D rotation but useful for context

**Data Lifecycle:**

```
Sensor → Flight Controller (main.py tick())
  → SQLite readings table
  → Dashboard /api/status endpoint
  → Frontend poll every 500ms
  → AttitudeIndicator.update(roll, pitch)
```

---

### Database Schema & Query Patterns

**Relevant Table: `readings`**

```sql
CREATE TABLE readings (
    id, flight_id, timestamp (REAL unix epoch),
    pressure, temperature, humidity,
    altitude, vspeed,
    roll, pitch, yaw,
    accel_x, accel_y, accel_z,
    battery_pct, battery_v, state
);
```

**Dashboard Queries:**

1. `get_latest_readings(count=1)` → Returns dict with all columns, most recent first
2. `get_readings_since(since_timestamp)` → For 60-second history charts

**Key Insight:**

- Latest reading includes **all** needed data in one row (roll, pitch, yaw, accel_x/y/z)
- No joins needed; single SELECT delivers complete state
- Accelerations stored as-is (m/s²); no unit conversion needed on frontend

---

### Performance Constraints

**Target Hardware: Raspberry Pi Zero 2W**

- **CPU**: ARM Cortex-A53 (4×1.0 GHz, though Pi Zero 2W = 2 cores @ 1.0 GHz)
- **RAM**: 512 MB (shared with OS, Flask, and flight controller)
- **GPU**: VideoCore IV (limited 3D capability, no WebGL 2.0)
- **Browser**: Chromium/Epiphany (both available, WebGL 1.0 supported)

**Current System State:**

- Flask running on port 8080 (low overhead)
- Flight controller in separate process (uses `multiprocessing` or `systemd` service)
- SQLite with WAL mode enabled (concurrent reader/writer support)
- Dashboard polling every 500ms = 2 frames/sec effective UI update rate

**GPU/WebGL Availability:**

- Pi Zero 2W **has** VideoCore IV GPU
- WebGL 1.0 available on modern Chromium
- Hardware acceleration works if browser is configured for it
- Canvas 2D is fallback (already proven working)

**Constraints for 3D:**

- **Memory**: 512 MB total (flight + dashboard share) → Must keep 3D scene lightweight
- **Rendering Budget**: 16.7ms per frame @ 60 Hz; more realistic 33ms @ 30 Hz on Pi Zero 2W
- **Library Size**: Minimal JavaScript dependencies (project uses no frameworks currently)
- **Update Frequency**: 500ms polling = 2 Hz effective scene update (not real-time 60 Hz)

---

### Current Technology Stack

**Frontend:**

- HTML5 (no templating framework)
- CSS3 (custom properties, flexbox, grid)
- Vanilla JavaScript (no React/Vue/Angular)
- Chart.js v4.4.0 (for altitude/acceleration charts)
- Canvas 2D API (current attitude indicator)

**Backend:**

- Flask (Python web framework)
- SQLite (data persistence, WAL mode enabled)
- No WebSockets (synchronous request/response only)

**Python Libraries (requirements.txt):**

- Adafruit drivers (Blinka, BMP280, no official Three.js equivalent)
- mpu6050-raspberrypi (lightweight I2C sensor driver)
- No 3D libraries currently (would need to add)

---

### Design Spec Reference

**From docs/superpowers/specs/2026-04-16-rocket-flight-computer-design.md:**

- PRIMARY FLIGHT DISPLAY is critical for in-flight decisions
- Must display attitude reliably and with minimal latency
- No mention of 3D (current design is 2D)
- Fallback requirement: System must remain usable if 3D fails

---

## Phase 2: Technical Architecture Recommendation

### Recommended Technology Stack

#### 3D Library: **Three.js** (Lightweight WebGL)

**Choice: Three.js over alternatives**

| Criterion             | Three.js                    | Babylon.js      | Raw WebGL             | Cesium.js           |
| --------------------- | --------------------------- | --------------- | --------------------- | ------------------- |
| **File Size**         | ~150KB (minified)           | ~500KB          | 0 KB (raw)            | 2+ MB               |
| **GPU Support**       | WebGL 1.0 + 2.0             | WebGL 1.0 + 2.0 | Requires write shader | WebGL 2.0 only      |
| **Ease of Use**       | High (abstractions)         | Very High       | Steep learning curve  | Very High (complex) |
| **Pi Zero 2W Compat** | ✅ Yes (WebGL 1.0)          | ✅ Yes          | ✅ Yes                | ⚠️ Overkill, heavy  |
| **Maintenance**       | ✅ Active (1000+ GH issues) | ✅ Active       | ❌ Manual updates     | ✅ Active           |
| **Documentation**     | ✅ Excellent                | ✅ Excellent    | ⚠️ Sparse             | ✅ Excellent        |
| **Dependency Chain**  | ✅ None (standalone)        | ✅ None         | N/A                   | Many                |

**Justification:**

1. **WebGL 1.0 support**: Three.js renders via WebGL 1.0 fallback on Pi Zero 2W (Babylon.js can too, but heavier)
2. **File size**: 150KB < Babylon's 500KB; critical on Pi Zero 2W with limited RAM/network
3. **Proven on embedded**: Three.js widely used in Raspberry Pi projects (astronomy, robotics, aerospace)
4. **Minimal dependencies**: CDN delivery, no build step required
5. **Fallback graceful**: If Three.js fails to load, can revert to 2D AttitudeIndicator via try/catch

**Loading Strategy:**

```javascript
// Load from CDN (or serve locally if bandwidth-critical)
<script src="https://cdn.jsdelivr.net/npm/three@r128/build/three.min.js"></script>
// Fallback: If Three.js load fails, AttitudeIndicator takes over
```

---

### Data Binding Mechanism: **Polling (existing, no change)**

**Decision: Extend existing 500ms polling**

Current polling at 500ms (2 Hz) is **sufficient** for flight display:

- Attitude changes smoothly (no jerk)
- Latency < 1 second (acceptable for ballistic trajectory)
- Avoids WebSocket complexity on Pi Zero 2W

**Data Flow:**

```
Frontend fetch() every 500ms
  ↓
/api/status returns latest reading
  ↓
JavaScript updates 3D model via three.js
  ↓
Scene.render() happens at browser's frame rate (60 FPS, uncoupled from data updates)
```

**Animation Strategy:**

- **Data Update**: 500ms polling (2 Hz)
- **Scene Rendering**: Continuous requestAnimationFrame (60 FPS)
- **Interpolation**: Optional smooth transition between polled attitudes (0.5s easing)

---

### 3D Model Architecture

#### Rocket Body Representation

**3D Prism Model:**

- **Geometry**: BoxGeometry (rectangular rocket body, ~2:1:0.3 ratio L:W:H)
- **Texture/Material**:
  - Simple Lambert or Phong material (WebGL 1.0 compatible)
  - Option 1: Flat color (cyan #00ccff to match dashboard theme)
  - Option 2: Simple texture (striped or weathered look)
  - Option 3: Gradient (top to bottom, simulating lighting)
- **Lighting**: Single directional light + ambient light (essential for 3D depth perception)
- **Camera**: Isometric or slight 3/4 perspective (not first-person)

**Coordinate System Mapping:**

```
Three.js rotations (radians) ← Dashboard angles (degrees)

Euler order: ZYX (yaw, pitch, roll)
- Roll (Z-axis): Rotate around forward axis (currently active from MPU6050)
- Pitch (X-axis): Rotate around right-wing axis (currently active)
- Yaw (Y-axis): Rotate around vertical axis (currently 0.0, reserved for future magnetometer)

Conversion:
  yaw_rad   = yaw_deg * (π/180)
  pitch_rad = pitch_deg * (π/180)
  roll_rad  = roll_deg * (π/180)
  object.rotation.order = 'YXZ'
  object.rotation.y = yaw_rad
  object.rotation.x = pitch_rad
  object.rotation.z = roll_rad
```

---

#### Acceleration Indicator Arrows

**3D Arrows on Rocket Faces:**

- **One arrow per axis** (X, Y, Z) pointing from center of rocket
- **Arrow properties:**
  - Base: 3D cones or arrow helpers (Three.js `ArrowHelper`)
  - **Color per axis:**
    - X (accel_x): Red (#ff0000)
    - Y (accel_y): Green (#00ff00)
    - Z (accel_z): Blue (#0000ff)
  - **Length**: Proportional to acceleration magnitude
    - Formula: `arrow_length = min(accel_magnitude / 20, 2.0)` (caps at 2× rocket length)
    - Scales from 0 to ~2m for accelerations 0 to 40 m/s² (0-4g)
  - **Thickness/Opacity**: Optional dynamic scaling by magnitude

**Alternative: 2D HUD Layer**

- Instead of 3D arrows in scene, overlay 2D canvas on top
- Shows acceleration gauges (three circles with radial fills)
- Simpler rendering, guaranteed performance

---

### Performance Optimization Strategy

#### LOD (Level of Detail):

- **High (target 60 FPS)**: Full rocket mesh, 3 arrow helpers, ambient + directional light
- **Medium (target 30 FPS)**: Simplified rocket (cube), 3 arrows, lower-res shadows
- **Low (target 15 FPS)**: Wireframe rocket, no arrows, single light

**Auto-detection:**

```javascript
requestAnimationFrame(tick);
// Measure frame time, if drops below 30 FPS, reduce LOD
```

#### Asset Optimization:

- **Mesh**: Use built-in Three.js primitives (no external model files)
- **Textures**: None initially; flat colors (1 texture = negligible)
- **Shaders**: Use Three.js built-in materials (Lambert, Phong) → compiled to WebGL 1.0

#### Update Batching:

- 500ms polling → Batch model updates into single scene update
- No per-frame recalculations; only when data changes

#### Memory Budget:

- Three.js core: ~150 KB
- Rocket mesh: <1 KB (geometry buffer)
- Scene graph: <10 KB (lights, camera, objects)
- **Total**: <200 KB (acceptable on Pi Zero 2W)

---

### Graceful Fallback Mechanism

**If 3D rendering fails:**

1. Catch Three.js load error → Revert to existing 2D `AttitudeIndicator`
2. Catch WebGL context loss → Switch to Canvas 2D rendering
3. User sees functional attitude display (2D) instead of broken 3D

**Implementation:**

```javascript
try {
  initThreeJS();
  use3DRenderer();
} catch (e) {
  console.warn("3D failed, falling back to 2D:", e);
  use2DAttitudeIndicator();
}
```

---

### Proposed Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ Primary Flight Display Container (#pfd-container)               │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────┐  ┌────────────────────────┐  ┌──────────────┐ │
│  │     ALT      │  │   3D Rocket Attitude   │  │      VS      │ │
│  │  (existing)  │  │                        │  │  (existing)  │ │
│  │              │  │  ┌──────────────────┐  │  │              │ │
│  │   0.0 m      │  │  │                  │  │  │   0.0 m/s    │ │
│  │              │  │  │   Three.js       │  │  │              │ │
│  │              │  │  │   WebGL Scene    │  │  │              │ │
│  │              │  │  │                  │  │  │              │ │
│  │              │  │  │  - Rocket mesh   │  │  │              │ │
│  │              │  │  │  - 3× arrows     │  │  │              │ │
│  │              │  │  │  - Lights        │  │  │              │ │
│  │              │  │  │                  │  │  │              │ │
│  │              │  │  └──────────────────┘  │  │              │ │
│  │              │  │  Fallback: 2D Canvas   │  │              │ │
│  └──────────────┘  └────────────────────────┘  └──────────────┘ │
│                                                                   │
│ Updates from /api/status every 500ms                             │
│ Scene renders continuously at browser frame rate (60 FPS)        │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 3: Implementation Plan

### Phased Milestones

#### **Milestone 1: Foundation & Setup**

**Objective**: Establish 3D rendering capability without breaking existing 2D display

**Tasks:**

1. **Create `dashboard/static/js/rocket3d.js`** (new file)
   - Three.js initialization function
   - Scene, camera, renderer setup
   - Rocket mesh creation
   - Light setup
   - Acceptance: Scene renders with rotating rocket (manual angle input for testing)

2. **Update `dashboard/templates/dashboard.html`**
   - Add Three.js CDN script tag (before main.js)
   - Replace `<canvas id="attitude-canvas"></canvas>` with `<div id="pfd-3d-container"></div>`
   - Keep backup: `<canvas id="attitude-canvas-2d" style="display:none;"></canvas>` for fallback
   - Acceptance: Page loads without console errors

3. **Update `dashboard/static/js/main.js`**
   - Import Rocket3D class
   - Add try/catch wrapper around 3D initialization
   - Acceptance: AttitudeIndicator is replaced; 2D still available if error caught

**Estimated Effort**: 2-3 hours

---

#### **Milestone 2: Data Binding & Real-Time Updates**

**Objective**: Connect 3D model to live sensor data

**Tasks:**

1. **Extend `rocket3d.js` with `update()` method**
   - Accept roll, pitch, yaw in degrees
   - Convert to radians
   - Apply to object3d.rotation
   - Acceptance: Updating with sensor data rotates rocket smoothly

2. **Update `dashboard/static/js/main.js`**
   - Call `rocket3d.update(data.roll, data.pitch, data.yaw)` in `updateDashboard()`
   - Acceptance: 3D rocket rotates with each poll (500ms updates visible)

3. **Test on real sensor data**
   - Run flight controller + dashboard
   - Verify attitude tracking matches 2D display
   - Acceptance: 3D and 2D attitudes match within 1°

**Estimated Effort**: 1-2 hours

---

#### **Milestone 3: Acceleration Indicators (Arrows)**

**Objective**: Add dynamic 3D acceleration arrows

**Tasks:**

1. **Extend `rocket3d.js` with `updateAcceleration()` method**
   - Accept accel_x, accel_y, accel_z in m/s²
   - Create/update three `ArrowHelper` objects (one per axis)
   - Scale arrow length by magnitude: `length = min(mag / 20, 2.0)`
   - Acceptance: Arrows appear/scale with acceleration input

2. **Update `dashboard/static/js/main.js`**
   - Call `rocket3d.updateAcceleration(data.accel_x, data.accel_y, data.accel_z)` in `updateDashboard()`
   - Acceptance: Arrows respond to simulated/real acceleration data

3. **Visual tuning**
   - Adjust arrow colors, scale factors, opacity
   - Acceptance: Arrows visible, not distracting, proportional to magnitude

**Estimated Effort**: 2-3 hours

---

#### **Milestone 4: Styling & Theme Integration**

**Objective**: Match dashboard cockpit theme

**Tasks:**

1. **Update `rocket3d.js` materials**
   - Rocket body: Cyan (#00ccff) or gradient
   - Lights: Tuned for cockpit aesthetic
   - Acceptance: Visually cohesive with existing dashboard

2. **Responsive canvas sizing**
   - Size 3D container to match old `#attitude-canvas` dimensions (300×300)
   - Maintain aspect ratio on resize
   - Acceptance: Container responds to window resize

3. **CSS updates in `dashboard/static/css/cockpit.css`**
   - Replace `#attitude-canvas` styles with `#pfd-3d-container`
   - Acceptance: Layout unchanged; 3D fills same space

**Estimated Effort**: 1-2 hours

---

#### **Milestone 5: Performance Testing & Optimization**

**Objective**: Verify performance on Pi Zero 2W

**Tasks:**

1. **Deploy to target Pi Zero 2W**
   - SSH into device
   - Run dashboard server
   - Open browser, verify 3D renders
   - Acceptance: No crashes; frame rate > 30 FPS (use Chrome DevTools)

2. **Measure CPU/Memory**
   - Monitor `top` during flight simulation
   - Check Three.js overhead
   - Acceptance: CPU < 50% idle, < 80% during flight; Memory stable

3. **LOD implementation (if needed)**
   - If frame rate drops below 30 FPS, implement LOD reduction
   - Acceptance: Frame rate stays >= 30 FPS under load

**Estimated Effort**: 2-3 hours

---

#### **Milestone 6: Graceful Fallback & Error Handling**

**Objective**: Ensure robustness; dashboard remains usable if 3D fails

**Tasks:**

1. **Implement fallback in `dashboard/static/js/main.js`**
   - Try 3D initialization; catch exceptions
   - On failure: unhide 2D canvas, re-initialize `AttitudeIndicator`
   - Log error to console for debugging
   - Acceptance: If Three.js fails to load, 2D attitude display appears automatically

2. **Test failure scenarios**
   - Disable Three.js CDN (simulate network failure)
   - Verify 2D fallback activates
   - Acceptance: Dashboard functional (2D only) without 3D

3. **WebGL context loss handling**
   - Add context loss listener to Three.js renderer
   - Fallback to 2D on context loss
   - Acceptance: No black screen; graceful recovery

**Estimated Effort**: 1-2 hours

---

#### **Milestone 7: Testing & Validation**

**Objective**: End-to-end verification

**Tasks:**

1. **Manual flight test (if available)**
   - Launch model rocket with flight computer
   - Verify 3D attitude tracks real attitude
   - Verify arrows scale with acceleration
   - Acceptance: 3D display accurate throughout flight

2. **Simulation testing**
   - Create mock data generator (pitch/roll/yaw sweeps, acceleration pulses)
   - Run dashboard against mock data
   - Verify all features work
   - Acceptance: 3D responds correctly to test cases

3. **Browser compatibility**
   - Test on Chromium (Pi Zero 2W primary browser)
   - Test on Firefox (fallback browser)
   - Acceptance: Works on both; graceful fallback if needed

4. **Documentation**
   - Update CLAUDE.md with 3D feature description
   - Add comments to `rocket3d.js` for maintainability
   - Acceptance: README updated

**Estimated Effort**: 2-3 hours

---

### File Modifications Summary

| File                                 | Change                                          | Lines | Effort |
| ------------------------------------ | ----------------------------------------------- | ----- | ------ |
| `dashboard/static/js/rocket3d.js`    | **CREATE**                                      | ~300  | New    |
| `dashboard/templates/dashboard.html` | Modify `#attitude-container`                    | 2-5   | 10 min |
| `dashboard/static/js/main.js`        | Add 3D calls + fallback                         | 15-20 | 30 min |
| `dashboard/static/css/cockpit.css`   | Update `#attitude-canvas` → `#pfd-3d-container` | 2-3   | 5 min  |
| `CLAUDE.md`                          | Document 3D feature                             | 5-10  | 10 min |

**Total New/Modified Lines**: ~350 lines

---

### Testing Strategy

#### Unit Tests:

- Angle conversion (degrees ↔ radians)
- Arrow scaling calculations
- Fallback activation

#### Integration Tests:

- 3D rendering with real `/api/status` data
- Data binding (poll → update cycle)
- Fallback behavior

#### Performance Tests:

- Frame rate on Pi Zero 2W
- Memory usage over 10-minute session
- CPU load during flight

#### Manual Tests:

- Visual inspection (arrow scaling, rotation accuracy)
- Browser compatibility
- Network latency effects (500ms polling)

---

### Rollback/Fallback Mechanism

**Rollback Plan (if 3D fails after deployment):**

1. **Option A: Revert to 2D (in-code fallback)**
   - Already implemented via try/catch
   - User sees 2D AttitudeIndicator automatically
   - No deployment needed

2. **Option B: Disable 3D via feature flag**
   - Add config parameter: `ENABLE_3D = false` (default true)
   - Conditionally load Three.js in HTML
   - Revert by setting to false and restarting dashboard

3. **Option C: Git rollback (last resort)**
   - Revert commits that added 3D
   - Restore original `dashboard.html`, `main.js`
   - Restart dashboard service

**Estimated Recovery Time**: < 1 minute for Options A or B

---

### Identified Risks & Mitigation

| Risk                                            | Likelihood | Impact                | Mitigation                                           |
| ----------------------------------------------- | ---------- | --------------------- | ---------------------------------------------------- |
| **Three.js CDN unavailable**                    | Low        | Dashboard breaks      | Host Three.js locally; fallback to 2D                |
| **WebGL not supported on target browser**       | Low        | 3D won't render       | Fallback to 2D canvas rendering                      |
| **Frame rate drops below 30 FPS on Pi Zero 2W** | Medium     | Poor UX               | Implement LOD; optimize mesh complexity              |
| **Acceleration arrow scaling unintuitive**      | Medium     | Confusing to user     | Tune scaling factor based on flight data; document   |
| **3D adds 500ms latency**                       | Low        | Stale data display    | Using existing 500ms polling (no worse than current) |
| **Memory spike causes crash**                   | Low        | Loss of display       | Cap Three.js scene complexity; monitor memory        |
| **Yaw not available (always 0.0)**              | N/A        | Limited rotation data | Reserve for future magnetometer; document            |

---

## Implementation Checklist

- [ ] **Milestone 1**: Create `rocket3d.js` and integrate into dashboard
- [ ] **Milestone 2**: Bind sensor data to 3D rotation
- [ ] **Milestone 3**: Add acceleration arrows
- [ ] **Milestone 4**: Style to match dashboard theme
- [ ] **Milestone 5**: Performance test on Pi Zero 2W
- [ ] **Milestone 6**: Implement graceful fallback
- [ ] **Milestone 7**: End-to-end testing
- [ ] **Documentation**: Update CLAUDE.md and code comments

---

## Next Steps

1. **Approve Phase 2 recommendations** (Three.js + polling architecture)
2. **Begin Milestone 1** (create `rocket3d.js`)
3. **Iteratively deploy** and test each milestone
4. **Gather feedback** from flight operations team
