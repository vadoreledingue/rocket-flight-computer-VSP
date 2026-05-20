import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from flight.camera import DEFAULT_VIDEO_DIR
from flight.database import FlightDB


DEFAULT_REPORT_DIR = "/opt/rocket/data/reports"
FALLBACK_REPORT_DIR = "/tmp/rocket/reports"
MEDIAN_FILTER_WINDOW = 5
KALMAN_PROCESS_SCALE = 0.12
KALMAN_MIN_VARIANCE = 1e-3
OUTLIER_SIGMA = 3.5

CHART_SPECS = (
    {
        "key": "altitude",
        "title": "Altitude",
        "ylabel": "Altitude (m)",
        "field": "altitude",
        "color": "#00ccff",
    },
    {
        "key": "temperature",
        "title": "Temperature",
        "ylabel": "Temperature (C)",
        "field": "temperature",
        "color": "#ffaa00",
    },
    {
        "key": "vertical_acceleration",
        "title": "Vertical Acceleration",
        "ylabel": "Acceleration Z (m/s^2)",
        "field": "accel_z",
        "color": "#00ff88",
    },
    {
        "key": "net_acceleration",
        "title": "Net Acceleration",
        "ylabel": "Net Acceleration (m/s^2)",
        "field": "net_accel",
        "color": "#ff6688",
    },
)


class FlightReportManager:
    def __init__(
        self,
        db: FlightDB,
        report_dir: str = DEFAULT_REPORT_DIR,
        video_dir: str = DEFAULT_VIDEO_DIR,
        video_fps: int = 24,
    ) -> None:
        self.db = db
        configured_report_dir = os.environ.get("ROCKET_REPORT_DIR", report_dir)
        configured_video_dir = os.environ.get("ROCKET_VIDEO_DIR", video_dir)
        self.report_dir = self._prepare_dir(
            configured_report_dir, FALLBACK_REPORT_DIR)
        self.video_dir = Path(configured_video_dir)
        self.video_fps = video_fps

    def list_reports(self) -> list[dict[str, Any]]:
        completed_flights = [
            flight for flight in self.db.get_flights()
            if flight.get("state") == "COMPLETED"
        ]
        return [self.get_report_summary(flight["id"]) for flight in completed_flights]

    def get_report_summary(self, flight_id: int) -> dict[str, Any] | None:
        flight = self.db.get_flight(flight_id)
        if not flight:
            return None

        manifest = self._read_manifest(flight_id)
        if manifest:
            return manifest

        rows = self.db.get_readings_for_flight(flight_id)
        raw_summary, smoothed_summary = self._build_default_summaries(flight, rows)
        video = self._build_video_metadata(
            self._get_video_sources(flight_id),
            self.get_report_path(flight_id) / "flight.mp4",
        )
        return self._build_manifest(
            flight,
            sample_count=len(rows),
            images=[],
            smoothed_images=[],
            raw_summary=raw_summary,
            smoothed_summary=smoothed_summary,
            smoothing=self._build_smoothing_metadata(),
            video=video,
        )

    def get_report(self, flight_id: int, generate_missing: bool = False) -> dict[str, Any] | None:
        manifest = self._read_manifest(flight_id)
        if manifest:
            return manifest

        if generate_missing:
            return self.generate_for_flight(flight_id)

        return self.get_report_summary(flight_id)

    def generate_for_flight(self, flight_id: int) -> dict[str, Any] | None:
        flight = self.db.get_flight(flight_id)
        if not flight:
            return None

        rows = self.db.get_readings_for_flight(flight_id)
        raw_summary, smoothed_summary = self._build_default_summaries(flight, rows)
        report_path = self.get_report_path(flight_id)
        report_path.mkdir(parents=True, exist_ok=True)

        images: list[dict[str, str]] = []
        smoothed_images: list[dict[str, str]] = []
        if rows:
            telemetry = self._build_telemetry(rows)
            smoothed_telemetry = self._build_smoothed_telemetry(
                telemetry,
                window_size=MEDIAN_FILTER_WINDOW,
            )
            images = self._render_chart_set(
                telemetry,
                report_path,
            )
            smoothed_images = self._render_chart_set(
                smoothed_telemetry,
                report_path,
                filename_suffix="_smoothed",
                title_suffix=" (Kalman Filter)",
                key_suffix="_smoothed",
            )
            raw_summary = self._build_raw_summary(flight, telemetry)
            smoothed_summary = self._build_smoothed_summary(smoothed_telemetry)

        video = self._prepare_video_asset(flight_id, report_path)
        manifest = self._build_manifest(
            flight,
            sample_count=len(rows),
            images=images,
            smoothed_images=smoothed_images,
            raw_summary=raw_summary,
            smoothed_summary=smoothed_summary,
            smoothing=self._build_smoothing_metadata(),
            video=video,
        )
        self._write_manifest(flight_id, manifest)
        return manifest

    def get_report_path(self, flight_id: int) -> Path:
        return self.report_dir / f"flight_{flight_id}"

    def get_asset_path(self, flight_id: int, filename: str) -> Path:
        candidate = (self.get_report_path(flight_id) / filename).resolve()
        report_root = self.get_report_path(flight_id).resolve()
        if report_root not in candidate.parents and candidate != report_root:
            raise ValueError("Invalid report asset path")
        return candidate

    def _build_telemetry(self, rows: list[dict[str, Any]]) -> dict[str, list[float]]:
        t0 = rows[0]["timestamp"] if rows else 0.0
        telemetry: dict[str, list[float]] = {
            "elapsed": [],
            "altitude": [],
            "temperature": [],
            "accel_z": [],
            "net_accel": [],
            "vspeed": [],
        }

        for row in rows:
            telemetry["elapsed"].append(row["timestamp"] - t0)
            telemetry["altitude"].append(self._safe_float(row.get("altitude")))
            telemetry["temperature"].append(self._safe_float(row.get("temperature")))
            telemetry["accel_z"].append(self._safe_float(row.get("accel_z")))
            telemetry["net_accel"].append(self._safe_float(row.get("net_accel")))
            telemetry["vspeed"].append(self._safe_float(row.get("vspeed")))

        return telemetry

    def _build_smoothed_telemetry(
        self,
        telemetry: dict[str, list[float]],
        window_size: int,
    ) -> dict[str, list[float]]:
        smoothed = {"elapsed": list(telemetry["elapsed"])}
        smoothed["altitude"] = self._adaptive_kalman_filter(
            telemetry["altitude"], window_size)
        smoothed["temperature"] = self._adaptive_kalman_filter(
            telemetry["temperature"], window_size)
        smoothed["accel_z"] = self._adaptive_kalman_filter(
            telemetry["accel_z"], window_size)
        smoothed["net_accel"] = self._adaptive_kalman_filter(
            telemetry["net_accel"], window_size)
        smoothed["vspeed"] = self._derive_vspeed(
            smoothed["altitude"], smoothed["elapsed"])
        return smoothed

    def _render_chart_set(
        self,
        telemetry: dict[str, list[float]],
        report_path: Path,
        filename_suffix: str = "",
        title_suffix: str = "",
        key_suffix: str = "",
    ) -> list[dict[str, str]]:
        images: list[dict[str, str]] = []
        for spec in CHART_SPECS:
            filename = f"{spec['key']}{filename_suffix}.png"
            self._render_chart(
                telemetry["elapsed"],
                telemetry[spec["field"]],
                spec["title"] + title_suffix,
                spec["ylabel"],
                spec["color"],
                report_path / filename,
            )
            images.append(
                {
                    "key": spec["key"] + key_suffix,
                    "title": spec["title"] + title_suffix,
                    "filename": filename,
                }
            )
        return images

    def _render_chart(
        self,
        elapsed: list[float],
        values: list[float],
        title: str,
        ylabel: str,
        color: str,
        output_path: Path,
    ) -> None:
        fig, ax = plt.subplots(figsize=(10, 4.5), dpi=140)
        fig.patch.set_facecolor("#0a1628")
        ax.set_facecolor("#111d35")
        ax.plot(elapsed, values, color=color, linewidth=2.2)
        ax.set_title(title, color="#ffffff", pad=12, fontsize=14)
        ax.set_xlabel("Time since launch arm (s)", color="#c6d4f2")
        ax.set_ylabel(ylabel, color="#c6d4f2")
        ax.grid(True, color="#29466f", alpha=0.55, linewidth=0.8)
        ax.tick_params(colors="#c6d4f2")
        for spine in ax.spines.values():
            spine.set_color("#1e3a5f")
        fig.tight_layout()
        fig.savefig(output_path, facecolor=fig.get_facecolor(), bbox_inches="tight")
        plt.close(fig)

    def _build_default_summaries(
        self,
        flight: dict[str, Any],
        rows: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        if not rows:
            return self._build_raw_summary(flight), None

        telemetry = self._build_telemetry(rows)
        smoothed_telemetry = self._build_smoothed_telemetry(
            telemetry,
            window_size=MEDIAN_FILTER_WINDOW,
        )
        return (
            self._build_raw_summary(flight, telemetry),
            self._build_smoothed_summary(smoothed_telemetry),
        )

    def _build_raw_summary(
        self,
        flight: dict[str, Any],
        telemetry: dict[str, list[float]] | None = None,
    ) -> dict[str, Any]:
        vertical_accel_max = None
        temperature_max = None
        if telemetry:
            vertical_accel_max = max(telemetry["accel_z"], default=None)
            temperature_max = max(telemetry["temperature"], default=None)

        return {
            "label": "Raw Telemetry",
            "duration": flight.get("duration"),
            "max_altitude": flight.get("max_altitude"),
            "max_vspeed": flight.get("max_vspeed"),
            "max_net_accel": flight.get("max_net_accel"),
            "max_vertical_accel": vertical_accel_max,
            "max_temperature": temperature_max,
        }

    def _build_smoothed_summary(
        self,
        telemetry: dict[str, list[float]],
    ) -> dict[str, Any]:
        max_vspeed = max((abs(v) for v in telemetry["vspeed"]), default=None)
        return {
            "label": "Smoothed Telemetry",
            "duration": telemetry["elapsed"][-1] if telemetry["elapsed"] else 0.0,
            "max_altitude": max(telemetry["altitude"], default=None),
            "max_vspeed": max_vspeed,
            "max_net_accel": max(telemetry["net_accel"], default=None),
            "max_vertical_accel": max(telemetry["accel_z"], default=None),
            "max_temperature": max(telemetry["temperature"], default=None),
        }

    def _median_filter(self, values: list[float], window_size: int) -> list[float]:
        if not values:
            return []
        radius = max(0, window_size // 2)
        smoothed: list[float] = []
        for index in range(len(values)):
            start = max(0, index - radius)
            end = min(len(values), index + radius + 1)
            smoothed.append(median(values[start:end]))
        return smoothed

    def _build_smoothing_metadata(self) -> dict[str, Any]:
        return {
            "method": "adaptive_kalman",
            "display_name": "Adaptive Kalman filter",
            "window_size": MEDIAN_FILTER_WINDOW,
            "outlier_guard": "sliding_median",
        }

    def _adaptive_kalman_filter(
        self,
        values: list[float],
        window_size: int,
    ) -> list[float]:
        if not values:
            return []
        guarded_values = self._suppress_outliers(values, window_size)
        measurement_variance = self._estimate_variance(guarded_values)
        process_variance = max(
            measurement_variance * KALMAN_PROCESS_SCALE,
            KALMAN_MIN_VARIANCE,
        )
        forward = self._run_scalar_kalman_filter(
            guarded_values,
            process_variance,
            measurement_variance,
        )
        backward = list(
            reversed(
                self._run_scalar_kalman_filter(
                    list(reversed(guarded_values)),
                    process_variance,
                    measurement_variance,
                )
            )
        )
        return [
            (forward_value + backward_value) / 2.0
            for forward_value, backward_value in zip(forward, backward)
        ]

    def _suppress_outliers(
        self,
        values: list[float],
        window_size: int,
    ) -> list[float]:
        if not values:
            return []
        radius = max(1, window_size // 2)
        cleaned: list[float] = []
        for index, value in enumerate(values):
            start = max(0, index - radius)
            end = min(len(values), index + radius + 1)
            window = values[start:end]
            local_median = median(window)
            deviations = [abs(sample - local_median) for sample in window]
            local_mad = median(deviations)
            robust_sigma = max(local_mad * 1.4826, KALMAN_MIN_VARIANCE)
            if abs(value - local_median) > OUTLIER_SIGMA * robust_sigma:
                cleaned.append(local_median)
            else:
                cleaned.append(value)
        return cleaned

    def _estimate_variance(self, values: list[float]) -> float:
        if len(values) < 2:
            return 1.0
        deltas = [values[index] - values[index - 1]
                  for index in range(1, len(values))]
        delta_scale = median(abs(delta) for delta in deltas)
        baseline = max(delta_scale, KALMAN_MIN_VARIANCE)
        return baseline * baseline

    def _run_scalar_kalman_filter(
        self,
        measurements: list[float],
        process_variance: float,
        measurement_variance: float,
    ) -> list[float]:
        if not measurements:
            return []

        estimate = measurements[0]
        estimation_error = max(measurement_variance, 1.0)
        filtered = [estimate]

        for measurement in measurements[1:]:
            estimation_error += process_variance
            gain = estimation_error / (estimation_error + measurement_variance)
            estimate += gain * (measurement - estimate)
            estimation_error *= 1.0 - gain
            filtered.append(estimate)

        return filtered

    def _derive_vspeed(self, altitudes: list[float], elapsed: list[float]) -> list[float]:
        if not altitudes:
            return []
        if len(altitudes) == 1:
            return [0.0]

        vspeeds = [0.0]
        for index in range(1, len(altitudes)):
            dt = elapsed[index] - elapsed[index - 1]
            if dt <= 0:
                vspeeds.append(vspeeds[-1])
                continue
            vspeeds.append((altitudes[index] - altitudes[index - 1]) / dt)
        return vspeeds

    def _safe_float(self, value: Any) -> float:
        if value is None:
            return 0.0
        return float(value)

    def _prepare_video_asset(self, flight_id: int, report_path: Path) -> dict[str, Any]:
        mp4_path = report_path / "flight.mp4"
        source_paths = self._get_video_sources(flight_id)
        metadata = self._build_video_metadata(source_paths, mp4_path)
        if not metadata["source_h264_available"]:
            return metadata

        newest_source_mtime = max(path.stat().st_mtime for path in source_paths)
        if metadata["available"] and mp4_path.stat().st_mtime >= newest_source_mtime:
            return metadata

        if len(source_paths) == 1:
            return self._remux_h264_to_mp4(source_paths[0], mp4_path)

        return self._assemble_segments_to_mp4(source_paths, mp4_path, report_path)

    def _build_video_metadata(self, source_paths: list[Path], mp4_path: Path) -> dict[str, Any]:
        return {
            "available": mp4_path.exists() and mp4_path.stat().st_size > 0,
            "filename": "flight.mp4" if mp4_path.exists() and mp4_path.stat().st_size > 0 else None,
            "source_h264_available": bool(source_paths),
            "source_filename": source_paths[0].name if source_paths else None,
            "source_filenames": [path.name for path in source_paths],
            "segment_count": len(source_paths),
            "error": None,
        }

    def _remux_h264_to_mp4(self, source_path: Path, output_path: Path) -> dict[str, Any]:
        if not source_path.exists() or source_path.stat().st_size == 0:
            return {
                "available": False,
                "filename": None,
                "source_h264_available": False,
                "source_filename": source_path.name,
                "source_filenames": [],
                "segment_count": 0,
                "error": "No recorded H.264 file found for this flight.",
            }

        command = [
            "ffmpeg",
            "-y",
            "-framerate",
            str(self.video_fps),
            "-i",
            str(source_path),
            "-c:v",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=90,
            )
            return {
                "available": output_path.exists() and output_path.stat().st_size > 0,
                "filename": output_path.name if output_path.exists() else None,
                "source_h264_available": True,
                "source_filename": source_path.name,
                "source_filenames": [source_path.name],
                "segment_count": 1,
                "error": None,
            }
        except FileNotFoundError:
            return {
                "available": False,
                "filename": None,
                "source_h264_available": True,
                "source_filename": source_path.name,
                "source_filenames": [source_path.name],
                "segment_count": 1,
                "error": "ffmpeg is not installed on the Pi, so the browser video could not be prepared.",
            }
        except subprocess.CalledProcessError as exc:
            error_text = (exc.stderr or exc.stdout or str(exc)).strip()
            return {
                "available": False,
                "filename": None,
                "source_h264_available": True,
                "source_filename": source_path.name,
                "source_filenames": [source_path.name],
                "segment_count": 1,
                "error": error_text[-240:] if error_text else "Video conversion failed.",
            }

    def _assemble_segments_to_mp4(
        self,
        source_paths: list[Path],
        output_path: Path,
        report_path: Path,
    ) -> dict[str, Any]:
        try:
            prepared_segments = self._prepare_mp4_segments(source_paths, report_path)
            concat_file = report_path / "segments.txt"
            concat_file.write_text(
                "".join(
                    f"file '{segment.as_posix()}'\n"
                    for segment in prepared_segments
                ),
                encoding="utf-8",
            )

            command = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return {
                "available": output_path.exists() and output_path.stat().st_size > 0,
                "filename": output_path.name if output_path.exists() else None,
                "source_h264_available": True,
                "source_filename": source_paths[0].name,
                "source_filenames": [path.name for path in source_paths],
                "segment_count": len(source_paths),
                "error": None,
            }
        except FileNotFoundError:
            return {
                "available": False,
                "filename": None,
                "source_h264_available": True,
                "source_filename": source_paths[0].name,
                "source_filenames": [path.name for path in source_paths],
                "segment_count": len(source_paths),
                "error": "ffmpeg is not installed on the Pi, so segmented flight video could not be assembled.",
            }
        except subprocess.CalledProcessError as exc:
            error_text = (exc.stderr or exc.stdout or str(exc)).strip()
            return {
                "available": False,
                "filename": None,
                "source_h264_available": True,
                "source_filename": source_paths[0].name,
                "source_filenames": [path.name for path in source_paths],
                "segment_count": len(source_paths),
                "error": error_text[-240:] if error_text else "Segmented video assembly failed.",
            }

    def _prepare_mp4_segments(self, source_paths: list[Path], report_path: Path) -> list[Path]:
        prepared_segments: list[Path] = []
        for index, source_path in enumerate(source_paths, start=1):
            segment_path = report_path / f"segment_{index:03d}.mp4"
            if not segment_path.exists() or segment_path.stat().st_mtime < source_path.stat().st_mtime:
                command = [
                    "ffmpeg",
                    "-y",
                    "-framerate",
                    str(self.video_fps),
                    "-fflags",
                    "+genpts",
                    "-i",
                    str(source_path),
                    "-c:v",
                    "copy",
                    str(segment_path),
                ]
                subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=90,
                )
            prepared_segments.append(segment_path)
        return prepared_segments

    def _get_video_sources(self, flight_id: int) -> list[Path]:
        segmented_paths = sorted(
            path for path in self.video_dir.glob(f"flight_{flight_id}_part*.h264")
            if path.is_file() and path.stat().st_size > 0
        )
        if segmented_paths:
            return segmented_paths

        legacy_path = self.video_dir / f"flight_{flight_id}.h264"
        if legacy_path.exists() and legacy_path.stat().st_size > 0:
            return [legacy_path]
        return []

    def _build_manifest(
        self,
        flight: dict[str, Any],
        sample_count: int,
        images: list[dict[str, str]],
        smoothed_images: list[dict[str, str]],
        raw_summary: dict[str, Any],
        smoothed_summary: dict[str, Any] | None,
        smoothing: dict[str, Any],
        video: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "flight_id": flight["id"],
            "started_at": flight.get("started_at"),
            "ended_at": flight.get("ended_at"),
            "duration": flight.get("duration"),
            "max_altitude": flight.get("max_altitude"),
            "max_vspeed": flight.get("max_vspeed"),
            "max_net_accel": flight.get("max_net_accel"),
            "state": flight.get("state"),
            "sample_count": sample_count,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "images": images,
            "smoothed_images": smoothed_images,
            "raw_summary": raw_summary,
            "smoothed_summary": smoothed_summary,
            "smoothing": smoothing,
            "video": video,
            "report_available": bool(images or smoothed_images),
        }

    def _manifest_path(self, flight_id: int) -> Path:
        return self.get_report_path(flight_id) / "report.json"

    def _write_manifest(self, flight_id: int, manifest: dict[str, Any]) -> None:
        manifest_path = self._manifest_path(flight_id)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )

    def _read_manifest(self, flight_id: int) -> dict[str, Any] | None:
        manifest_path = self._manifest_path(flight_id)
        if not manifest_path.exists():
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not self._is_manifest_current(manifest):
            return None
        return manifest

    def _is_manifest_current(self, manifest: dict[str, Any]) -> bool:
        expected = self._build_smoothing_metadata()
        actual = manifest.get("smoothing") or {}
        return (
            actual.get("method") == expected["method"]
            and actual.get("window_size") == expected["window_size"]
            and actual.get("outlier_guard") == expected["outlier_guard"]
        )

    def _prepare_dir(self, preferred_dir: str, fallback_dir: str) -> Path:
        candidates = [Path(preferred_dir), Path(fallback_dir)]
        last_error = None

        for candidate in candidates:
            try:
                candidate.mkdir(parents=True, exist_ok=True)
                probe = candidate / ".write_test"
                probe.write_text("ok", encoding="ascii")
                probe.unlink(missing_ok=True)
                return candidate
            except OSError as exc:
                last_error = exc

        raise PermissionError(
            f"No writable report directory available (last error: {last_error})"
        )
