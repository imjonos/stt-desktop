import threading

import numpy as np
import sounddevice as sd

from app.logging_utils import LOGGER


class Recorder:
    def __init__(self, samplerate: int = 16000, channels: int = 1):
        self.samplerate = samplerate
        self.target_samplerate = samplerate
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
        try:
            self._stream = self._create_started_input_stream()
        except Exception:
            self._recording = False
            raise

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
        return self._resample_to_target(audio)

    def _callback(self, indata, frames, time_info, status):
        if status:
            LOGGER.warning("Audio input status: %s", status)
        if not self._recording:
            return
        with self._lock:
            self._frames.append(indata.copy())

    def _create_started_input_stream(self):
        errors = []
        for samplerate in self._candidate_samplerates():
            stream = None
            try:
                sd.check_input_settings(
                    samplerate=samplerate,
                    channels=self.channels,
                    dtype="float32",
                )
                stream = sd.InputStream(
                    samplerate=samplerate,
                    channels=self.channels,
                    dtype="float32",
                    callback=self._callback,
                )
                stream.start()
                self.samplerate = int(samplerate)
                LOGGER.info("Audio input opened at %s Hz", self.samplerate)
                return stream
            except Exception as e:
                errors.append(f"{samplerate} Hz: {e}")
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        LOGGER.exception("Failed to close rejected audio stream")

        raise RuntimeError("Не удалось открыть микрофон. " + " | ".join(errors))

    def _candidate_samplerates(self):
        candidates = [self.target_samplerate]
        try:
            default_device = sd.query_devices(kind="input")
            default_samplerate = int(default_device.get("default_samplerate") or 0)
            if default_samplerate:
                candidates.append(default_samplerate)
        except Exception as e:
            LOGGER.warning("Unable to query default input device: %s", e)

        unique = []
        for samplerate in candidates:
            if samplerate > 0 and samplerate not in unique:
                unique.append(samplerate)
        return unique

    def _resample_to_target(self, audio: np.ndarray) -> np.ndarray:
        if self.samplerate == self.target_samplerate or audio.size == 0:
            return audio

        source_len = audio.shape[0]
        target_len = max(1, int(round(source_len * self.target_samplerate / self.samplerate)))
        source_positions = np.linspace(0.0, 1.0, source_len, endpoint=False)
        target_positions = np.linspace(0.0, 1.0, target_len, endpoint=False)

        if audio.ndim == 1:
            return np.interp(target_positions, source_positions, audio).astype(np.float32)

        channels = [
            np.interp(target_positions, source_positions, audio[:, channel])
            for channel in range(audio.shape[1])
        ]
        return np.stack(channels, axis=1).astype(np.float32)
