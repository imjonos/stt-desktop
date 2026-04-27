from PySide6 import QtCore, QtWidgets

from app.constants import APP_NAME


class MainWindow(QtWidgets.QWidget):
    start_stop = QtCore.Signal()
    apply_settings = QtCore.Signal(str, str, str, str, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(680, 460)
        self.resize(760, 500)
        self._build_ui()
        self._apply_styles()

    def _build_ui(self):
        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(20, 18, 20, 18)
        root_layout.setSpacing(12)

        title = QtWidgets.QLabel(APP_NAME)
        title.setObjectName("TitleLabel")
        subtitle = QtWidgets.QLabel("Быстрая диктовка, аккуратная обработка и вставка текста по горячей клавише")
        subtitle.setObjectName("SubtitleLabel")

        root_layout.addWidget(title)
        root_layout.addWidget(subtitle)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setObjectName("MainTabs")

        self.recording_page = QtWidgets.QWidget()
        recording_layout = QtWidgets.QVBoxLayout(self.recording_page)
        recording_layout.setContentsMargins(26, 22, 26, 22)
        recording_layout.setSpacing(14)

        self.status_card = QtWidgets.QFrame()
        self.status_card.setObjectName("StatusCard")
        status_layout = QtWidgets.QVBoxLayout(self.status_card)
        status_layout.setContentsMargins(24, 22, 24, 22)
        status_layout.setSpacing(12)

        self.status_dot = QtWidgets.QLabel()
        self.status_dot.setObjectName("StatusDot")
        self.status_dot.setFixedSize(14, 14)

        self.status_label = QtWidgets.QLabel("Готов к записи")
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)
        self.status_label.setObjectName("StatusLabel")

        self.status_detail_label = QtWidgets.QLabel("Модель готовится в фоне. После загрузки можно начинать запись.")
        self.status_detail_label.setAlignment(QtCore.Qt.AlignCenter)
        self.status_detail_label.setWordWrap(True)
        self.status_detail_label.setObjectName("StatusDetailLabel")

        status_header = QtWidgets.QHBoxLayout()
        status_header.addStretch(1)
        status_header.addWidget(self.status_dot)
        status_header.addWidget(self.status_label)
        status_header.addStretch(1)
        status_layout.addLayout(status_header)
        status_layout.addWidget(self.status_detail_label)

        self.action_button = QtWidgets.QPushButton("Начать запись")
        self.action_button.setFixedHeight(60)
        self.action_button.setCursor(QtCore.Qt.PointingHandCursor)
        self.action_button.clicked.connect(self.start_stop.emit)

        self.hint_label = QtWidgets.QLabel("Горячая клавиша: Ctrl+Cmd+S")
        self.hint_label.setAlignment(QtCore.Qt.AlignCenter)
        self.hint_label.setObjectName("HintLabel")

        self.error_box = QtWidgets.QPlainTextEdit()
        self.error_box.setReadOnly(True)
        self.error_box.setPlaceholderText("Ошибки будут отображаться здесь")
        self.error_box.setFixedHeight(96)
        self.error_box.setObjectName("ErrorBox")

        recording_layout.addWidget(self.status_card)
        recording_layout.addWidget(self.action_button)
        recording_layout.addWidget(self.hint_label)
        recording_layout.addWidget(self.error_box)
        recording_layout.addStretch(1)

        self.settings_page = QtWidgets.QWidget()
        settings_layout = QtWidgets.QVBoxLayout(self.settings_page)
        settings_layout.setContentsMargins(26, 20, 26, 22)
        settings_layout.setSpacing(12)

        settings_content = QtWidgets.QWidget()
        settings_content.setObjectName("SettingsContent")
        settings_content_layout = QtWidgets.QVBoxLayout(settings_content)
        settings_content_layout.setContentsMargins(0, 0, 8, 0)
        settings_content_layout.setSpacing(0)

        self.hotkey_input = QtWidgets.QLineEdit()
        self.hotkey_input.setPlaceholderText("<ctrl>+<cmd>+s")
        self.hotkey_input.setMinimumWidth(260)

        self.api_key_input = QtWidgets.QLineEdit()
        self.api_key_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.api_key_input.setPlaceholderText("GigaChat API key")
        self.api_key_input.setMinimumWidth(280)

        self.gigachat_model_input = QtWidgets.QComboBox()
        self.gigachat_model_input.setEditable(True)
        self.gigachat_model_input.addItems(["GigaChat", "GigaChat-Pro", "GigaChat-Max"])
        self.gigachat_model_input.setCurrentText("GigaChat")
        self.gigachat_model_input.setMinimumWidth(240)

        self.whisper_model_input = QtWidgets.QComboBox()
        self.whisper_model_input.setEditable(True)
        self.whisper_model_input.addItems(["tiny", "base", "small", "medium", "large"])
        self.whisper_model_input.setCurrentText("base")
        self.whisper_model_input.setMinimumWidth(180)

        self.prompt_input = QtWidgets.QPlainTextEdit()
        self.prompt_input.setPlaceholderText("Системный промпт для обработки текста...")
        self.prompt_input.setMinimumHeight(170)
        self.prompt_input.setMinimumWidth(360)

        self.settings_status_label = QtWidgets.QLabel("")
        self.settings_status_label.setAlignment(QtCore.Qt.AlignLeft)
        self.settings_status_label.setWordWrap(True)

        self.apply_button = QtWidgets.QPushButton("Применить")
        self.apply_button.setFixedHeight(46)
        self.apply_button.setCursor(QtCore.Qt.PointingHandCursor)
        self.apply_button.clicked.connect(self._emit_apply_settings)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignLeft)
        form.setFormAlignment(QtCore.Qt.AlignTop)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        form.addRow("Горячая клавиша", self.hotkey_input)
        form.addRow("API ключ GigaChat", self.api_key_input)
        form.addRow("Модель GigaChat", self.gigachat_model_input)
        form.addRow("Модель Whisper", self.whisper_model_input)
        form.addRow("Промпт", self.prompt_input)

        settings_content_layout.addLayout(form)
        settings_content_layout.addStretch(1)

        self.settings_scroll = QtWidgets.QScrollArea()
        self.settings_scroll.setObjectName("SettingsScroll")
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.settings_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.settings_scroll.viewport().setObjectName("SettingsViewport")
        self.settings_scroll.setWidget(settings_content)

        settings_layout.addWidget(self.settings_scroll, 1)
        settings_layout.addWidget(self.settings_status_label)
        settings_layout.addWidget(self.apply_button)

        self.tabs.addTab(self.recording_page, "Запись")
        self.tabs.addTab(self.settings_page, "Настройки")

        root_layout.addWidget(self.tabs)

    def _apply_styles(self):
        self.setStyleSheet(
            """
            QWidget {
                background: #101418;
                color: #e8edf0;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                font-size: 14px;
            }
            QLabel { background: transparent; }
            #TitleLabel {
                color: #f7faf8;
                font-size: 24px;
                font-weight: 700;
            }
            #SubtitleLabel {
                color: #9aa7a7;
                font-size: 13px;
            }
            #MainTabs {
                background: #101418;
                border: 0;
            }
            QTabWidget::pane {
                background: #101418;
                border: 0;
                top: -1px;
            }
            QTabWidget::tab-bar {
                left: 0;
            }
            QTabBar {
                background: #101418;
            }
            QTabBar::base {
                background: #101418;
                border: 0;
            }
            QTabBar::tab {
                background: #171f25;
                color: #a9b6b6;
                padding: 9px 18px;
                margin-right: 8px;
                border: 1px solid #263139;
                border-radius: 7px;
            }
            QTabBar::tab:selected {
                background: #223039;
                color: #f5fbf8;
                border-color: #2b4654;
            }
            QTabBar::tab:!selected {
                margin-top: 2px;
            }
            #StatusCard {
                background: #182229;
                border: 1px solid #2b3a42;
                border-radius: 8px;
            }
            #SettingsScroll, #SettingsViewport, #SettingsContent {
                background: #101418;
                border: 0;
            }
            #StatusDot {
                background: #4ade80;
                border-radius: 7px;
            }
            #StatusLabel {
                color: #f6faf8;
                font-size: 22px;
                font-weight: 650;
            }
            #StatusDetailLabel, #HintLabel {
                color: #aab7b7;
                font-size: 13px;
            }
            QLineEdit, QPlainTextEdit, QComboBox {
                background: #0f1519;
                border: 1px solid #2d3940;
                border-radius: 7px;
                padding: 9px 10px;
                color: #f2f6f4;
                selection-background-color: #2f7d62;
            }
            QLineEdit, QComboBox {
                min-height: 22px;
            }
            QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {
                border-color: #48b586;
            }
            QComboBox::drop-down {
                border: 0;
                width: 28px;
            }
            #ErrorBox {
                color: #f3c5c5;
            }
            QScrollBar:vertical {
                background: #101418;
                width: 10px;
                margin: 2px 0 2px 0;
            }
            QScrollBar::handle:vertical {
                background: #2d3940;
                border-radius: 5px;
                min-height: 28px;
            }
            QScrollBar::handle:vertical:hover {
                background: #3c4c55;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
                border: 0;
                background: transparent;
            }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QPushButton {
                background: #4ade80;
                color: #07100b;
                font-size: 16px;
                font-weight: 700;
                border: none;
                border-radius: 8px;
                padding: 10px;
            }
            QPushButton:hover { background: #63e792; }
            QPushButton:pressed { background: #2fb96a; }
            QPushButton:disabled {
                background: #2e3a3f;
                color: #7f8d8d;
            }
            """
        )

    def set_recording(self, is_recording: bool):
        if is_recording:
            self.status_label.setText("Идет запись…")
            self.status_detail_label.setText("Говорите естественно. Нажмите кнопку или горячую клавишу, чтобы остановить.")
            self.action_button.setText("Остановить запись")
            self.status_dot.setStyleSheet("background: #fb7185; border-radius: 7px;")
        else:
            self.status_label.setText("Готов к записи")
            self.status_detail_label.setText("Нажмите кнопку или используйте горячую клавишу, чтобы начать диктовку.")
            self.action_button.setText("Начать запись")
            self.status_dot.setStyleSheet("background: #4ade80; border-radius: 7px;")

    def set_processing(self):
        self.status_label.setText("Обрабатываю текст…")
        self.status_detail_label.setText("Распознаю речь и отправляю текст на постобработку.")
        self.action_button.setText("Подождите…")
        self.action_button.setEnabled(False)
        self.status_dot.setStyleSheet("background: #fbbf24; border-radius: 7px;")

    def set_start_model_loading(self, model_name: str = "base"):
        self.status_label.setText("Загрузка модели…")
        self.status_detail_label.setText(f"Whisper {model_name} загружается в фоне. Первый запуск может занять чуть больше времени.")
        self.action_button.setText("Подождите…")
        self.action_button.setEnabled(False)
        self.status_dot.setStyleSheet("background: #60a5fa; border-radius: 7px;")

    def set_idle(self):
        self.action_button.setEnabled(True)
        self.set_recording(False)

    def set_settings(self, hotkey: str, api_key: str, gigachat_model: str, whisper_model: str, prompt: str):
        self.hotkey_input.setText(hotkey)
        self.api_key_input.setText(api_key)
        self.gigachat_model_input.setCurrentText(gigachat_model)
        self.whisper_model_input.setCurrentText(whisper_model)
        self.prompt_input.setPlainText(prompt)

    def set_settings_status(self, text: str, ok: bool):
        color = "#86efac" if ok else "#fca5a5"
        self.settings_status_label.setStyleSheet(f"color: {color};")
        self.settings_status_label.setText(text)

    def _emit_apply_settings(self):
        self.apply_settings.emit(
            self.hotkey_input.text().strip(),
            self.api_key_input.text().strip(),
            self.gigachat_model_input.currentText().strip(),
            self.whisper_model_input.currentText().strip(),
            self.prompt_input.toPlainText().strip(),
        )

    def set_error_text(self, text: str):
        self.error_box.setPlainText(text)

    def clear_error_text(self):
        self.error_box.clear()
