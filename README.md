# STT Desktop

Кроссплатформенное десктоп-приложение на Python:
- Глобальная горячая клавиша для записи
- Локальный Whisper для STT
- Постобработка текста через GigaChat
- Вставка результата в активное поле (Cmd+V / Ctrl+V)

## Быстрый старт

1) Установите зависимости
```bash
pip install -r requirements.txt
```

2) Для запуска из IDE/консоли создайте `.env` в корне проекта
```bash
cp .env.example .env
```

3) Запуск
```bash
python -m app.main
```

## Где хранятся файлы

Для собранного приложения (`.app` / `.exe`) рабочая папка:
- `~/.stt-desktop/`

В этой папке лежат:
- `~/.stt-desktop/.env` — конфиг приложения
- `~/.stt-desktop/prompt.md` — текущий промпт (можно открыть и отредактировать вручную)
- `~/.stt-desktop/whisper-cache/` — кэш моделей Whisper
- `~/.stt-desktop/app-errors.log` — лог ошибок приложения

Важно:
- В режиме IDE/консоли `.env` и `prompt.md` берутся из корня проекта.
- В собранной версии `.env` и `prompt.md` используются из `~/.stt-desktop/`.

## Переменные `.env`

- `GIGACHAT_API_KEY` — ключ API
- `GIGACHAT_MODEL` — модель GigaChat для постобработки текста (по умолчанию `GigaChat`)
- `HOTKEY` — горячая клавиша в формате `pynput` (пример: `<ctrl>+<cmd>+s`)
- `PROMPT_PATH` — путь к `prompt.md` (обычно `prompt.md`)
- `WHISPER_MODEL` — модель Whisper (`tiny` быстрее стартует, `base` точнее и используется по умолчанию)
- `WHISPER_SSL_NO_VERIFY` — отключение SSL-проверки при загрузке модели (если нужно в корпоративной сети)
- `GIGACHAT_SSL_NO_VERIFY` — отключение SSL-проверки для GigaChat (если нужно)

## Разрешения

macOS для собранного `.app`:
- `System Settings -> Privacy & Security -> Microphone`
- `System Settings -> Privacy & Security -> Accessibility`
- `System Settings -> Privacy & Security -> Input Monitoring`

Без этих разрешений запись и вставка могут не работать.

## Сборка

```bash
python build.py
```

На macOS сборка идет через `.spec` (с plist и правами на микрофон).
