import os
import platform
import shutil
import subprocess


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
        'pyinstaller',
        '--windowed',
        '--onefile',
        '--name', 'STT Desktop',
        '--collect-data', 'whisper',
        '--add-data', f'assets{sep}assets',
        '--add-data', f'prompt.md{sep}.',
        icon_option,
        'app/main.py'
    ]

    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path and is_usable_binary(ffmpeg_path):
        cmd.extend(['--add-binary', f'{ffmpeg_path}{sep}.'])
        print(f'Bundling ffmpeg: {ffmpeg_path}')
    else:
        print('ffmpeg not found or not usable; building without bundled ffmpeg.')

    cmd = [arg for arg in cmd if arg.strip()]
    subprocess.run(cmd, check=True)

if __name__ == '__main__':
    build()
