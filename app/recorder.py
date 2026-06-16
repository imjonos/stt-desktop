import multiprocessing
import platform
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
        self._stop_event = None
        self._recording = False

    def start(self):
        if self._recording:
            return

        context = multiprocessing.get_context("spawn")
        use_stop_event = platform.system() == "Windows"
        parent_connection, child_connection = context.Pipe(duplex=not use_stop_event)
        stop_event = context.Event() if use_stop_event else None
        process = context.Process(
            target=_recording_process,
            args=(child_connection, stop_event, self.target_samplerate, self.channels),
            name="stt-audio-recorder",
        )
        process.start()
        child_connection.close()

        self._process = process
        self._connection = parent_connection
        self._stop_event = stop_event
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
            if self._stop_event is not None:
                self._stop_event.set()
            else:
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
        self._stop_event = None

        if process is not None:
            process.join(timeout=1)
            if force and process.is_alive():
                process.terminate()
                process.join(timeout=2)
            process.close()
        if connection is not None:
            connection.close()


def _recording_process(connection, stop_event, target_samplerate: int, channels: int):
    enable_native_crash_logging("audio-crash.log")
    if platform.system() == "Windows":
        try:
            _recording_process_winmm(connection, stop_event, target_samplerate, channels)
            return
        except BaseException:
            try:
                connection.send(("error", traceback.format_exc()))
            except Exception:
                pass
            try:
                connection.close()
            except Exception:
                pass
            return

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
            if stop_event is not None:
                if stop_event.is_set():
                    break
                time.sleep(0.1)
            elif connection.poll(0.1) and connection.recv() == "stop":
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


def _recording_process_winmm(connection, stop_event, target_samplerate: int, channels: int):
    import ctypes
    from ctypes import wintypes

    if channels != 1:
        raise RuntimeError("Windows recorder supports mono input only")

    winmm = ctypes.WinDLL("winmm")
    CALLBACK_NULL = 0
    WAVE_FORMAT_PCM = 1
    WAVE_MAPPER = 0xFFFFFFFF
    WHDR_DONE = 0x00000001
    MMSYSERR_NOERROR = 0

    class WAVEFORMATEX(ctypes.Structure):
        _fields_ = [
            ("wFormatTag", wintypes.WORD),
            ("nChannels", wintypes.WORD),
            ("nSamplesPerSec", wintypes.DWORD),
            ("nAvgBytesPerSec", wintypes.DWORD),
            ("nBlockAlign", wintypes.WORD),
            ("wBitsPerSample", wintypes.WORD),
            ("cbSize", wintypes.WORD),
        ]

    class WAVEHDR(ctypes.Structure):
        _fields_ = [
            ("lpData", ctypes.c_void_p),
            ("dwBufferLength", wintypes.DWORD),
            ("dwBytesRecorded", wintypes.DWORD),
            ("dwUser", ctypes.c_size_t),
            ("dwFlags", wintypes.DWORD),
            ("dwLoops", wintypes.DWORD),
            ("lpNext", ctypes.c_void_p),
            ("reserved", ctypes.c_size_t),
        ]

    winmm.waveInOpen.argtypes = [
        ctypes.POINTER(ctypes.c_void_p),
        wintypes.UINT,
        ctypes.POINTER(WAVEFORMATEX),
        ctypes.c_size_t,
        ctypes.c_size_t,
        wintypes.DWORD,
    ]
    winmm.waveInOpen.restype = wintypes.UINT
    winmm.waveInPrepareHeader.argtypes = [ctypes.c_void_p, ctypes.POINTER(WAVEHDR), wintypes.UINT]
    winmm.waveInPrepareHeader.restype = wintypes.UINT
    winmm.waveInAddBuffer.argtypes = [ctypes.c_void_p, ctypes.POINTER(WAVEHDR), wintypes.UINT]
    winmm.waveInAddBuffer.restype = wintypes.UINT
    winmm.waveInStart.argtypes = [ctypes.c_void_p]
    winmm.waveInStart.restype = wintypes.UINT
    winmm.waveInStop.argtypes = [ctypes.c_void_p]
    winmm.waveInStop.restype = wintypes.UINT
    winmm.waveInReset.argtypes = [ctypes.c_void_p]
    winmm.waveInReset.restype = wintypes.UINT
    winmm.waveInUnprepareHeader.argtypes = [ctypes.c_void_p, ctypes.POINTER(WAVEHDR), wintypes.UINT]
    winmm.waveInUnprepareHeader.restype = wintypes.UINT
    winmm.waveInClose.argtypes = [ctypes.c_void_p]
    winmm.waveInClose.restype = wintypes.UINT
    winmm.waveInGetErrorTextW.argtypes = [wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
    winmm.waveInGetErrorTextW.restype = wintypes.UINT

    def raise_if_error(result: int, operation: str):
        if result == MMSYSERR_NOERROR:
            return
        message = ctypes.create_unicode_buffer(256)
        winmm.waveInGetErrorTextW(result, message, len(message))
        detail = message.value or f"WinMM error {result}"
        raise RuntimeError(f"{operation}: {detail}")

    def make_format(samplerate: int):
        bits_per_sample = 16
        block_align = channels * bits_per_sample // 8
        return WAVEFORMATEX(
            WAVE_FORMAT_PCM,
            channels,
            samplerate,
            samplerate * block_align,
            block_align,
            bits_per_sample,
            0,
        )

    handle = ctypes.c_void_p()
    actual_samplerate = None
    open_errors = []
    for samplerate in _candidate_winmm_samplerates(target_samplerate):
        fmt = make_format(samplerate)
        result = winmm.waveInOpen(
            ctypes.byref(handle),
            WAVE_MAPPER,
            ctypes.byref(fmt),
            0,
            0,
            CALLBACK_NULL,
        )
        if result == MMSYSERR_NOERROR:
            actual_samplerate = samplerate
            break
        message = ctypes.create_unicode_buffer(256)
        winmm.waveInGetErrorTextW(result, message, len(message))
        open_errors.append(f"{samplerate} Hz: {message.value or result}")

    if actual_samplerate is None:
        raise RuntimeError("Не удалось открыть микрофон через WinMM. " + " | ".join(open_errors))

    header_size = ctypes.sizeof(WAVEHDR)
    buffer_count = 8
    buffer_milliseconds = 100
    bytes_per_sample = 2
    buffer_size = max(
        1024,
        int(actual_samplerate * channels * bytes_per_sample * buffer_milliseconds / 1000),
    )
    buffers = [ctypes.create_string_buffer(buffer_size) for _ in range(buffer_count)]
    headers = []
    frames = []

    try:
        for buffer in buffers:
            header = WAVEHDR(
                ctypes.cast(buffer, ctypes.c_void_p),
                buffer_size,
                0,
                0,
                0,
                0,
                None,
                0,
            )
            raise_if_error(winmm.waveInPrepareHeader(handle, ctypes.byref(header), header_size), "waveInPrepareHeader")
            raise_if_error(winmm.waveInAddBuffer(handle, ctypes.byref(header), header_size), "waveInAddBuffer")
            headers.append(header)

        raise_if_error(winmm.waveInStart(handle), "waveInStart")
        connection.send(("ready", actual_samplerate))

        should_stop = False
        while not should_stop:
            should_stop = stop_event.is_set()
            for index, header in enumerate(headers):
                if header.dwFlags & WHDR_DONE:
                    if header.dwBytesRecorded:
                        frames.append(bytes(buffers[index].raw[: header.dwBytesRecorded]))
                    header.dwBytesRecorded = 0
                    header.dwFlags &= ~WHDR_DONE
                    if not should_stop:
                        raise_if_error(winmm.waveInAddBuffer(handle, ctypes.byref(header), header_size), "waveInAddBuffer")
            if not should_stop:
                time.sleep(0.01)

        winmm.waveInStop(handle)
        winmm.waveInReset(handle)

        for index, header in enumerate(headers):
            if header.dwBytesRecorded:
                frames.append(bytes(buffers[index].raw[: header.dwBytesRecorded]))
                header.dwBytesRecorded = 0

        if not frames:
            connection.send(("audio", None))
            return

        raw_audio = b"".join(frames)
        audio = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32) / 32768.0
        audio = audio.reshape(-1, channels)
        audio = _resample_to_target(audio, actual_samplerate, target_samplerate)
        connection.send(("audio", audio))
    finally:
        if handle.value:
            try:
                winmm.waveInReset(handle)
            except Exception:
                pass
            for header in headers:
                try:
                    winmm.waveInUnprepareHeader(handle, ctypes.byref(header), header_size)
                except Exception:
                    pass
            try:
                winmm.waveInClose(handle)
            except Exception:
                pass
        connection.close()


def _candidate_winmm_samplerates(target_samplerate: int):
    return list(dict.fromkeys(rate for rate in (target_samplerate, 44100, 48000) if rate > 0))


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
