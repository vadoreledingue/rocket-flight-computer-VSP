const REPORT_API_BASE = window.location.protocol + "//" + window.location.host;

let reports = [];
let selectedFlightId = null;

document.addEventListener("DOMContentLoaded", function () {
  document
    .getElementById("btn-refresh-reports")
    .addEventListener("click", function () {
      loadReports(selectedFlightId);
    });
  loadReports();
});

async function loadReports(preferredFlightId = null) {
  setStatus("LOADING", "status-inactive");
  try {
    const resp = await fetch(REPORT_API_BASE + "/api/reports");
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    reports = await resp.json();
    renderReportList();

    if (reports.length === 0) {
      renderEmptyState();
      return;
    }

    const targetId =
      preferredFlightId && reports.some((r) => r.flight_id === preferredFlightId)
        ? preferredFlightId
        : reports[0].flight_id;
    selectFlight(targetId);
  } catch (e) {
    setStatus("ERROR", "status-critical");
    document.getElementById("report-selected-title").textContent =
      "Unable to load flight reports";
    document.getElementById("report-summary").innerHTML =
      '<div class="report-empty">The report list could not be loaded.</div>';
    document.getElementById("report-grid").innerHTML = "";
    document.getElementById("report-video-slot").innerHTML = "";
  }
}

function renderReportList() {
  const list = document.getElementById("report-flight-list");
  list.innerHTML = "";

  reports.forEach(function (report) {
    const button = document.createElement("button");
    button.type = "button";
    button.className =
      "report-flight-card" +
      (report.flight_id === selectedFlightId ? " active" : "");
    button.addEventListener("click", function () {
      selectFlight(report.flight_id);
    });

    const title = document.createElement("div");
    title.className = "report-flight-card-title";
    title.textContent = "Flight #" + report.flight_id;

    const meta = document.createElement("div");
    meta.className = "report-flight-card-meta";
    meta.textContent =
      formatDateTime(report.started_at) +
      " | " +
      formatDuration(report.duration || 0);

    const badges = document.createElement("div");
    badges.className = "report-flight-card-badges";
    badges.textContent =
      (report.report_available ? "Graphs ready" : "Generate on open") +
      (report.video && report.video.available ? " | Video ready" : "");

    button.appendChild(title);
    button.appendChild(meta);
    button.appendChild(badges);
    list.appendChild(button);
  });
}

async function selectFlight(flightId) {
  selectedFlightId = flightId;
  renderReportList();
  setStatus("LOADING", "status-inactive");

  try {
    const resp = await fetch(REPORT_API_BASE + "/api/reports/" + flightId);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const report = await resp.json();
    renderReportDetail(report);
    setStatus("READY", "status-active");
  } catch (e) {
    setStatus("ERROR", "status-critical");
    document.getElementById("report-selected-title").textContent =
      "Flight #" + flightId;
    document.getElementById("report-summary").innerHTML =
      '<div class="report-empty">The selected report could not be loaded.</div>';
    document.getElementById("report-grid").innerHTML = "";
    document.getElementById("report-video-slot").innerHTML = "";
  }
}

function renderReportDetail(report) {
  document.getElementById("report-selected-title").textContent =
    "Flight #" + report.flight_id + " | " + formatDateTime(report.started_at);

  document.getElementById("report-summary").innerHTML = [
    summaryCell("Duration", formatDuration(report.duration || 0)),
    summaryCell("Max Altitude", formatNumber(report.max_altitude, 1) + " m"),
    summaryCell("Max VSpeed", formatNumber(report.max_vspeed, 1) + " m/s"),
    summaryCell(
      "Max Net Accel",
      formatNumber(report.max_net_accel, 2) + " m/s^2",
    ),
    summaryCell("Samples", String(report.sample_count || 0)),
    summaryCell("State", report.state || "UNKNOWN"),
  ].join("");

  renderVideo(report.video || {});
  renderImages(report.images || []);
}

function renderVideo(video) {
  const slot = document.getElementById("report-video-slot");
  slot.innerHTML = "";

  if (video.available && video.url) {
    const videoEl = document.createElement("video");
    videoEl.controls = true;
    videoEl.preload = "metadata";
    videoEl.src = video.url;
    videoEl.className = "report-video-player";
    slot.appendChild(videoEl);
    return;
  }

  const empty = document.createElement("div");
  empty.className = "report-empty";
  empty.textContent = video.error
    ? video.error
    : "No browser-ready video is available for this flight.";
  slot.appendChild(empty);
}

function renderImages(images) {
  const grid = document.getElementById("report-grid");
  grid.innerHTML = "";

  if (!images.length) {
    grid.innerHTML =
      '<div class="report-empty">No telemetry images were generated for this flight.</div>';
    return;
  }

  images.forEach(function (image) {
    const card = document.createElement("article");
    card.className = "report-card";

    const title = document.createElement("h3");
    title.textContent = image.title;

    const img = document.createElement("img");
    img.src = image.url;
    img.alt = image.title;
    img.className = "report-graph-image";
    img.loading = "lazy";

    card.appendChild(title);
    card.appendChild(img);
    grid.appendChild(card);
  });
}

function renderEmptyState() {
  document.getElementById("report-selected-title").textContent =
    "No completed flights yet";
  document.getElementById("report-summary").innerHTML =
    '<div class="report-empty">The flight report page will populate after the first completed flight.</div>';
  document.getElementById("report-grid").innerHTML = "";
  document.getElementById("report-video-slot").innerHTML = "";
  setStatus("EMPTY", "status-inactive");
}

function setStatus(text, className) {
  const el = document.getElementById("report-status");
  el.textContent = text;
  el.className = "value " + className;
}

function summaryCell(label, value) {
  return (
    '<div class="report-summary-card">' +
    '<span class="label">' +
    label +
    "</span>" +
    '<span class="value">' +
    value +
    "</span>" +
    "</div>"
  );
}

function formatDuration(seconds) {
  const total = Math.max(0, Math.round(seconds || 0));
  const h = String(Math.floor(total / 3600)).padStart(2, "0");
  const m = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const s = String(total % 60).padStart(2, "0");
  return h + ":" + m + ":" + s;
}

function formatDateTime(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatNumber(value, digits) {
  if (value === null || value === undefined) return "--";
  return Number(value).toFixed(digits);
}
