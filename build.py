import os
import platform
import subprocess


def build():
    system = platform.system()
    sep = ';' if system == 'Windows' else ':'

    cmd = [
        'pyinstaller',
        '--windowed',
        '--onefile',
        '--name', 'STT Desktop',
        '--add-data', f'assets{sep}assets',
        '--add-data', f'prompt.md{sep}.',
        # иконка
        '--icon=assets/icon.icns',  # macOS
        '--icon=assets/icon.ico',   # Windows
        'app/main.py'
    ]

    subprocess.run(cmd, check=True)

if __name__ == '__main__':
    build()