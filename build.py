import os
import platform
import shutil
import subprocess
import sys


def is_usable_binary(binary_path):
    try:
        subprocess.run(
            [binary_path, '-version'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=True,
        )
        return True
    except Exception:
        return False


def build():
    system = platform.system()
    sep = ';' if system == 'Windows' else ':'

    if system == 'Darwin':
        cmd = ['pyinstaller', '--noconfirm', 'STT Desktop.spec']
        subprocess.run(cmd, check=True)
        return

    icon_option = ''
    if system == 'Windows':
        icon_option = '--icon=assets/icon.ico'
    elif system == 'Darwin':  # macOS
        icon_option = '--icon=assets/icon.icns'

    cmd = [
        sys.executable,
        '-m',
        'PyInstaller',
        '--noconfirm',
        '--windowed',
        '--onedir' if system == 'Windows' else '--onefile',
        '--name', 'STT Desktop',
        '--collect-data', 'whisper',
        '--collect-binaries', '_sounddevice_data',
        '--add-data', f'assets{sep}assets',
        '--add-data', f'prompt.md{sep}.',
        icon_option,
    ]

    if system == 'Windows':
        # pynput selects its OS backend dynamically, so PyInstaller cannot
        # reliably discover it from imports alone.
        cmd.extend([
            '--hidden-import', 'pynput.keyboard._win32',
            '--hidden-import', 'pynput._util.win32',
            '--hidden-import', 'pynput._util.win32_vks',
        ])

    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path and is_usable_binary(ffmpeg_path):
        cmd.extend(['--add-binary', f'{ffmpeg_path}{sep}.'])
        print(f'Bundling ffmpeg: {ffmpeg_path}')
    else:
        print('ffmpeg not found or not usable; building without bundled ffmpeg.')

    cmd = [arg for arg in cmd if arg.strip()]
    cmd.append('app/main.py')
    subprocess.run(cmd, check=True)

if __name__ == '__main__':
    build()
