import numpy as np
from PySide6 import QtCore

from app.ai_client import AIClientConfig, create_ai_client
from app.config_model import AppConfig
from app.logging_utils import LOGGER


class ProcessingWorker(QtCore.QObject):
    finished = QtCore.Signal(str)
    error = QtCore.Signal(str)

    def __init__(self, audio: np.ndarray, config: AppConfig, whisper_model):
        super().__init__()
        self.audio = audio
        self.config = config
        self.whisper_model = whisper_model

    def run(self):
        try:
            text = self._transcribe(self.audio)
            if not text.strip():
                self.error.emit("Не удалось распознать речь (пустой результат)")
                return
            prompt = self._load_prompt()
            final_text = self._process_text(prompt, text)
            self.finished.emit(final_text)
        except Exception as e:
            LOGGER.exception("Audio processing failed")
            self.error.emit(str(e))

    def _transcribe(self, audio: np.ndarray) -> str:
        waveform = np.asarray(audio, dtype=np.float32)
        if waveform.ndim == 2:
            waveform = waveform.mean(axis=1)
        waveform = np.ascontiguousarray(waveform.squeeze())

        if waveform.size == 0:
            raise RuntimeError("Пустая аудиозапись")

        rms = float(np.sqrt(np.mean(np.square(waveform))))
        if rms < 1e-4:
            raise RuntimeError("Слишком тихий сигнал (проверьте микрофон и права доступа)")

        if rms < 0.01:
            gain = min(20.0, 0.03 / (rms + 1e-8))
            waveform = np.clip(waveform * gain, -1.0, 1.0)

        result = self.whisper_model.transcribe(
            waveform,
            language="ru",
            task="transcribe",
            temperature=0.0,
            fp16=False,
        )
        text = (result.get("text") or "").strip()
        if text:
            return text

        segments = result.get("segments") or []
        seg_text = " ".join((seg.get("text") or "").strip() for seg in segments).strip()
        return seg_text

    def _load_prompt(self) -> str:
        for mode in self.config.prompt_modes:
            if mode.id == self.config.active_prompt_mode_id:
                return mode.prompt
        if self.config.prompt_modes:
            return self.config.prompt_modes[0].prompt
        if self.config.prompt_path.exists():
            return self.config.prompt_path.read_text(encoding="utf-8").strip()
        return "Сделай текст красивым и грамотным."

    def _process_text(self, prompt: str, text: str) -> str:
        ai_config = AIClientConfig(
            provider=self.config.ai_provider,
            api_key=self.config.ai_api_key,
            model=self.config.ai_model,
            base_url=self.config.ai_base_url,
        )
        client = create_ai_client(ai_config)
        return client.process_text(prompt, text)
