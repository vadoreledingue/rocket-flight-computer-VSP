let attitude;
let pollInterval;
const POLL_MS = 500;

document.addEventListener('DOMContentLoaded', function() {
    attitude = new AttitudeIndicator('attitude-canvas');
    startPolling();
    setupControls();
    updateClock();
    setInterval(updateClock, 1000);
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

    document.getElementById('alt-value').textContent =
        (d.altitude != null ? d.altitude.toFixed(1) : '0') + ' m';

    var vs = d.vspeed || 0;
    document.getElementById('vs-value').textContent =
        (vs >= 0 ? '+' : '') + vs.toFixed(1) + ' m/s';

    attitude.update(d.roll || 0, d.pitch || 0);

    document.getElementById('pressure').textContent =
        (d.pressure != null ? d.pressure.toFixed(1) : '----') + ' hPa';
    document.getElementById('temperature').textContent =
        (d.temperature != null ? d.temperature.toFixed(1) : '--') + ' \u00B0C';
    document.getElementById('humidity').textContent =
        (d.humidity != null ? d.humidity.toFixed(0) : '--') + ' %';

    var batEl = document.getElementById('battery-status');
    if (d.battery_low) {
        batEl.textContent = 'LOW';
        batEl.className = 'value status-critical';
    } else {
        batEl.textContent = 'OK';
        batEl.className = 'value status-active';
    }

    var logEl = document.getElementById('logging-status');
    var isActive = d.state && d.state !== 'IDLE';
    logEl.textContent = isActive ? 'ACTIVE' : 'INACTIVE';
    logEl.className = 'value ' + (isActive ? 'status-active' : 'status-inactive');

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
