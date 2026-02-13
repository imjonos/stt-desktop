import multiprocessing
import sys

from PySide6 import QtGui, QtWidgets

from app.app_controller import AppController
from app.constants import APP_NAME, DEFAULT_HOTKEY
from app.logging_utils import LOGGER, configure_error_logging
from app.main_window import MainWindow
from app.runtime_utils import configure_bundled_ffmpeg, load_config, resolve_app_icon_path


def main():
    configure_error_logging()
    configure_bundled_ffmpeg()

    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    icon_path = resolve_app_icon_path()
    app_icon = QtGui.QIcon(str(icon_path)) if icon_path else app.style().standardIcon(QtWidgets.QStyle.SP_ComputerIcon)
    app.setWindowIcon(app_icon)
    app.setApplicationDisplayName(APP_NAME)

    window = MainWindow()
    window.setWindowIcon(app_icon)

    try:
        config = load_config()
    except Exception as e:
        LOGGER.exception("Configuration load failed")
        QtWidgets.QMessageBox.critical(window, APP_NAME, str(e))
        return

    controller = AppController(config, window)
    default_prompt = "Сделай текст красивым и грамотным."
    if config.prompt_path.exists():
        default_prompt = config.prompt_path.read_text(encoding="utf-8").strip() or default_prompt
    window.set_settings(config.hotkey or DEFAULT_HOTKEY, config.gigachat_key, default_prompt)

    tray = QtWidgets.QSystemTrayIcon(app_icon, window)
    menu = QtWidgets.QMenu()
    show_action = menu.addAction("Открыть")
    show_action.triggered.connect(window.show)
    toggle_action = menu.addAction("Старт/Стоп запись")
    toggle_action.triggered.connect(controller.toggle_recording)
    quit_action = menu.addAction("Выход")
    quit_action.triggered.connect(app.quit)
    tray.setContextMenu(menu)
    tray.setToolTip(APP_NAME)
    tray.show()
    window.show()
    controller.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
