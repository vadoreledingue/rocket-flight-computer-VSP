import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from flight.camera import DEFAULT_VIDEO_DIR
from flight.database import FlightDB


DEFAULT_REPORT_DIR = "/opt/rocket/data/reports"
FALLBACK_REPORT_DIR = "/tmp/rocket/reports"

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

        video = self._build_video_metadata(
            flight_id, self.get_report_path(flight_id) / "flight.mp4")
        return self._build_manifest(
            flight,
            sample_count=len(self.db.get_readings_for_flight(flight_id)),
            images=[],
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
        report_path = self.get_report_path(flight_id)
        report_path.mkdir(parents=True, exist_ok=True)

        images: list[dict[str, str]] = []
        if rows:
            telemetry = self._build_telemetry(rows)
            for spec in CHART_SPECS:
                filename = f"{spec['key']}.png"
                self._render_chart(
                    telemetry["elapsed"],
                    telemetry[spec["field"]],
                    spec["title"],
                    spec["ylabel"],
                    spec["color"],
                    report_path / filename,
                )
                images.append(
                    {
                        "key": spec["key"],
                        "title": spec["title"],
                        "filename": filename,
                    }
                )

        video = self._prepare_video_asset(flight_id, report_path)
        manifest = self._build_manifest(
            flight,
            sample_count=len(rows),
            images=images,
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
        telemetry: dict[str, list[float]] = {"elapsed": []}
        for spec in CHART_SPECS:
            telemetry[spec["field"]] = []

        for row in rows:
            telemetry["elapsed"].append(row["timestamp"] - t0)
            for spec in CHART_SPECS:
                value = row.get(spec["field"])
                telemetry[spec["field"]].append(0.0 if value is None else value)

        return telemetry

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

    def _prepare_video_asset(self, flight_id: int, report_path: Path) -> dict[str, Any]:
        mp4_path = report_path / "flight.mp4"
        metadata = self._build_video_metadata(flight_id, mp4_path)
        source_path = self.video_dir / f"flight_{flight_id}.h264"
        if not metadata["source_h264_available"]:
            return metadata

        if metadata["available"] and mp4_path.stat().st_mtime >= source_path.stat().st_mtime:
            return metadata

        return self._remux_h264_to_mp4(source_path, mp4_path)

    def _build_video_metadata(self, flight_id: int, mp4_path: Path) -> dict[str, Any]:
        source_path = self.video_dir / f"flight_{flight_id}.h264"
        return {
            "available": mp4_path.exists() and mp4_path.stat().st_size > 0,
            "filename": "flight.mp4" if mp4_path.exists() and mp4_path.stat().st_size > 0 else None,
            "source_h264_available": source_path.exists() and source_path.stat().st_size > 0,
            "source_filename": source_path.name if source_path.exists() else None,
            "error": None,
        }

    def _remux_h264_to_mp4(self, source_path: Path, output_path: Path) -> dict[str, Any]:
        if not source_path.exists() or source_path.stat().st_size == 0:
            return {
                "available": False,
                "filename": None,
                "source_h264_available": False,
                "source_filename": source_path.name,
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
                "error": None,
            }
        except FileNotFoundError:
            return {
                "available": False,
                "filename": None,
                "source_h264_available": True,
                "source_filename": source_path.name,
                "error": "ffmpeg is not installed on the Pi, so the browser video could not be prepared.",
            }
        except subprocess.CalledProcessError as exc:
            error_text = (exc.stderr or exc.stdout or str(exc)).strip()
            return {
                "available": False,
                "filename": None,
                "source_h264_available": True,
                "source_filename": source_path.name,
                "error": error_text[-240:] if error_text else "Video conversion failed.",
            }

    def _build_manifest(
        self,
        flight: dict[str, Any],
        sample_count: int,
        images: list[dict[str, str]],
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
            "video": video,
            "report_available": bool(images),
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
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

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
