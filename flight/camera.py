import threading
import time
from pathlib import Path
from datetime import datetime
from io import BytesIO

try:
    from picamera2 import Picamera2
    from picamera2.encoders import JpegEncoder, H264Encoder
    from picamera2.outputs import FileOutput
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
            print("Warning: picamera2 not available. Install with: pip install picamera2")

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
            self.camera = Picamera2()

            config = self.camera.create_video_configuration(
                main={"size": (self.width, self.height), "format": "RGB888"},
                controls={"FrameRate": self.fps}
            )
            self.camera.configure(config)

            h264_encoder = H264Encoder(bitrate=5000000)
            file_output = FileOutput(str(self.video_file))

            self.camera.start_recording(h264_encoder, file_output)

            frame_count = 0
            while self.is_running:
                try:
                    request = self.camera.capture_request()
                    buffer = request.make_buffer(0)
                    array = request.make_array(0)
                    request.release()

                    from PIL import Image
                    img = Image.fromarray(array)
                    jpeg_buffer = BytesIO()
                    img.save(jpeg_buffer, format='JPEG', quality=80)
                    jpeg_data = jpeg_buffer.getvalue()

                    with self._lock:
                        self.frame_file.write_bytes(jpeg_data)

                    frame_count += 1
                    time.sleep(1.0 / self.fps)

                except Exception as e:
                    print(f"Frame capture error: {e}")
                    time.sleep(0.1)

        except Exception as e:
            print(f"Camera initialization error: {e}")
        finally:
            self.is_running = False
            if self.camera:
                try:
                    self.camera.stop_recording()
                    self.camera.close()
                except Exception:
                    pass
                self.camera = None

