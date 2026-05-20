let attitude;
let rocket3d = null;
let use3D = false;
let pollInterval;
let altitudeChart, accelChart;
let cameraReconnectTimer = null;
let cameraStreamingRequested = false;
const CHART_UPDATE_MS = 1000;
const POLL_MS = 500;
const CAMERA_STATES = new Set(["ARMED", "ASCENT", "APOGEE", "DESCENT"]);
const CAMERA_RETRY_MS = 1500;

const API_BASE = window.location.protocol + "//" + window.location.host;

document.addEventListener("DOMContentLoaded", function () {
  initAttitude();
  initCharts();
  startPolling();
  setInterval(updateCharts, CHART_UPDATE_MS);
  setupControls();
  refreshFlatTestButton();
  updateClock();
  setInterval(updateClock, 1000);
  pollHardware();
  setInterval(pollHardware, 5000);
  setupCameraDisplay();
});

function initAttitude() {
  // Try to initialize 3D visualization first
  try {
    if (typeof Rocket3D === "undefined") {
      throw new Error("Rocket3D class not available");
    }
    rocket3d = new Rocket3D("pfd-3d-container");
    use3D = true;
    console.log("[ATTITUDE] Using 3D visualization");
    console.log("[ATTITUDE] 3D Status:", rocket3d.getStatus());
  } catch (e) {
    console.warn(
      "[ATTITUDE] 3D initialization failed, falling back to 2D:",
      e.message,
    );
    use3D = false;
    // Fall back to 2D attitude indicator
    attitude = new AttitudeIndicator("attitude-canvas-2d");
    document.getElementById("attitude-canvas-2d").style.display = "block";
  }
}

function startCameraDisplay() {
  const cameraImg = document.getElementById("camera-stream");
  if (!cameraImg) {
    return;
  }
  cameraStreamingRequested = true;
  clearTimeout(cameraReconnectTimer);
  if (!cameraImg.dataset.streaming) {
    cameraImg.dataset.streaming = "true";
    cameraImg.src = API_BASE + "/api/camera/stream?t=" + Date.now();
    setCameraStatus("Waiting for camera...");
    console.log("[CAMERA] Started streaming:", cameraImg.src);
  }
}

function stopCameraDisplay() {
  const cameraImg = document.getElementById("camera-stream");
  cameraStreamingRequested = false;
  clearTimeout(cameraReconnectTimer);
  if (cameraImg) {
    cameraImg.dataset.streaming = "";
    cameraImg.src = "";
    cameraImg.style.display = "none";
    setCameraStatus("Camera inactive");
    console.log("[CAMERA] Stopped streaming");
  }
}

function setupCameraDisplay() {
  const cameraImg = document.getElementById("camera-stream");
  if (!cameraImg) {
    return;
  }

  cameraImg.addEventListener("load", function () {
    cameraImg.style.display = "block";
    setCameraStatus("");
  });

  cameraImg.addEventListener("error", function () {
    cameraImg.style.display = "none";
    cameraImg.dataset.streaming = "";
    if (!cameraStreamingRequested) {
      return;
    }
    setCameraStatus("Camera unavailable, retrying...");
    cameraReconnectTimer = window.setTimeout(function () {
      if (cameraStreamingRequested) {
        startCameraDisplay();
      }
    }, CAMERA_RETRY_MS);
  });
}

function setCameraStatus(message) {
  const statusEl = document.getElementById("camera-stream-status");
  if (!statusEl) {
    return;
  }
  statusEl.textContent = message;
  statusEl.style.display = message ? "block" : "none";
}

function startPolling() {
  poll();
  pollInterval = setInterval(poll, POLL_MS);
}

function initCharts() {
  try {
    const altCtx = document.getElementById("chart-altitude").getContext("2d");
    altitudeChart = new Chart(altCtx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "Altitude (m)",
            data: [],
            borderColor: "#00ccff",
            backgroundColor: "rgba(0,204,255,0.1)",
            tension: 0.2,
            pointRadius: 0,
          },
        ],
      },
      options: {
        maintainAspectRatio: false,
        scales: { x: { display: true }, y: { display: true } },
      },
    });

    const axCtx = document.getElementById("chart-accel").getContext("2d");
    accelChart = new Chart(axCtx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "Net Accel (m/s^2)",
            data: [],
            borderColor: "#ff9900",
            backgroundColor: "rgba(255,153,0,0.08)",
            tension: 0.2,
            pointRadius: 0,
          },
        ],
      },
      options: {
        maintainAspectRatio: false,
        scales: { x: { display: true }, y: { display: true } },
      },
    });
  } catch (e) {
    // canvas or Chart.js not available
  }
}

async function fetchHistory(seconds = 60) {
  try {
    const resp = await fetch(API_BASE + "/api/history?seconds=" + seconds);
    if (!resp.ok) return null;
    const rows = await resp.json();
    return rows;
  } catch (e) {
    return null;
  }
}

async function updateCharts() {
  if (!altitudeChart || !accelChart) return;
  const rows = await fetchHistory(60);
  if (!rows) return;

  const labels = [];
  const altData = [];
  const axData = [];
  rows.forEach(function (r) {
    const ts = r.timestamp || 0;
    const tlabel = new Date(ts * 1000).toLocaleTimeString();
    labels.push(tlabel);
    altData.push(r.altitude != null ? r.altitude : null);
    axData.push(r.net_accel != null ? r.net_accel : null);
  });

  // Limit points to last 120
  const maxPoints = 120;
  const sliceFrom = Math.max(0, labels.length - maxPoints);

  altitudeChart.data.labels = labels.slice(sliceFrom);
  altitudeChart.data.datasets[0].data = altData.slice(sliceFrom);
  altitudeChart.update("none");

  accelChart.data.labels = labels.slice(sliceFrom);
  accelChart.data.datasets[0].data = axData.slice(sliceFrom);
  accelChart.update("none");
}

async function poll() {
  try {
    const resp = await fetch(API_BASE + "/api/status");
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const data = await resp.json();
    updateDashboard(data);
    setConnectionStatus(true);
  } catch (e) {
    setConnectionStatus(false);
    console.warn("[POLL] Error fetching status:", e.message);
  }
}

function fallbackTo2D() {
  console.warn("[FALLBACK] Switching to 2D attitude indicator");
  use3D = false;
  if (rocket3d && rocket3d.initialized) {
    try {
      rocket3d.destroy();
    } catch (e) {
      console.error("[FALLBACK] Error destroying 3D:", e);
    }
  }
  // Initialize 2D if not already initialized
  if (!attitude) {
    try {
      document.getElementById("attitude-canvas-2d").style.display = "block";
      attitude = new AttitudeIndicator("attitude-canvas-2d");
    } catch (e) {
      console.error("[FALLBACK] Failed to initialize 2D:", e);
    }
  }
}

function updateDashboard(d) {
  const state = d.state || "IDLE";
  var stateEl = document.getElementById("flight-state");
  stateEl.textContent = state;
  stateEl.className = "state " + state.toLowerCase();

  // PFD: altitude and vertical speed
  document.getElementById("alt-value").textContent =
    (d.altitude != null ? d.altitude.toFixed(1) : "0") + " m";

  var vs = d.vspeed || 0;
  document.getElementById("vs-value").textContent =
    (vs >= 0 ? "+" : "") + vs.toFixed(1) + " m/s";

  // Update attitude (3D or 2D)
  if (use3D && rocket3d) {
    // Check if 3D is still initialized (not lost)
    if (!rocket3d.initialized) {
      console.warn("[DASHBOARD] 3D not initialized, falling back to 2D");
      fallbackTo2D();
    } else {
      try {
        rocket3d.update(d.roll || 0, d.pitch || 0, d.yaw || 0);
        rocket3d.updateAcceleration(
          d.accel_x || 0,
          d.accel_y || 0,
          d.accel_z || 0,
        );
      } catch (e) {
        console.error("[DASHBOARD] 3D update failed:", e);
        fallbackTo2D();
      }
    }
  }

  if (!use3D && attitude) {
    try {
      attitude.update(d.roll || 0, d.pitch || 0);
    } catch (e) {
      console.error("[DASHBOARD] 2D update failed:", e);
    }
  }

  // Environment readouts
  document.getElementById("pressure").textContent =
    (d.pressure != null ? d.pressure.toFixed(1) : "----") + " hPa";
  document.getElementById("temperature").textContent =
    (d.temperature != null ? d.temperature.toFixed(1) : "--") + " \u00B0C";

  // Logging status
  var logEl = document.getElementById("logging-status");
  var isActive = state !== "IDLE";
  logEl.textContent = isActive ? "ACTIVE" : "INACTIVE";
  logEl.className = "value " + (isActive ? "status-active" : "status-inactive");

  // IMU data
  var hasImu =
    d.roll != null ||
    d.pitch != null ||
    d.yaw != null ||
    d.accel_x != null ||
    d.accel_y != null ||
    d.accel_z != null;
  document.getElementById("imu-roll").textContent = hasImu
    ? d.roll.toFixed(1) + "\u00B0"
    : "--";
  document.getElementById("imu-pitch").textContent = hasImu
    ? d.pitch.toFixed(1) + "\u00B0"
    : "--";
  document.getElementById("imu-yaw").textContent = hasImu
    ? d.yaw.toFixed(1) + "\u00B0"
    : "--";
  document.getElementById("imu-ax").textContent = hasImu
    ? d.accel_x.toFixed(2) + " m/s² (" + (d.accel_x / 9.81).toFixed(2) + "g)"
    : "--";
  document.getElementById("imu-ay").textContent = hasImu
    ? d.accel_y.toFixed(2) + " m/s² (" + (d.accel_y / 9.81).toFixed(2) + "g)"
    : "--";
  document.getElementById("imu-az").textContent = hasImu
    ? d.accel_z.toFixed(2) + " m/s² (" + (d.accel_z / 9.81).toFixed(2) + "g)"
    : "--";

  if (hasImu) {
    document.getElementById("imu-total").textContent =
      d.total_accel != null
        ? d.total_accel.toFixed(2) +
          " m/s² (" +
          (d.total_accel / 9.81).toFixed(2) +
          "g)"
        : "--";
    document.getElementById("imu-net").textContent =
      d.net_accel != null
        ? d.net_accel.toFixed(2) +
          " m/s² (" +
          (d.net_accel / 9.81).toFixed(2) +
          "g)"
        : "--";
  } else {
    document.getElementById("imu-total").textContent = "--";
    document.getElementById("imu-net").textContent = "--";
  }

  // Button states
  var isIdle = state === "IDLE";
  var isArmed = state === "ARMED";
  document.getElementById("btn-arm").disabled = !isIdle;
  document.getElementById("btn-disarm").disabled = !isArmed;

  // Camera panel visibility: active once the system has been armed for flight.
  var cameraPanel = document.getElementById("camera-panel");
  if (CAMERA_STATES.has(state)) {
    cameraPanel.style.display = "block";
    startCameraDisplay();
  } else {
    cameraPanel.style.display = "none";
    stopCameraDisplay();
  }
}

function setConnectionStatus(connected) {
  var el = document.getElementById("connection-status");
  el.textContent = connected ? "Connected" : "Disconnected";
  el.className = "conn-status " + (connected ? "connected" : "disconnected");
}

function updateClock() {
  var now = new Date();
  var h = String(now.getHours()).padStart(2, "0");
  var m = String(now.getMinutes()).padStart(2, "0");
  var s = String(now.getSeconds()).padStart(2, "0");
  document.getElementById("clock").textContent = h + ":" + m + ":" + s;
}

function setupControls() {
  document
    .getElementById("btn-arm")
    .addEventListener("click", async function () {
      try {
        console.log("[ARM] Button clicked");
        const resp = await fetch(API_BASE + "/api/arm", { method: "POST" });
        const data = await resp.json();
        console.log("[ARM] Response:", data);
        if (!resp.ok) console.log("[ARM] HTTP Error:", resp.status);
      } catch (e) {
        console.log("[ARM] Error:", e);
      }
    });
  document
    .getElementById("btn-disarm")
    .addEventListener("click", async function () {
      try {
        console.log("[DISARM] Button clicked");
        const resp = await fetch(API_BASE + "/api/disarm", { method: "POST" });
        const data = await resp.json();
        console.log("[DISARM] Response:", data);
        if (!resp.ok) console.log("[DISARM] HTTP Error:", resp.status);
      } catch (e) {
        console.log("[DISARM] Error:", e);
      }
    });
  document
    .getElementById("btn-calibrate")
    .addEventListener("click", async function () {
      await fetch(API_BASE + "/api/calibrate", { method: "POST" });
    });
  document
    .getElementById("btn-flattest")
    .addEventListener("click", async function () {
      try {
        // Read current config, toggle flat_test, write it back
        const resp = await fetch(API_BASE + "/api/config");
        if (!resp.ok) return;
        const cfg = await resp.json();
        const current = !!cfg.flat_test;
        const newVal = !current;
        await fetch(API_BASE + "/api/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ flat_test: newVal }),
        });
        updateFlatTestButton(newVal);
      } catch (e) {
        console.warn("[FLATTEST] Toggle failed", e);
      }
    });
  document.getElementById("btn-config").addEventListener("click", openConfig);
  document
    .getElementById("btn-config-close")
    .addEventListener("click", closeConfig);
  document
    .getElementById("btn-config-save")
    .addEventListener("click", saveConfig);
}

async function refreshFlatTestButton() {
  try {
    const resp = await fetch(API_BASE + "/api/config");
    if (!resp.ok) return;
    const cfg = await resp.json();
    updateFlatTestButton(!!cfg.flat_test);
  } catch (e) {
    // ignore
  }
}

function updateFlatTestButton(enabled) {
  const btn = document.getElementById("btn-flattest");
  if (!btn) return;
  btn.textContent = enabled ? "FLAT TEST: ON" : "FLAT TEST: OFF";
  btn.className = "ctrl-btn " + (enabled ? "active" : "");
}

// -- Hardware status --

async function pollHardware() {
  try {
    var resp = await fetch(API_BASE + "/api/hardware");
    var hw = await resp.json();

    // I2C bus status
    var i2cEl = document.getElementById("hw-i2c");
    var anyI2c = hw.sensors.some(function (s) {
      return s.connected;
    });
    i2cEl.textContent = anyI2c ? "OK" : "NO DEV";
    i2cEl.className =
      "pin-status " + (anyI2c ? "status-active" : "status-inactive");

    // Sensors
    hw.sensors.forEach(function (s) {
      var id = "hw-" + s.name.toLowerCase();
      var el = document.getElementById(id);
      if (el) {
        el.textContent = s.connected ? "OK" : "N/C";
        el.className =
          "pin-status " + (s.connected ? "status-active" : "status-inactive");
      }
    });

    // Supply voltage status
    var supplyEl = document.getElementById("supply-status");
    if (hw.power && hw.power.undervoltage !== null) {
      if (hw.power.undervoltage) {
        supplyEl.textContent = "LOW";
        supplyEl.className = "value status-critical";
      } else {
        supplyEl.textContent = "OK";
        supplyEl.className = "value status-active";
      }
    } else {
      supplyEl.textContent = "N/A";
      supplyEl.className = "value status-inactive";
    }
  } catch (e) {
    // ignore - not running on Pi
  }
}

async function openConfig() {
  var resp = await fetch(API_BASE + "/api/config");
  var cfg = await resp.json();
  var container = document.getElementById("config-fields");
  while (container.firstChild) {
    container.removeChild(container.firstChild);
  }
  for (var key in cfg) {
    if (!cfg.hasOwnProperty(key)) continue;
    var row = document.createElement("div");
    row.className = "config-row";
    var label = document.createElement("label");
    label.textContent = key;
    var input = document.createElement("input");
    input.type = "text";
    input.dataset.key = key;
    input.value = cfg[key];
    row.appendChild(label);
    row.appendChild(input);
    container.appendChild(row);
  }
  document.getElementById("config-modal").classList.remove("hidden");
}

function closeConfig() {
  document.getElementById("config-modal").classList.add("hidden");
}

async function saveConfig() {
  var inputs = document.querySelectorAll("#config-fields input");
  var cfg = {};
  inputs.forEach(function (input) {
    var val = input.value;
    var num = Number(val);
    cfg[input.dataset.key] = isNaN(num) ? val : num;
  });
  await fetch(API_BASE + "/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cfg),
  });
  closeConfig();
}
