let attitude;
let pollInterval;
const POLL_MS = 500;

document.addEventListener('DOMContentLoaded', function() {
    attitude = new AttitudeIndicator('attitude-canvas');
    startPolling();
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

async function poll() {
    try {
        const resp = await fetch('/api/status');
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        updateDashboard(data);
        setConnectionStatus(true);
    } catch (e) {
        setConnectionStatus(false);
    }
}

function updateDashboard(d) {
    var stateEl = document.getElementById('flight-state');
    stateEl.textContent = d.state || 'IDLE';
    stateEl.className = 'state ' + (d.state || 'idle').toLowerCase();

    // PFD: altitude and vertical speed
    document.getElementById('alt-value').textContent =
        (d.altitude != null ? d.altitude.toFixed(1) : '0') + ' m';

    var vs = d.vspeed || 0;
    document.getElementById('vs-value').textContent =
        (vs >= 0 ? '+' : '') + vs.toFixed(1) + ' m/s';

    attitude.update(d.roll || 0, d.pitch || 0);

    // Environment readouts
    document.getElementById('pressure').textContent =
        (d.pressure != null ? d.pressure.toFixed(1) : '----') + ' hPa';
    document.getElementById('temperature').textContent =
        (d.temperature != null ? d.temperature.toFixed(1) : '--') + ' \u00B0C';
    document.getElementById('humidity').textContent =
        (d.humidity != null ? d.humidity.toFixed(0) : '--') + ' %';

    // Battery status
    var batEl = document.getElementById('battery-status');
    if (d.battery_low) {
        batEl.textContent = 'LOW';
        batEl.className = 'value status-critical';
    } else {
        batEl.textContent = 'OK';
        batEl.className = 'value status-active';
    }

    // Logging status
    var logEl = document.getElementById('logging-status');
    var isActive = d.state && d.state !== 'IDLE';
    logEl.textContent = isActive ? 'ACTIVE' : 'INACTIVE';
    logEl.className = 'value ' + (isActive ? 'status-active' : 'status-inactive');

    // IMU data
    var hasImu = d.roll != null && (d.roll !== 0 || d.pitch !== 0 || d.yaw !== 0);
    document.getElementById('imu-roll').textContent = hasImu ? d.roll.toFixed(1) + '\u00B0' : '--';
    document.getElementById('imu-pitch').textContent = hasImu ? d.pitch.toFixed(1) + '\u00B0' : '--';
    document.getElementById('imu-yaw').textContent = hasImu ? d.yaw.toFixed(1) + '\u00B0' : '--';
    document.getElementById('imu-ax').textContent = hasImu ? d.accel_x.toFixed(2) + ' g' : '--';
    document.getElementById('imu-ay').textContent = hasImu ? d.accel_y.toFixed(2) + ' g' : '--';
    document.getElementById('imu-az').textContent = hasImu ? d.accel_z.toFixed(2) + ' g' : '--';

    // Button states
    var isIdle = !d.state || d.state === 'IDLE';
    var isArmed = d.state === 'ARMED';
    document.getElementById('btn-arm').disabled = !isIdle;
    document.getElementById('btn-disarm').disabled = !isArmed;
}

function setConnectionStatus(connected) {
    var el = document.getElementById('connection-status');
    el.textContent = connected ? 'Connected' : 'Disconnected';
    el.className = 'conn-status ' + (connected ? 'connected' : 'disconnected');
}

function updateClock() {
    var now = new Date();
    var h = String(now.getHours()).padStart(2, '0');
    var m = String(now.getMinutes()).padStart(2, '0');
    var s = String(now.getSeconds()).padStart(2, '0');
    document.getElementById('clock').textContent = h + ':' + m + ':' + s;
}

function setupControls() {
    document.getElementById('btn-arm').addEventListener('click', async function() {
        await fetch('/api/arm', { method: 'POST' });
    });
    document.getElementById('btn-disarm').addEventListener('click', async function() {
        await fetch('/api/disarm', { method: 'POST' });
    });
    document.getElementById('btn-calibrate').addEventListener('click', async function() {
        await fetch('/api/calibrate', { method: 'POST' });
    });
    document.getElementById('btn-config').addEventListener('click', openConfig);
    document.getElementById('btn-config-close').addEventListener('click', closeConfig);
    document.getElementById('btn-config-save').addEventListener('click', saveConfig);
    document.getElementById('btn-bat-start').addEventListener('click', async function() {
        await fetch('/api/battery-test/start', { method: 'POST' });
        pollBatteryTest();
        loadBatteryHistory();
    });
    document.getElementById('btn-bat-stop').addEventListener('click', async function() {
        await fetch('/api/battery-test/stop', { method: 'POST' });
        pollBatteryTest();
        loadBatteryHistory();
    });
    document.getElementById('btn-bat-clear').addEventListener('click', async function() {
        await fetch('/api/battery-tests/clear', { method: 'POST' });
        loadBatteryHistory();
    });
}

// -- Hardware status --

async function pollHardware() {
    try {
        var resp = await fetch('/api/hardware');
        var hw = await resp.json();

        // I2C bus status
        var i2cEl = document.getElementById('hw-i2c');
        var anyI2c = hw.sensors.some(function(s) { return s.connected; });
        i2cEl.textContent = anyI2c ? 'OK' : 'NO DEV';
        i2cEl.className = 'pin-status ' + (anyI2c ? 'status-active' : 'status-inactive');

        // LBO pin
        var lboEl = document.getElementById('hw-lbo');
        lboEl.textContent = 'READY';
        lboEl.className = 'pin-status status-active';

        // Deploy pin
        var deployEl = document.getElementById('hw-deploy');
        deployEl.textContent = 'READY';
        deployEl.className = 'pin-status status-active';

        // Sensors
        hw.sensors.forEach(function(s) {
            var id = 'hw-' + s.name.toLowerCase();
            var el = document.getElementById(id);
            if (el) {
                el.textContent = s.connected ? 'OK' : 'N/C';
                el.className = 'pin-status ' + (s.connected ? 'status-active' : 'status-inactive');
            }
        });
    } catch (e) {
        // ignore - not running on Pi
    }
}

// -- Battery test --

async function pollBatteryTest() {
    try {
        var resp = await fetch('/api/battery-test');
        var test = await resp.json();
        var stateEl = document.getElementById('bat-test-state');
        var runtimeEl = document.getElementById('bat-test-runtime');
        var lowEl = document.getElementById('bat-test-low-at');
        var btnStart = document.getElementById('btn-bat-start');
        var btnStop = document.getElementById('btn-bat-stop');

        if (test && test.state === 'RUNNING') {
            stateEl.textContent = 'RUNNING';
            stateEl.className = 'value status-active';
            runtimeEl.textContent = formatDuration(test.elapsed);
            if (test.low_at) {
                var lowElapsed = test.low_at - test.started_at;
                lowEl.textContent = formatDuration(lowElapsed);
                lowEl.className = 'value status-critical';
            } else {
                lowEl.textContent = '--';
                lowEl.className = 'value';
            }
            btnStart.disabled = true;
            btnStop.disabled = false;
        } else {
            stateEl.textContent = 'IDLE';
            stateEl.className = 'value status-inactive';
            runtimeEl.textContent = '--:--:--';
            lowEl.textContent = '--';
            lowEl.className = 'value';
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
    return String(h).padStart(2, '0') + ':' +
           String(m).padStart(2, '0') + ':' +
           String(s).padStart(2, '0');
}

async function loadBatteryHistory() {
    try {
        var resp = await fetch('/api/battery-tests');
        var tests = await resp.json();
        var container = document.getElementById('bat-test-history');
        while (container.firstChild) { container.removeChild(container.firstChild); }

        var completed = tests.filter(function(t) { return t.state === 'COMPLETED'; });
        if (completed.length === 0) return;

        var title = document.createElement('div');
        title.className = 'bat-history-title';
        title.textContent = 'PREVIOUS TESTS';
        container.appendChild(title);

        completed.slice(0, 5).forEach(function(t) {
            var row = document.createElement('div');
            row.className = 'bat-history-row';
            var duration = (t.ended_at || 0) - t.started_at;
            var date = new Date(t.started_at * 1000);
            var dateStr = date.toLocaleDateString('de-DE') + ' ' +
                          date.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });

            var dateSpan = document.createElement('span');
            dateSpan.textContent = dateStr;

            var runtimeSpan = document.createElement('span');
            runtimeSpan.className = 'runtime';
            runtimeSpan.textContent = formatDuration(duration);

            row.appendChild(dateSpan);

            if (t.low_at) {
                var lowSpan = document.createElement('span');
                lowSpan.className = 'low-time';
                lowSpan.textContent = 'LOW @ ' + formatDuration(t.low_at - t.started_at);
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
    var resp = await fetch('/api/config');
    var cfg = await resp.json();
    var container = document.getElementById('config-fields');
    while (container.firstChild) {
        container.removeChild(container.firstChild);
    }
    for (var key in cfg) {
        if (!cfg.hasOwnProperty(key)) continue;
        var row = document.createElement('div');
        row.className = 'config-row';
        var label = document.createElement('label');
        label.textContent = key;
        var input = document.createElement('input');
        input.type = 'text';
        input.dataset.key = key;
        input.value = cfg[key];
        row.appendChild(label);
        row.appendChild(input);
        container.appendChild(row);
    }
    document.getElementById('config-modal').classList.remove('hidden');
}

function closeConfig() {
    document.getElementById('config-modal').classList.add('hidden');
}

async function saveConfig() {
    var inputs = document.querySelectorAll('#config-fields input');
    var cfg = {};
    inputs.forEach(function(input) {
        var val = input.value;
        var num = Number(val);
        cfg[input.dataset.key] = isNaN(num) ? val : num;
    });
    await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg),
    });
    closeConfig();
}
