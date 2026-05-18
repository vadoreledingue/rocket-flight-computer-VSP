import os
import tempfile
import time
import subprocess

from flight.database import FlightDB
from flight.reporting import FlightReportManager


def build_completed_flight(db: FlightDB) -> int:
    flight_id = db.create_flight()
    now = time.time()
    for index in range(6):
        db.insert_reading(
            flight_id=flight_id,
            timestamp=now + index * 0.5,
            pressure=1013.25 - index * 0.5,
            temperature=20.0 + index * 0.3,
            altitude=index * 15.0,
            vspeed=8.0 + index,
            roll=0.0,
            pitch=0.0,
            yaw=0.0,
            accel_x=0.0,
            accel_y=0.1 * index,
            accel_z=9.81 + index * 0.8,
            total_accel=9.81 + index * 0.8,
            net_accel=index * 0.8,
            state="ASCENT" if index < 5 else "LANDED",
        )
    db.end_flight(
        flight_id,
        max_altitude=75.0,
        max_vspeed=13.0,
        max_net_accel=4.0,
        duration=3.0,
    )
    return flight_id


def test_generate_report_images(tmp_path):
    db_path = tmp_path / "flight.db"
    db = FlightDB(str(db_path))
    flight_id = build_completed_flight(db)

    manager = FlightReportManager(
        db,
        report_dir=str(tmp_path / "reports"),
        video_dir=str(tmp_path / "videos"),
    )
    report = manager.generate_for_flight(flight_id)

    assert report is not None
    assert report["report_available"] is True
    assert report["sample_count"] == 6
    assert len(report["images"]) == 4

    report_path = manager.get_report_path(flight_id)
    for image in report["images"]:
        assert (report_path / image["filename"]).exists()

    db.close()


def test_report_uses_existing_mp4_when_present(tmp_path):
    db_path = tmp_path / "flight.db"
    db = FlightDB(str(db_path))
    flight_id = build_completed_flight(db)

    report_dir = tmp_path / "reports"
    report_path = report_dir / f"flight_{flight_id}"
    report_path.mkdir(parents=True, exist_ok=True)
    mp4_path = report_path / "flight.mp4"
    mp4_path.write_bytes(b"mp4-data")

    manager = FlightReportManager(
        db,
        report_dir=str(report_dir),
        video_dir=str(tmp_path / "videos"),
    )
    report = manager.generate_for_flight(flight_id)

    assert report is not None
    assert report["video"]["available"] is True
    assert report["video"]["filename"] == "flight.mp4"

    db.close()


def test_report_discovers_segmented_h264_sources(tmp_path):
    db_path = tmp_path / "flight.db"
    db = FlightDB(str(db_path))
    flight_id = build_completed_flight(db)
    video_dir = tmp_path / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    (video_dir / f"flight_{flight_id}_part002.h264").write_bytes(b"b")
    (video_dir / f"flight_{flight_id}_part001.h264").write_bytes(b"a")

    manager = FlightReportManager(
        db,
        report_dir=str(tmp_path / "reports"),
        video_dir=str(video_dir),
    )

    sources = manager._get_video_sources(flight_id)

    assert [path.name for path in sources] == [
        f"flight_{flight_id}_part001.h264",
        f"flight_{flight_id}_part002.h264",
    ]

    db.close()


def test_report_assembles_segmented_video_metadata(tmp_path, monkeypatch):
    db_path = tmp_path / "flight.db"
    db = FlightDB(str(db_path))
    flight_id = build_completed_flight(db)
    video_dir = tmp_path / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    part1 = video_dir / f"flight_{flight_id}_part001.h264"
    part2 = video_dir / f"flight_{flight_id}_part002.h264"
    part1.write_bytes(b"part1")
    part2.write_bytes(b"part2")

    manager = FlightReportManager(
        db,
        report_dir=str(tmp_path / "reports"),
        video_dir=str(video_dir),
    )

    def fake_run(command, check, capture_output, text, timeout):
        output_path = None
        if str(video_dir) in command[-1]:
            output_path = None
        else:
            output_path = command[-1]
        if output_path.endswith(".mp4"):
            with open(output_path, "wb") as handle:
                handle.write(b"mp4")
        elif output_path.endswith("segments.txt"):
            raise AssertionError("segments.txt should not be passed as ffmpeg output")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("flight.reporting.subprocess.run", fake_run)
    report = manager.generate_for_flight(flight_id)

    assert report is not None
    assert report["video"]["available"] is True
    assert report["video"]["segment_count"] == 2
    assert report["video"]["source_filenames"] == [part1.name, part2.name]
    assert (manager.get_report_path(flight_id) / "flight.mp4").exists()

    db.close()
