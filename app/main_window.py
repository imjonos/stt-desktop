from PySide6 import QtCore, QtWidgets

from app.constants import APP_NAME


class MainWindow(QtWidgets.QWidget):
    start_stop = QtCore.Signal()
    apply_settings = QtCore.Signal(str, str, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(680, 500)
        self._build_ui()
        self._apply_styles()

    def _build_ui(self):
        self.tabs = QtWidgets.QTabWidget()

        self.recording_page = QtWidgets.QWidget()
        recording_layout = QtWidgets.QVBoxLayout(self.recording_page)

        self.status_label = QtWidgets.QLabel("Готов к записи")
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)

        self.action_button = QtWidgets.QPushButton("Начать запись")
        self.action_button.setFixedHeight(60)
        self.action_button.clicked.connect(self.start_stop.emit)

        self.hint_label = QtWidgets.QLabel("Горячая клавиша: Ctrl+Cmd+S")
        self.hint_label.setAlignment(QtCore.Qt.AlignCenter)

        self.error_box = QtWidgets.QPlainTextEdit()
        self.error_box.setReadOnly(True)
        self.error_box.setPlaceholderText("Ошибки будут отображаться здесь")
        self.error_box.setFixedHeight(90)

        recording_layout.addStretch(1)
        recording_layout.addWidget(self.status_label)
        recording_layout.addSpacing(20)
        recording_layout.addWidget(self.action_button)
        recording_layout.addSpacing(12)
        recording_layout.addWidget(self.hint_label)
        recording_layout.addSpacing(10)
        recording_layout.addWidget(self.error_box)
        recording_layout.addStretch(2)

        self.settings_page = QtWidgets.QWidget()
        settings_layout = QtWidgets.QVBoxLayout(self.settings_page)

        self.hotkey_input = QtWidgets.QLineEdit()
        self.hotkey_input.setPlaceholderText("<ctrl>+<cmd>+s")

        self.api_key_input = QtWidgets.QLineEdit()
        self.api_key_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.api_key_input.setPlaceholderText("GigaChat API key")

        self.prompt_input = QtWidgets.QPlainTextEdit()
        self.prompt_input.setPlaceholderText("Системный промпт для обработки текста...")
        self.prompt_input.setMinimumHeight(220)

        self.settings_status_label = QtWidgets.QLabel("")
        self.settings_status_label.setAlignment(QtCore.Qt.AlignLeft)

        self.apply_button = QtWidgets.QPushButton("Применить")
        self.apply_button.setFixedHeight(46)
        self.apply_button.clicked.connect(self._emit_apply_settings)

        form = QtWidgets.QFormLayout()
        form.addRow("Горячая клавиша", self.hotkey_input)
        form.addRow("API ключ GigaChat", self.api_key_input)
        form.addRow("Промпт", self.prompt_input)

        settings_layout.addLayout(form)
        settings_layout.addWidget(self.apply_button)
        settings_layout.addWidget(self.settings_status_label)
        settings_layout.addStretch(1)

        self.tabs.addTab(self.recording_page, "Запись")
        self.tabs.addTab(self.settings_page, "Настройки")

        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.addWidget(self.tabs)

    def _apply_styles(self):
        self.setStyleSheet(
            """
            QWidget { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0f172a, stop:1 #1f2937); color: #e5e7eb; }
            QLabel { font-size: 16px; }
            QTabWidget::pane { border: 1px solid #334155; border-radius: 12px; }
            QTabBar::tab { background: #1e293b; color: #cbd5e1; padding: 10px 16px; margin-right: 6px; border-top-left-radius: 8px; border-top-right-radius: 8px; }
            QTabBar::tab:selected { background: #334155; color: #f8fafc; }
            QLineEdit, QPlainTextEdit { background: #111827; border: 1px solid #374151; border-radius: 10px; padding: 10px; color: #f3f4f6; }
            QPushButton { background: #22c55e; color: #0b111e; font-size: 18px; border: none; border-radius: 14px; padding: 12px; }
            QPushButton:hover { background: #16a34a; }
            QPushButton:pressed { background: #15803d; }
            """
        )

    def set_recording(self, is_recording: bool):
        if is_recording:
            self.status_label.setText("Идет запись…")
            self.action_button.setText("Остановить запись")
        else:
            self.status_label.setText("Готов к записи")
            self.action_button.setText("Начать запись")

    def set_processing(self):
        self.status_label.setText("Обрабатываю текст…")
        self.action_button.setText("Подождите…")
        self.action_button.setEnabled(False)

    def set_idle(self):
        self.action_button.setEnabled(True)
        self.set_recording(False)

    def set_settings(self, hotkey: str, api_key: str, prompt: str):
        self.hotkey_input.setText(hotkey)
        self.api_key_input.setText(api_key)
        self.prompt_input.setPlainText(prompt)

    def set_settings_status(self, text: str, ok: bool):
        color = "#86efac" if ok else "#fca5a5"
        self.settings_status_label.setStyleSheet(f"color: {color};")
        self.settings_status_label.setText(text)

    def _emit_apply_settings(self):
        self.apply_settings.emit(
            self.hotkey_input.text().strip(),
            self.api_key_input.text().strip(),
            self.prompt_input.toPlainText().strip(),
        )

    def set_error_text(self, text: str):
        self.error_box.setPlainText(text)

    def clear_error_text(self):
        self.error_box.clear()
