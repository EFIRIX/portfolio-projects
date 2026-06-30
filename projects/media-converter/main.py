#!/usr/bin/env python3
"""
Media Converter - Автоматическая конвертация медиафайлов при изменении расширения
Использование: python main.py [папка_для_мониторинга]
Пример: python main.py ~/Downloads
"""

import os
import sys
import subprocess
import threading
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import tkinter as tk
from tkinter import messagebox

# Поддерживаемые форматы
VIDEO_FORMATS = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v']
AUDIO_FORMATS = ['.mp3', '.wav', '.aac', '.ogg', '.flac', '.m4a']
IMAGE_FORMATS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']

SUPPORTED_EXTENSIONS = VIDEO_FORMATS + AUDIO_FORMATS + IMAGE_FORMATS


class ConversionDialog:
    """Diалоговое окно для подтверждения конвертации"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()  # Скрываем главное окно
        self.result = None
    
    def ask_convert(self, old_path, new_path):
        """Показать диалог подтверждения"""
        self.result = None
        old_ext = os.path.splitext(old_path)[1].lower()
        new_ext = os.path.splitext(new_path)[1].lower()
        
        response = messagebox.askyesno(
            "Конвертация медиафайла",
            f"Вы изменили расширение файла:\n\n{os.path.basename(old_path)} → {os.path.basename(new_path)}\n\n"
            f"Хотите сконвертировать файл из {old_ext} в {new_ext}?"
        )
        
        if response:
            self.result = True
        else:
            self.result = False
        
        return self.result
    
    def show_error(self, message):
        """Показать ошибку"""
        messagebox.showerror("Ошибка", message)
    
    def show_success(self, message):
        """Показать успех"""
        messagebox.showinfo("Успех", message)


class MediaConverterHandler(FileSystemEventHandler):
    """Обработчик событий файловой системы"""
    
    def __init__(self, watch_dir, dialog):
        self.watch_dir = Path(watch_dir)
        self.dialog = dialog
        self.file_history = {}  # историиrename: {new_path: old_path}
        self.lock = threading.Lock()
    
    def on_renamed(self, event):
        """Обработка переименования файла"""
        if not event.is_directory:
            old_path = Path(event.src_path)
            new_path = Path(event.dest_path)
            
            # Проверяем что файл в наблюдаемой директории
            if not new_path.parent.samefile(self.watch_dir):
                return
            
            # Получаем расширения
            old_ext = old_path.suffix.lower()
            new_ext = new_path.suffix.lower()
            
            # Проверяем что оба расширения поддерживаются
            if old_ext in SUPPORTED_EXTENSIONS and new_ext in SUPPORTED_EXTENSIONS and old_ext != new_ext:
                # Сохраняем историю для обработки в основном потоке
                with self.lock:
                    self.file_history[str(new_path)] = str(old_path)
    
    def check_and_convert(self):
        """Проверка и конвертация файлов (вызывается в основном потоке)"""
        with self.lock:
            if not self.file_history:
                return
            
            items = list(self.file_history.items())
            self.file_history.clear()
        
        for new_path, old_path in items:
            self.process_conversion(old_path, new_path)
    
    def process_conversion(self, old_path, new_path):
        """Обработка конвертации файла"""
        # Проверяем что файл существует
        if not os.path.exists(old_path):
            return
        
        # Спрашиваем пользователя
        if not self.dialog.ask_convert(old_path, new_path):
            # Если отмена - переименовываем обратно
            try:
                os.rename(new_path, old_path)
            except Exception as e:
                self.dialog.show_error(f"Не удалось переименовать обратно: {e}")
            return
        
        # Конвертируем
        try:
            self.convert_file(old_path, new_path)
            self.dialog.show_success(f"Файл успешно сконвертирован:\n{os.path.basename(new_path)}")
        except Exception as e:
            self.dialog.show_error(f"Ошибка конвертации:\n{str(e)}")
            # Возвращаем исходное имя
            try:
                os.rename(new_path, old_path)
            except:
                pass
    
    def convert_file(self, input_path, output_path):
        """Конвертация файла с помощью FFmpeg"""
        # Удаляем файл назначения если существует
        if os.path.exists(output_path):
            os.remove(output_path)
        
        # Определяем тип файла
        input_ext = Path(input_path).suffix.lower()
        output_ext = Path(output_path).suffix.lower()
        
        # Собираем команду FFmpeg
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-y',  # Перезаписать без вопроса
        ]
        
        # Для изображений используем ImageMagick
        if input_ext in IMAGE_FORMATS or output_ext in IMAGE_FORMATS:
            cmd = [
                'convert',
                input_path,
                output_path
            ]
        else:
            # Для видео и аудио
            if output_ext in VIDEO_FORMATS:
                cmd.extend(['-c:v', 'libx264', '-preset', 'fast', '-crf', '23'])
            elif output_ext in AUDIO_FORMATS:
                cmd.extend(['-c:a', 'aac', '-b:a', '192k'])
            
            cmd.append(output_path)
        
        # Выполняем команду
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 минут на конвертацию
        )
        
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout
            raise Exception(f"FFmpeg ошибка: {error_msg}")
        
        # Удаляем исходный файл после успешной конвертации
        os.remove(input_path)


def check_ffmpeg():
    """Проверка наличия FFmpeg"""
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=10)
        return True
    except:
        return False


def check_imagemagick():
    """Проверка наличия ImageMagick"""
    try:
        subprocess.run(['convert', '-version'], capture_output=True, timeout=10)
        return True
    except:
        return False


def main():
    """Главная функция"""
    # Проверяем зависимости
    if not check_ffmpeg():
        print("ОШИБКА: FFmpeg не найден!")
        print("Установите FFmpeg: brew install ffmpeg")
        sys.exit(1)
    
    print("FFmpeg найден ✓")
    
    if not check_imagemagick():
        print("ВНИМАНИЕ: ImageMagick не найден. Конвертация изображений отключена.")
        print("Установите: brew install imagemagick")
    else:
        print("ImageMagick найден ✓")
    
    # Определяем папку для мониторинга
    watch_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/Downloads")
    watch_dir = os.path.abspath(watch_dir)
    
    if not os.path.isdir(watch_dir):
        print(f"ОШИБКА: Папка не существует: {watch_dir}")
        sys.exit(1)
    
    print(f"Мониторинг папки: {watch_dir}")
    print("Поддерживаемые форматы:")
    print(f"  Видео: {', '.join(VIDEO_FORMATS)}")
    print(f"  Аудио: {', '.join(AUDIO_FORMATS)}")
    print(f"  Изображения: {', '.join(IMAGE_FORMATS)}")
    print("\nНажмите Ctrl+C для остановки...")
    
    # Создаем диалог (в основном потоке tkinter)
    dialog = ConversionDialog()
    
    # Создаем обработчик
    handler = MediaConverterHandler(watch_dir, dialog)
    
    # Настраиваем наблюдатель
    observer = Observer()
    observer.schedule(handler, watch_dir, recursive=True)
    observer.start()
    
    try:
        while True:
            # Проверяем события каждую секунду
            time.sleep(1)
            
            # Обрабатываем конвертации в основном потоке
            handler.check_and_convert()
            
    except KeyboardInterrupt:
        print("\nОстановка...")
    finally:
        observer.stop()
        observer.join()
        print("Готово!")


if __name__ == "__main__":
    main()
