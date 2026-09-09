"""
Audio capture — records from the system default input device.

If the user has set up an aggregate device (mic + BlackHole 2ch) as the
default input in System Settings, this captures both mic and system audio
automatically. No device switching — OverAI just uses whatever macOS says
is the default input.
"""

import threading
import struct
import wave
import io
import base64
from typing import Optional, Callable

from AVFoundation import AVAudioEngine

from .logger import Logger

logger = Logger("AudioCapture")

SAMPLE_RATE = 16000
CHANNELS = 1
BUFFER_SIZE = 4096


class AudioCaptureManager:

    def __init__(self):
        self._recording = False
        self._on_complete: Optional[Callable] = None
        self._frames = []
        self._lock = threading.Lock()
        self._engine: Optional[AVAudioEngine] = None
        self._stop_event = threading.Event()

    def start(self, on_complete: Callable[[str], None]):
        if self._recording:
            return
        self._on_complete = on_complete
        self._frames = []
        self._recording = True
        self._stop_event.clear()
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        if not self._recording:
            return
        self._recording = False
        self._stop_event.set()

    def _run(self):
        try:
            engine = AVAudioEngine.alloc().init()
            self._engine = engine
            input_node = engine.inputNode()
            hw_fmt = input_node.inputFormatForBus_(0)

            input_node.installTapOnBus_bufferSize_format_block_(
                0, BUFFER_SIZE, hw_fmt,
                lambda buf, when: self._collect(buf)
            )
            engine.prepare()
            engine.startAndReturnError_(None)
            logger.info("Audio engine started")

            self._stop_event.wait()

            input_node.removeTapOnBus_(0)
            engine.stop()
            self._engine = None

            self._deliver()

        except Exception as e:
            logger.error(f"Capture error: {e}")
            self._recording = False
            if self._on_complete:
                self._on_complete("")

    def _collect(self, buffer):
        if not self._recording:
            return
        try:
            channel_data = buffer.floatChannelData()
            frame_count = int(buffer.frameLength())
            if not channel_data or frame_count == 0:
                return
            ptr = channel_data[0]
            samples = [max(-32768, min(32767, int(ptr[i] * 32767))) for i in range(frame_count)]
            pcm = struct.pack(f"<{len(samples)}h", *samples)
            with self._lock:
                self._frames.append(pcm)
        except Exception as e:
            logger.debug(f"Collect error: {e}")

    def _deliver(self):
        try:
            with self._lock:
                audio = b"".join(self._frames)

            if not audio:
                if self._on_complete:
                    self._on_complete("")
                return

            logger.info(f"Delivering audio: {len(audio)}B")

            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(audio)

            wav_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            if self._on_complete:
                self._on_complete(wav_b64)

        except Exception as e:
            logger.error(f"Deliver error: {e}")
            if self._on_complete:
                self._on_complete("")


_capture_manager: Optional[AudioCaptureManager] = None


def get_audio_capture() -> AudioCaptureManager:
    global _capture_manager
    if _capture_manager is None:
        _capture_manager = AudioCaptureManager()
    return _capture_manager
