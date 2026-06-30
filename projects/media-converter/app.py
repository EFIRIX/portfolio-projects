#!/usr/bin/env python3
"""
Media Converter - Main Entry Point
Запускает GUI приложение в стиле Liquid Glass
"""

import sys
import os
import subprocess

def get_ffmpeg_path():
    """Получаем путь к ffmpeg"""
    # Проверяем внутри bundle
    if getattr(sys, 'frozen', False):
        # Running in PyInstaller bundle
        bundle_path = sys._MEIPASS
        ffmpeg_path = os.path.join(bundle_path, 'ffmpeg')
        if os.path.exists(ffmpeg_path):
            return ffmpeg_path
    
    # Проверяем стандартные пути
    for path in [
        '/opt/homebrew/bin/ffmpeg',
        '/usr/local/bin/ffmpeg',
        'ffmpeg'
    ]:
        if os.path.exists(path) or subprocess.run(['which', path], capture_output=True).returncode == 0:
            return path
    return 'ffmpeg'

def get_convert_path():
    """Получаем путь к convert (ImageMagick)"""
    if getattr(sys, 'frozen', False):
        bundle_path = sys._MEIPASS
        convert_path = os.path.join(bundle_path, 'convert')
        if os.path.exists(convert_path):
            return convert_path
    
    for path in [
        '/opt/homebrew/bin/convert',
        '/usr/local/bin/convert',
        'convert'
    ]:
        if os.path.exists(path) or subprocess.run(['which', path], capture_output=True).returncode == 0:
            return path
    return 'convert'

# Сохраняем пути в переменные окружения для gui.py
os.environ['MEDIA_CONVERTER_FFMPEG'] = get_ffmpeg_path()
os.environ['MEDIA_CONVERTER_CONVERT'] = get_convert_path()

# Проверяем наличие FFmpeg
try:
    subprocess.run([get_ffmpeg_path(), '-version'], capture_output=True, timeout=5)
except:
    print("ОШИБКА: FFmpeg не найден!")
    print("Установите FFmpeg: brew install ffmpeg")
    sys.exit(1)

# Проверяем наличие ImageMagick
try:
    subprocess.run([get_convert_path(), '-version'], capture_output=True, timeout=5)
except:
    print("ВНИМАНИЕ: ImageMagick не найден. Конвертация изображений отключена.")
    print("Установите: brew install imagemagick")

# Импортируем и запускаем GUI
from gui import ConverterApp
from PySide6.QtWidgets import QApplication

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ConverterApp()
    sys.exit(app.exec())
