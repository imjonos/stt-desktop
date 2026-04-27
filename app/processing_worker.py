import os
import tempfile

import numpy as np
import soundfile as sf
from PySide6 import QtCore
from gigachat import GigaChat
from gigachat.models import Chat, Messages

from app.config_model import AppConfig


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

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        sf.write(path, waveform, 16000)
        result = self.whisper_model.transcribe(
            path,
            language="ru",
            task="transcribe",
            temperature=0.0,
            fp16=False,
        )
        try:
            os.unlink(path)
        except OSError:
            pass
        text = (result.get("text") or "").strip()
        if text:
            return text

        segments = result.get("segments") or []
        seg_text = " ".join((seg.get("text") or "").strip() for seg in segments).strip()
        return seg_text

    def _load_prompt(self) -> str:
        if self.config.prompt_path.exists():
            return self.config.prompt_path.read_text(encoding="utf-8").strip()
        return "Сделай текст красивым и грамотным."

    def _process_text(self, prompt: str, text: str) -> str:
        with GigaChat(credentials=self.config.gigachat_key, verify_ssl_certs=False) as giga:
            chat = Chat(
                model=self.config.gigachat_model,
                messages=[
                    Messages(role="system", content=prompt),
                    Messages(role="user", content=text),
                ]
            )
            response = giga.chat(chat)
            print(response.choices[0].message.content.strip())
            return response.choices[0].message.content.strip()
