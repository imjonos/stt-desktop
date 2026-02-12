import os
import platform
import shutil
import subprocess


def build():
    system = platform.system()
    sep = ';' if system == 'Windows' else ':'

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
        '--add-data', f'assets{sep}assets',
        '--add-data', f'prompt.md{sep}.',
        icon_option,
        'app/main.py'
    ]

    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        cmd.extend(['--add-binary', f'{ffmpeg_path}{sep}.'])
        print(f'Bundling ffmpeg: {ffmpeg_path}')
    else:
        print('ffmpeg not found in PATH; building without bundled ffmpeg.')

    cmd = [arg for arg in cmd if arg.strip()]
    subprocess.run(cmd, check=True)

if __name__ == '__main__':
    build()
