import threading

import numpy as np
import sounddevice as sd


class Recorder:
    def __init__(self, samplerate: int = 16000, channels: int = 1):
        self.samplerate = samplerate
        self.channels = channels
        self._frames = []
        self._stream = None
        self._lock = threading.Lock()
        self._recording = False

    def start(self):
        if self._recording:
            return
        self._frames = []
        self._recording = True
        self._stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=self.channels,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def stop(self):
        if not self._recording:
            return None
        self._recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._lock:
            if not self._frames:
                return None
            audio = np.concatenate(self._frames, axis=0)
        return audio

    def _callback(self, indata, frames, time_info, status):
        if status:
            pass
        if not self._recording:
            return
        with self._lock:
            self._frames.append(indata.copy())
