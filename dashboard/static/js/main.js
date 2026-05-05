let attitude;
let pollInterval;
let altitudeChart, accelChart;
const CHART_UPDATE_MS = 1000;
const POLL_MS = 500;

document.addEventListener("DOMContentLoaded", function () {
  attitude = new AttitudeIndicator("attitude-canvas");
  initCharts();
  startPolling();
  setInterval(updateCharts, CHART_UPDATE_MS);
  setupControls();
  updateClock();
  setInterval(updateClock, 1000);
  pollBatteryTest();
  setInterval(pollBatteryTest, 1000);
  loadBatteryHistory();
  pollHardware();
  setInterval(pollHardware, 5000);
});

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
            label: "Accel (g)",
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
    const resp = await fetch(`/api/history?seconds=${seconds}`);
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
    const ax = r.accel_x || 0;
    const ay = r.accel_y || 0;
    const az = r.accel_z || 0;
    const mag = Math.sqrt(ax * ax + ay * ay + az * az);
    axData.push(mag);
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
    const resp = await fetch("/api/status");
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const data = await resp.json();
    updateDashboard(data);
    setConnectionStatus(true);
  } catch (e) {
    setConnectionStatus(false);
  }
}

function updateDashboard(d) {
  var stateEl = document.getElementById("flight-state");
  stateEl.textContent = d.state || "IDLE";
  stateEl.className = "state " + (d.state || "idle").toLowerCase();

  // PFD: altitude and vertical speed
  document.getElementById("alt-value").textContent =
    (d.altitude != null ? d.altitude.toFixed(1) : "0") + " m";

  var vs = d.vspeed || 0;
  document.getElementById("vs-value").textContent =
    (vs >= 0 ? "+" : "") + vs.toFixed(1) + " m/s";

  attitude.update(d.roll || 0, d.pitch || 0);

  // Environment readouts
  document.getElementById("pressure").textContent =
    (d.pressure != null ? d.pressure.toFixed(1) : "----") + " hPa";
  document.getElementById("temperature").textContent =
    (d.temperature != null ? d.temperature.toFixed(1) : "--") + " \u00B0C";

  // Battery status
  var batEl = document.getElementById("battery-status");
  if (d.battery_low) {
    batEl.textContent = "LOW";
    batEl.className = "value status-critical";
  } else {
    batEl.textContent = "OK";
    batEl.className = "value status-active";
  }

  // Logging status
  var logEl = document.getElementById("logging-status");
  var isActive = d.state && d.state !== "IDLE";
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
    ? d.accel_x.toFixed(2) + " g"
    : "--";
  document.getElementById("imu-ay").textContent = hasImu
    ? d.accel_y.toFixed(2) + " g"
    : "--";
  document.getElementById("imu-az").textContent = hasImu
    ? d.accel_z.toFixed(2) + " g"
    : "--";

  // Button states
  var isIdle = !d.state || d.state === "IDLE";
  var isArmed = d.state === "ARMED";
  document.getElementById("btn-arm").disabled = !isIdle;
  document.getElementById("btn-disarm").disabled = !isArmed;
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
      await fetch("/api/arm", { method: "POST" });
    });
  document
    .getElementById("btn-disarm")
    .addEventListener("click", async function () {
      await fetch("/api/disarm", { method: "POST" });
    });
  document
    .getElementById("btn-calibrate")
    .addEventListener("click", async function () {
      await fetch("/api/calibrate", { method: "POST" });
    });
  document.getElementById("btn-config").addEventListener("click", openConfig);
  document
    .getElementById("btn-config-close")
    .addEventListener("click", closeConfig);
  document
    .getElementById("btn-config-save")
    .addEventListener("click", saveConfig);
  document
    .getElementById("btn-bat-start")
    .addEventListener("click", async function () {
      await fetch("/api/battery-test/start", { method: "POST" });
      pollBatteryTest();
      loadBatteryHistory();
    });
  document
    .getElementById("btn-bat-stop")
    .addEventListener("click", async function () {
      await fetch("/api/battery-test/stop", { method: "POST" });
      pollBatteryTest();
      loadBatteryHistory();
    });
  document
    .getElementById("btn-bat-clear")
    .addEventListener("click", async function () {
      await fetch("/api/battery-tests/clear", { method: "POST" });
      loadBatteryHistory();
    });
}

// -- Hardware status --

async function pollHardware() {
  try {
    var resp = await fetch("/api/hardware");
    var hw = await resp.json();

    // I2C bus status
    var i2cEl = document.getElementById("hw-i2c");
    var anyI2c = hw.sensors.some(function (s) {
      return s.connected;
    });
    i2cEl.textContent = anyI2c ? "OK" : "NO DEV";
    i2cEl.className =
      "pin-status " + (anyI2c ? "status-active" : "status-inactive");

    // LBO pin
    var lboEl = document.getElementById("hw-lbo");
    lboEl.textContent = "READY";
    lboEl.className = "pin-status status-active";

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

// -- Battery test --

async function pollBatteryTest() {
  try {
    var resp = await fetch("/api/battery-test");
    var test = await resp.json();
    var stateEl = document.getElementById("bat-test-state");
    var runtimeEl = document.getElementById("bat-test-runtime");
    var lowEl = document.getElementById("bat-test-low-at");
    var btnStart = document.getElementById("btn-bat-start");
    var btnStop = document.getElementById("btn-bat-stop");

    if (test && test.state === "RUNNING") {
      stateEl.textContent = "RUNNING";
      stateEl.className = "value status-active";
      runtimeEl.textContent = formatDuration(test.elapsed);
      if (test.low_at) {
        var lowElapsed = test.low_at - test.started_at;
        lowEl.textContent = formatDuration(lowElapsed);
        lowEl.className = "value status-critical";
      } else {
        lowEl.textContent = "--";
        lowEl.className = "value";
      }
      btnStart.disabled = true;
      btnStop.disabled = false;
    } else {
      stateEl.textContent = "IDLE";
      stateEl.className = "value status-inactive";
      runtimeEl.textContent = "--:--:--";
      lowEl.textContent = "--";
      lowEl.className = "value";
      btnStart.disabled = false;
      btnStop.disabled = true;
    }
  } catch (e) {
    // ignore polling errors
  }
}

function formatDuration(seconds) {
  var h = Math.floor(seconds / 3600);
  var m = Math.floor((seconds % 3600) / 60);
  var s = Math.floor(seconds % 60);
  return (
    String(h).padStart(2, "0") +
    ":" +
    String(m).padStart(2, "0") +
    ":" +
    String(s).padStart(2, "0")
  );
}

async function loadBatteryHistory() {
  try {
    var resp = await fetch("/api/battery-tests");
    var tests = await resp.json();
    var container = document.getElementById("bat-test-history");
    while (container.firstChild) {
      container.removeChild(container.firstChild);
    }

    var completed = tests.filter(function (t) {
      return t.state === "COMPLETED";
    });
    if (completed.length === 0) return;

    var title = document.createElement("div");
    title.className = "bat-history-title";
    title.textContent = "PREVIOUS TESTS";
    container.appendChild(title);

    completed.slice(0, 5).forEach(function (t) {
      var row = document.createElement("div");
      row.className = "bat-history-row";
      var duration = (t.ended_at || 0) - t.started_at;
      var date = new Date(t.started_at * 1000);
      var dateStr =
        date.toLocaleDateString("de-DE") +
        " " +
        date.toLocaleTimeString("de-DE", {
          hour: "2-digit",
          minute: "2-digit",
        });

      var dateSpan = document.createElement("span");
      dateSpan.textContent = dateStr;

      var runtimeSpan = document.createElement("span");
      runtimeSpan.className = "runtime";
      runtimeSpan.textContent = formatDuration(duration);

      row.appendChild(dateSpan);

      if (t.low_at) {
        var lowSpan = document.createElement("span");
        lowSpan.className = "low-time";
        lowSpan.textContent =
          "LOW @ " + formatDuration(t.low_at - t.started_at);
        row.appendChild(lowSpan);
      }

      row.appendChild(runtimeSpan);
      container.appendChild(row);
    });
  } catch (e) {
    // ignore
  }
}

async function openConfig() {
  var resp = await fetch("/api/config");
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
  await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cfg),
  });
  closeConfig();
}
