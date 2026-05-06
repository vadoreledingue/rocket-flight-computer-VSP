import io
import threading
import time
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
                 frame_file: str = "/dev/shm/rocket_camera_frame.jpg") -> None:
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
            print("[CAMERA] Warning: picamera2 not available. Install with: apt install -y python3-picamera2")

    def start(self, flight_id: str = None) -> None:
        """Start camera capture and recording."""
        if self.is_running:
            print(f"[CAMERA] Already running, ignoring start request")
            return

        if not PICAMERA2_AVAILABLE:
            print("[CAMERA] Error: picamera2 not available, cannot start")
            return

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
            return

        print("[CAMERA] Stopping capture...")
        self.is_running = False

        if self.camera:
            try:
                self.camera.stop_recording()
                self.camera.stop()
                self.camera.close()
                print("[CAMERA] Camera closed successfully")
            except Exception as e:
                print(f"[CAMERA] Error closing camera: {e}")
            finally:
                self.camera = None

        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=3)
            print("[CAMERA] Capture thread stopped")

    def _capture_loop(self) -> None:
        """Picamera2 capture loop with H.264 recording and JPEG frame extraction."""
        try:
            print("[CAMERA] Initializing Picamera2...")
            self.camera = Picamera2()

            config = self.camera.create_video_configuration(
                main={"size": (self.width, self.height), "format": "YUV420"}
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
            frame_dir = self.frame_file.parent
            frame_dir.mkdir(parents=True, exist_ok=True)

            while self.is_running:
                try:
                    request = self.camera.capture_request()
                    if request is None:
                        time.sleep(0.01)
                        continue

                    try:
                        array = request.make_array("main")

                        if array is None or array.size == 0:
                            print("[CAMERA] Invalid capture array")
                            request.release()
                            time.sleep(0.01)
                            continue

                        image = Image.frombytes('YCbCr', (self.width, self.height),
                                              array.tobytes(), 'raw', 'YCbCr')
                        image_rgb = image.convert('RGB')

                        stream = io.BytesIO()
                        image_rgb.save(stream, format="JPEG", quality=75)
                        jpeg_data = stream.getvalue()

                        with self._lock:
                            tmp_path = str(self.frame_file) + ".tmp"
                            with open(tmp_path, 'wb') as f:
                                f.write(jpeg_data)
                            os.replace(tmp_path, str(self.frame_file))

                        frame_count += 1
                        now = time.time()
                        if now - last_log >= 2.0:
                            print(f"[CAMERA] {frame_count} frames, latest: {len(jpeg_data)} bytes")
                            last_log = now

                    finally:
                        request.release()

                except Exception as e:
                    print(f"[CAMERA] Frame capture error: {e}")
                    time.sleep(0.1)

        except Exception as e:
            print(f"[CAMERA] Init error: {e}")
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
