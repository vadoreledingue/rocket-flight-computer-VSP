import threading
import time
import os
from pathlib import Path
from datetime import datetime

try:
    from picamera2 import Picamera2
    from picamera2.encoders import H264Encoder
    from picamera2.outputs import FileOutput
    PICAMERA2_AVAILABLE = True
except ImportError:
    PICAMERA2_AVAILABLE = False


DEFAULT_VIDEO_DIR = "/opt/rocket/data/videos"
FALLBACK_VIDEO_DIR = "/tmp/rocket/videos"
DEFAULT_FRAME_FILE = "/dev/shm/rocket_camera_frame.jpg"


class CameraStreamer:
    """Captures camera video using picamera2 for MJPEG streaming + H.264 recording."""

    def __init__(self, width: int = 1280, height: int = 720, fps: int = 24,
                 video_dir: str = DEFAULT_VIDEO_DIR,
                 frame_file: str = DEFAULT_FRAME_FILE,
                 stream_fps: int = 6) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.stream_fps = max(1, min(stream_fps, fps))
        configured_video_dir = os.environ.get("ROCKET_VIDEO_DIR", video_dir)
        self.video_dir = self._prepare_video_dir(configured_video_dir)
        self.frame_file = Path(frame_file)

        self.is_running = False
        self.camera = None
        self.capture_thread = None
        self.video_file = None
        self._lock = threading.Lock()
        self.last_error: str | None = None
        self.last_frame_at: float | None = None

        if not PICAMERA2_AVAILABLE:
            print("[CAMERA] Warning: picamera2 not available. Install with: apt install -y python3-picamera2")

    def start(self, flight_id: str = None) -> None:
        """Start camera capture and recording."""
        if self.is_running:
            print(f"[CAMERA] Already running, ignoring start request")
            return

        if not PICAMERA2_AVAILABLE:
            print("[CAMERA] Error: picamera2 not available, cannot start")
            return

        self.last_error = None
        self.last_frame_at = None
        self._remove_frame_file()
        self.is_running = True
        if flight_id is None:
            flight_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.video_file = self.video_dir / f"flight_{flight_id}.h264"

        print(f"[CAMERA] Starting capture thread (flight_id={flight_id})")
        self.capture_thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name="CameraCapture"
        )
        self.capture_thread.start()

    def stop(self) -> None:
        """Stop camera capture and recording."""
        if not self.is_running:
            self._remove_frame_file()
            return

        print("[CAMERA] Stopping capture...")
        self.is_running = False

        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=3)
            print("[CAMERA] Capture thread stopped")

        self._close_camera()
        self._remove_frame_file()

    def _capture_loop(self) -> None:
        """Picamera2 capture loop with H.264 recording and JPEG frame extraction."""
        try:
            print("[CAMERA] Initializing Picamera2...")
            self.camera = Picamera2()

            config = self.camera.create_video_configuration(
                main={"size": (self.width, self.height), "format": "YUV420"},
                controls={"FrameRate": self.fps},
                buffer_count=6,
            )
            self.camera.configure(config)
            print(f"[CAMERA] Configured: {self.width}x{self.height} @ {self.fps}fps")

            h264_encoder = H264Encoder(bitrate=2000000, repeat=True)
            file_output = FileOutput(str(self.video_file))

            self.camera.start()
            print("[CAMERA] Camera started")

            self.camera.start_recording(h264_encoder, file_output)
            print(f"[CAMERA] Recording H.264 to {self.video_file}")

            frame_count = 0
            last_log = time.time()
            last_preview_at = 0.0
            preview_interval = 1.0 / self.stream_fps
            frame_dir = self.frame_file.parent
            frame_dir.mkdir(parents=True, exist_ok=True)

            while self.is_running:
                try:
                    request = self.camera.capture_request()
                    if request is None:
                        time.sleep(0.01)
                        continue

                    now = time.time()
                    try:
                        if now - last_preview_at < preview_interval:
                            continue

                        tmp_path = self._temp_frame_path()
                        request.save("main", str(tmp_path))
                        with self._lock:
                            os.replace(str(tmp_path), str(self.frame_file))

                        self.last_frame_at = now
                        last_preview_at = now
                        frame_count += 1
                        if now - last_log >= 2.0:
                            try:
                                frame_size = self.frame_file.stat().st_size
                            except FileNotFoundError:
                                frame_size = 0
                            print(f"[CAMERA] {frame_count} preview frames, latest: {frame_size} bytes")
                            last_log = now
                    finally:
                        request.release()

                except Exception as e:
                    self.last_error = str(e)
                    print(f"[CAMERA] Frame capture error: {e}")
                    time.sleep(0.1)

        except Exception as e:
            self.last_error = str(e)
            print(f"[CAMERA] Init error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.is_running = False
            self._close_camera()
            self._remove_frame_file()

    def _close_camera(self) -> None:
        if not self.camera:
            return
        try:
            self.camera.stop_recording()
        except Exception:
            pass
        try:
            self.camera.stop()
        except Exception:
            pass
        try:
            self.camera.close()
            print("[CAMERA] Camera closed")
        except Exception as e:
            print(f"[CAMERA] Error closing camera: {e}")
        finally:
            self.camera = None

    def _remove_frame_file(self) -> None:
        try:
            self.frame_file.unlink(missing_ok=True)
        except Exception as e:
            print(f"[CAMERA] Could not remove frame file: {e}")

    def _temp_frame_path(self) -> Path:
        if self.frame_file.suffix:
            return self.frame_file.with_name(
                f"{self.frame_file.stem}.tmp{self.frame_file.suffix}"
            )
        return self.frame_file.with_name(f"{self.frame_file.name}.tmp.jpg")

    def _prepare_video_dir(self, preferred_dir: str) -> Path:
        candidates = [Path(preferred_dir), Path(FALLBACK_VIDEO_DIR)]
        last_error = None

        for candidate in candidates:
            try:
                candidate.mkdir(parents=True, exist_ok=True)
                probe = candidate / ".write_test"
                probe.write_text("ok", encoding="ascii")
                probe.unlink(missing_ok=True)
                print(f"[CAMERA] Video directory ready: {candidate}")
                return candidate
            except OSError as e:
                last_error = e
                print(f"[CAMERA] Video directory not writable: {candidate} ({e})")

        raise PermissionError(
            f"No writable video directory available (last error: {last_error})"
        )
