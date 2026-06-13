import multiprocessing
import time
import traceback

import numpy as np

from app.logging_utils import LOGGER, enable_native_crash_logging


START_TIMEOUT_SECONDS = 12
STOP_TIMEOUT_SECONDS = 30


class Recorder:
    def __init__(self, samplerate: int = 16000, channels: int = 1):
        self.samplerate = samplerate
        self.target_samplerate = samplerate
        self.channels = channels
        self._process = None
        self._connection = None
        self._recording = False

    def start(self):
        if self._recording:
            return

        context = multiprocessing.get_context("spawn")
        parent_connection, child_connection = context.Pipe()
        process = context.Process(
            target=_recording_process,
            args=(child_connection, self.target_samplerate, self.channels),
            name="stt-audio-recorder",
        )
        process.start()
        child_connection.close()

        self._process = process
        self._connection = parent_connection
        try:
            message = self._receive_message(START_TIMEOUT_SECONDS, "запуска микрофона")
            if message[0] != "ready":
                raise RuntimeError(message[1])
            self.samplerate = int(message[1])
            self._recording = True
            LOGGER.info("Audio recorder process started at %s Hz (pid=%s)", self.samplerate, process.pid)
        except Exception:
            self._cleanup_process(force=True)
            raise

    def stop(self):
        if not self._recording:
            return None

        self._recording = False
        try:
            self._connection.send("stop")
            message = self._receive_message(STOP_TIMEOUT_SECONDS, "остановки микрофона")
            if message[0] == "error":
                raise RuntimeError(message[1])
            if message[0] != "audio":
                raise RuntimeError(f"Неожиданный ответ процесса записи: {message[0]}")
            return message[1]
        finally:
            self._cleanup_process(force=True)

    def _receive_message(self, timeout: float, operation: str):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._connection.poll(0.1):
                try:
                    return self._connection.recv()
                except EOFError:
                    break
            if self._process is None or not self._process.is_alive():
                break

        exit_code = self._process.exitcode if self._process is not None else None
        if exit_code is not None:
            raise RuntimeError(
                f"Процесс записи аварийно завершился во время {operation} "
                f"(код {exit_code}). Проверьте audio-crash.log и драйвер микрофона."
            )
        raise RuntimeError(f"Превышено время ожидания {operation}")

    def _cleanup_process(self, force: bool):
        process = self._process
        connection = self._connection
        self._process = None
        self._connection = None

        if process is not None:
            process.join(timeout=1)
            if force and process.is_alive():
                process.terminate()
                process.join(timeout=2)
            process.close()
        if connection is not None:
            connection.close()


def _recording_process(connection, target_samplerate: int, channels: int):
    enable_native_crash_logging("audio-crash.log")
    stream = None
    try:
        # Importing sounddevice loads the native PortAudio library. Keeping it
        # in this process prevents a faulty DLL or audio driver from taking
        # down the Qt application.
        import sounddevice as sd

        frames = []

        def callback(indata, _frames, _time_info, _status):
            frames.append(indata.copy())

        errors = []
        actual_samplerate = target_samplerate
        for samplerate in _candidate_samplerates(sd, target_samplerate):
            try:
                sd.check_input_settings(
                    samplerate=samplerate,
                    channels=channels,
                    dtype="float32",
                )
                stream = sd.InputStream(
                    samplerate=samplerate,
                    channels=channels,
                    dtype="float32",
                    callback=callback,
                )
                stream.start()
                actual_samplerate = int(samplerate)
                break
            except Exception as error:
                errors.append(f"{samplerate} Hz: {error}")
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
                    stream = None

        if stream is None:
            raise RuntimeError("Не удалось открыть микрофон. " + " | ".join(errors))

        connection.send(("ready", actual_samplerate))
        while True:
            if connection.poll(0.1) and connection.recv() == "stop":
                break

        stream.stop()
        stream.close()
        stream = None

        if not frames:
            connection.send(("audio", None))
            return

        audio = np.concatenate(frames, axis=0)
        audio = _resample_to_target(audio, actual_samplerate, target_samplerate)
        connection.send(("audio", audio))
    except BaseException as error:
        try:
            connection.send(("error", f"{error}\n{traceback.format_exc()}"))
        except Exception:
            pass
    finally:
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass
        connection.close()


def _candidate_samplerates(sounddevice, target_samplerate: int):
    candidates = [target_samplerate]
    try:
        default_device = sounddevice.query_devices(kind="input")
        default_samplerate = int(default_device.get("default_samplerate") or 0)
        if default_samplerate:
            candidates.append(default_samplerate)
    except Exception:
        pass
    return list(dict.fromkeys(rate for rate in candidates if rate > 0))


def _resample_to_target(audio: np.ndarray, samplerate: int, target_samplerate: int) -> np.ndarray:
    if samplerate == target_samplerate or audio.size == 0:
        return audio

    source_len = audio.shape[0]
    target_len = max(1, int(round(source_len * target_samplerate / samplerate)))
    source_positions = np.linspace(0.0, 1.0, source_len, endpoint=False)
    target_positions = np.linspace(0.0, 1.0, target_len, endpoint=False)

    if audio.ndim == 1:
        return np.interp(target_positions, source_positions, audio).astype(np.float32)

    resampled_channels = [
        np.interp(target_positions, source_positions, audio[:, channel])
        for channel in range(audio.shape[1])
    ]
    return np.stack(resampled_channels, axis=1).astype(np.float32)
