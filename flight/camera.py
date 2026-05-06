import io
import threading
import time
import tempfile
import os
from pathlib import Path
from datetime import datetime

try:
    from picamera2 import Picamera2
    from picamera2.encoders import H264Encoder
    from picamera2.outputs import FileOutput
    from PIL import Image
    PICAMERA2_AVAILABLE = True
except ImportError:
    PICAMERA2_AVAILABLE = False


class CameraStreamer:
    """Captures camera video using picamera2 for MJPEG streaming + H.264 recording."""

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
        self.camera = None
        self.capture_thread = None
        self.video_file = None
        self._lock = threading.Lock()

        if not PICAMERA2_AVAILABLE:
            print(
                "Warning: picamera2 not available. Install with: apt install -y python3-picamera2")

    def start(self, flight_id: str = None) -> None:
        """Start camera capture and recording."""
        if self.is_running:
            return

        if not PICAMERA2_AVAILABLE:
            print("Error: picamera2 not available")
            return

        self.is_running = True
        if flight_id is None:
            flight_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.video_file = self.video_dir / f"flight_{flight_id}.h264"

        self.capture_thread = threading.Thread(
            target=self._capture_loop,
            daemon=True
        )
        self.capture_thread.start()

    def stop(self) -> None:
        """Stop camera capture and recording."""
        self.is_running = False
        if self.camera:
            try:
                self.camera.stop_recording()
                self.camera.stop()
                self.camera.close()
            except Exception as e:
                print(f"Error closing camera: {e}")
            self.camera = None
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

    def _capture_loop(self) -> None:
        """Picamera2 capture loop with video recording and frame extraction."""
        try:
            print("[CAMERA] Initializing camera...")
            self.camera = Picamera2()
            print("[CAMERA] Camera initialized")

            config = self.camera.create_video_configuration(
                main={"format": "RGB888", "size": (self.width, self.height)},
                controls={"FrameRate": self.fps}
            )
            self.camera.configure(config)
            print(
                f"[CAMERA] Configured: {self.width}x{self.height} @ {self.fps}fps")

            h264_encoder = H264Encoder(bitrate=5000000)
            file_output = FileOutput(str(self.video_file))

            self.camera.start()
            print("[CAMERA] Camera started")

            self.camera.start_recording(h264_encoder, file_output)
            print(f"[CAMERA] Recording to {self.video_file}")

            frame_count = 0
            tmp_dir = self.frame_file.parent
            tmp_dir.mkdir(parents=True, exist_ok=True)
            print(f"[CAMERA] Frame directory: {tmp_dir}")

            while self.is_running:
                try:
                    array = self.camera.capture_array()
                    if array is None:
                        print("[CAMERA] capture_array() returned None")
                        time.sleep(0.1)
                        continue

                    image = Image.fromarray(array, mode='RGB')
                    stream = io.BytesIO()
                    image.save(stream, format="JPEG", quality=80)
                    jpeg_data = stream.getvalue()

                    with self._lock:
                        with tempfile.NamedTemporaryFile(dir=str(tmp_dir), delete=False, suffix='.jpg') as tmp:
                            tmp.write(jpeg_data)
                            tmp_path = tmp.name
                        os.replace(tmp_path, str(self.frame_file))

                    frame_count += 1
                    if frame_count % 30 == 0:
                        print(
                            f"[CAMERA] Captured {frame_count} frames, last frame size: {len(jpeg_data)} bytes")

                    time.sleep(1.0 / self.fps)

                except Exception as e:
                    print(f"[CAMERA] Frame capture error: {e}")
                    import traceback
                    traceback.print_exc()
                    time.sleep(0.1)

        except Exception as e:
            print(f"[CAMERA] Camera initialization error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.is_running = False
            if self.camera:
                try:
                    self.camera.stop_recording()
                    self.camera.stop()
                    self.camera.close()
                    print("[CAMERA] Camera closed")
                except Exception:
                    pass
                self.camera = None
