import subprocess
import threading
import time
from pathlib import Path
import signal
import os
from datetime import datetime


class CameraStreamer:
    """Captures camera video and provides MJPEG streaming + H.264 recording."""

    def __init__(self, width: int = 1280, height: int = 720, fps: int = 24,
                 video_dir: str = "/opt/rocket/videos",
                 frame_file: str = "/tmp/rocket_camera_frame.jpg") -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.video_dir = Path(video_dir)
        self.video_dir.mkdir(parents=True, exist_ok=True)
        self.frame_file = Path(frame_file)

        self.is_running = False
        self.capture_process = None
        self.capture_thread = None
        self.video_file = None
        self._lock = threading.Lock()

    def start(self, flight_id: str = None) -> None:
        """Start camera capture and recording."""
        if self.is_running:
            return

        self.is_running = True
        if flight_id is None:
            flight_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.video_file = self.video_dir / f"flight_{flight_id}.h264"

        self.capture_thread = threading.Thread(
            target=self._capture_loop,
            kwargs={"flight_id": flight_id},
            daemon=True
        )
        self.capture_thread.start()

    def stop(self) -> None:
        """Stop camera capture and recording."""
        self.is_running = False
        if self.capture_process:
            self.capture_process.terminate()
            try:
                self.capture_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.capture_process.kill()
            self.capture_process = None
        if self.capture_thread:
            self.capture_thread.join(timeout=2)

    def get_frame(self) -> bytes:
        """Returns current JPEG frame (for MJPEG streaming)."""
        try:
            with self._lock:
                if self.frame_file.exists():
                    return self.frame_file.read_bytes()
        except Exception:
            pass
        return None

    def _capture_loop(self, flight_id: str) -> None:
        """Libcamera capture loop with video recording and frame extraction."""
        try:
            cmd = [
                "libcamera-vid",
                "--width", str(self.width),
                "--height", str(self.height),
                "--framerate", str(self.fps),
                "--sensor", "imx708_wide",
                "--autofocus", "continuous",
                "-o", str(self.video_file),
                "-t", "0",  # Run indefinitely
                "--codec", "h264",
                "--inline",
            ]

            self.capture_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=lambda: signal.signal(
                    signal.SIGTERM, signal.SIG_DFL)
            )

            frame_extract_thread = threading.Thread(
                target=self._frame_extract_loop,
                daemon=True
            )
            frame_extract_thread.start()

            self.capture_process.wait()

        except FileNotFoundError:
            print("Error: libcamera-vid not found. Ensure libcamera is installed.")
        except Exception as e:
            print(f"Camera capture error: {e}")
        finally:
            self.is_running = False

    def _frame_extract_loop(self) -> None:
        """Extract JPEG frames from camera using libcamera-still in rapid succession."""
        while self.is_running:
            try:
                temp_frame = f"/tmp/rocket_camera_frame_tmp_{os.getpid()}.jpg"
                cmd = [
                    "libcamera-still",
                    "--width", str(self.width),
                    "--height", str(self.height),
                    "--sensor", "imx708_wide",
                    "--autofocus", "continuous",
                    "-o", temp_frame,
                    "-t", "1",
                    "--nopreview",
                    "-q", "80",
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=1.5
                )

                if result.returncode == 0 and Path(temp_frame).exists():
                    with self._lock:
                        frame_data = Path(temp_frame).read_bytes()
                        self.frame_file.write_bytes(frame_data)
                    Path(temp_frame).unlink(missing_ok=True)

                time.sleep(1.0 / self.fps)

            except subprocess.TimeoutExpired:
                Path(temp_frame).unlink(missing_ok=True)
            except Exception as e:
                print(f"Frame extraction error: {e}")
                time.sleep(0.5)
