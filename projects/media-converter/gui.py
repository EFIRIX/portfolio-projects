#!/usr/bin/env python3
"""
Media Converter GUI - Liquid Glass Style
"""

import sys
import os
import subprocess
import threading
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QFileDialog, QProgressBar,
    QFrame
)
from PySide6.QtCore import Qt, QSize, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QIcon, QPixmap, QColor, QLinearGradient, QRadialGradient,
    QBrush, QFont, QFontDatabase, QPalette
)

# Поддерживаемые форматы
VIDEO_FORMATS = ['mp4', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'webm', 'm4v']
AUDIO_FORMATS = ['mp3', 'wav', 'aac', 'ogg', 'flac', 'm4a']
IMAGE_FORMATS = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp']

ALL_FORMATS = VIDEO_FORMATS + AUDIO_FORMATS + IMAGE_FORMATS

# Цвета Liquid Glass
class Colors:
    PRIMARY = QColor(0, 180, 255)  # Синий
    SECONDARY = QColor(100, 220, 255)  # Светло-синий
    ACCENT = QColor(0, 255, 200)  # Бирюзовый
    BG_DARK = QColor(15, 25, 40)  # Темно-синий фон
    BG_LIGHT = QColor(30, 45, 65)  # Светлее
    TEXT = QColor(220, 230, 240)  # Светлый текст
    TEXT_SECONDARY = QColor(150, 170, 190)  # Вторичный текст
    GLASS = QColor(255, 255, 255, 30)  # Полупрозрачный белый
    BORDER = QColor(255, 255, 255, 50)  # Граница
    SUCCESS = QColor(0, 255, 150)
    ERROR = QColor(255, 80, 100)


class LiquidButton(QPushButton):
    """Кнопка в стиле Liquid Glass"""
    
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 180, 255, 150);
                border: 1px solid rgba(255, 255, 255, 50);
                border-radius: 15px;
                color: white;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: rgba(100, 220, 255, 180);
                border-color: rgba(255, 255, 255, 80);
            }
            QPushButton:pressed {
                background-color: rgba(0, 150, 220, 200);
                border-color: rgba(255, 255, 255, 100);
            }
            QPushButton:disabled {
                background-color: rgba(0, 180, 255, 50);
                color: rgba(255, 255, 255, 80);
            }
        """)
        self.setCursor(Qt.PointingHandCursor)
        
        # Анимация свечения
        # Убираем анимацию свечения (может вызывать проблемы)
        # self.glow_animation = QPropertyAnimation(self, b"opacity")
        # self.glow_animation.setDuration(2000)
        # self.glow_animation.setKeyValueAt(0, 1.0)
        # self.glow_animation.setKeyValueAt(0.5, 0.8)
        # self.glow_animation.setKeyValueAt(1, 1.0)
        # self.glow_animation.setLoopCount(-1)
        # self.glow_animation.start()


class GlassFrame(QFrame):
    """Рамка с эффектом стекла"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            GlassFrame {
                background-color: rgba(255, 255, 255, 15);
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 20px;
            }
        """)


class LiquidProgressBar(QProgressBar):
    """Прогресс-бар в стиле Liquid Glass"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QProgressBar {
                background-color: rgba(255, 255, 255, 20);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 10px;
                text-align: center;
                color: white;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, x2:1, 
                    stop:0 rgba(0, 180, 255, 180), 
                    stop:1 rgba(0, 255, 200, 180));
                border-radius: 10px;
            }
        """)
        self.setTextVisible(False)


class FormatSelector(QComboBox):
    """Выбор формата с стилем Liquid Glass"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QComboBox {
                background-color: rgba(255, 255, 255, 20);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 10px;
                color: white;
                padding: 10px 15px;
                min-width: 150px;
            }
            QComboBox::drop-down {
                border: 0px;
                width: 0px;
                height: 0px;
            }
            QComboBox QAbstractItemView {
                background-color: rgba(30, 45, 65, 240);
                border: 1px solid rgba(0, 180, 255, 100);
                color: white;
                selection-background-color: rgba(0, 180, 255, 150);
            }
        """)


class FileDropArea(QFrame):
    """Область для перетаскивания файлов"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(200)
        self.setStyleSheet("""
            FileDropArea {
                background-color: rgba(0, 180, 255, 20);
                border: 2px dashed rgba(0, 180, 255, 100);
                border-radius: 15px;
            }
            FileDropArea:hover {
                background-color: rgba(0, 180, 255, 30);
                border-color: rgba(0, 180, 255, 150);
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        
        self.icon_label = QLabel("📁")
        self.icon_label.setStyleSheet("font-size: 48px; color: rgba(0, 180, 255, 150);")
        
        self.text_label = QLabel("Перетащите файл сюда или нажмите для выбора")
        self.text_label.setStyleSheet("color: rgba(255, 255, 255, 150); font-size: 14px;")
        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(Qt.AlignCenter)
        
        self.file_label = QLabel()
        self.file_label.setStyleSheet("color: white; font-size: 12px; margin-top: 10px;")
        self.file_label.setWordWrap(True)
        self.file_label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)
        layout.addWidget(self.file_label)
        
        self.file_path = None
        self.file_dropped = lambda path: None
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
    
    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            self.file_path = urls[0].toLocalFile()
            self.file_label.setText(os.path.basename(self.file_path))
            self.file_dropped(self.file_path)
            event.acceptProposedAction()
    
    def mousePressEvent(self, event):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите файл", "",
            "Медиа файлы (*.mp4 *.mkv *.avi *.mov *.mp3 *.wav *.jpg *.png);;Все файлы (*)"
        )
        if file_path:
            self.file_path = file_path
            self.file_label.setText(os.path.basename(file_path))
            self.file_dropped(file_path)


class ConverterApp(QMainWindow):
    """Главное окно приложения"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Media Converter")
        self.setFixedSize(500, 650)
        
        # Настраиваем прозрачность и стиль окна
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        
        # Центральный виджет
        central_widget = QWidget(self)
        central_widget.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(15, 25, 40, 240),
                    stop:1 rgba(30, 45, 65, 240));
            }
        """)
        self.setCentralWidget(central_widget)
        
        # Главный лэйаут
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)
        
        # Заголовок
        self.create_header(main_layout)
        
        # Основной контент
        self.create_content(main_layout)
        
        # Нижняя панель
        self.create_footer(main_layout)
        
        # Анимация загрузки окна
        self.fade_in()
    
    def create_header(self, layout):
        """Создаем заголовок"""
        header_frame = GlassFrame()
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(20, 15, 20, 15)
        
        # Иконка (используем Unicode символ)
        icon_label = QLabel("🎬")
        icon_label.setStyleSheet("font-size: 32px;")
        icon_label.setFixedSize(40, 40)
        
        # Название
        title_label = QLabel("Media Converter")
        title_label.setStyleSheet("""
            color: white;
            font-size: 24px;
            font-weight: 700;
        """)
        
        # Пустое пространство
        spacer = QWidget()
        spacer.setSizePolicy(QWidget.Expanding, QWidget.Expanding)
        
        # Кнопки управления окном
        close_btn = QPushButton("✕")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: rgba(255, 255, 255, 150);
                font-size: 20px;
                padding: 5px;
            }
            QPushButton:hover {
                color: white;
                background-color: rgba(255, 80, 100, 100);
                border-radius: 5px;
            }
        """)
        close_btn.setFixedSize(30, 30)
        close_btn.clicked.connect(self.close)
        
        header_layout.addWidget(icon_label)
        header_layout.addWidget(title_label)
        header_layout.addWidget(spacer)
        header_layout.addWidget(close_btn)
        
        layout.addWidget(header_frame)
    
    def create_content(self, layout):
        """Создаем основной контент"""
        # Область перетаскивания
        self.drop_area = FileDropArea()
        self.drop_area.file_dropped = self.on_file_selected
        layout.addWidget(self.drop_area)
        
        # Выбор формата
        format_frame = GlassFrame()
        format_layout = QVBoxLayout(format_frame)
        format_layout.setContentsMargins(20, 15, 20, 15)
        format_layout.setSpacing(10)
        
        format_label = QLabel("Выберите формат:")
        format_label.setStyleSheet("color: white; font-size: 14px; font-weight: 600;")
        
        self.format_selector = FormatSelector()
        self.format_selector.addItems(ALL_FORMATS)
        self.format_selector.setCurrentText("mp4")
        
        format_layout.addWidget(format_label)
        format_layout.addWidget(self.format_selector)
        layout.addWidget(format_frame)
        
        # Прогресс-бар
        self.progress_bar = LiquidProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Статус
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: rgba(255, 255, 255, 150); font-size: 12px;")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # Кнопка конвертации
        self.convert_btn = LiquidButton("Конвертировать")
        self.convert_btn.setEnabled(False)
        self.convert_btn.clicked.connect(self.start_conversion)
        layout.addWidget(self.convert_btn)
    
    def create_footer(self, layout):
        """Создаем нижнюю панель"""
        footer_frame = GlassFrame()
        footer_layout = QHBoxLayout(footer_frame)
        footer_layout.setContentsMargins(20, 10, 20, 10)
        
        info_label = QLabel("✨ Liquid Glass Design")
        info_label.setStyleSheet("color: rgba(255, 255, 255, 100); font-size: 11px;")
        
        spacer = QWidget()
        spacer.setSizePolicy(QWidget.Expanding, QWidget.Expanding)
        
        version_label = QLabel("v1.0.0")
        version_label.setStyleSheet("color: rgba(255, 255, 255, 100); font-size: 11px;")
        
        footer_layout.addWidget(info_label)
        footer_layout.addWidget(spacer)
        footer_layout.addWidget(version_label)
        
        layout.addWidget(footer_frame)
    
    def on_file_selected(self, file_path):
        """Обработка выбора файла"""
        self.file_path = file_path
        self.convert_btn.setEnabled(True)
        self.status_label.setText(f"Файл: {os.path.basename(file_path)}")
        
        # Автоматически определяем тип файла и выбираем подходящий формат
        ext = os.path.splitext(file_path)[1][1:].lower()
        if ext in VIDEO_FORMATS:
            # Для видео предлагаем mkv или mp4
            if self.format_selector.currentText() in VIDEO_FORMATS:
                pass
            else:
                self.format_selector.setCurrentText("mkv" if ext != "mkv" else "mp4")
        elif ext in AUDIO_FORMATS:
            self.format_selector.setCurrentText("mp3" if ext != "mp3" else "wav")
        elif ext in IMAGE_FORMATS:
            self.format_selector.setCurrentText("png" if ext != "png" else "jpg")
    
    def start_conversion(self):
        """Запуск конвертации"""
        if not hasattr(self, 'file_path'):
            return
        
        output_ext = self.format_selector.currentText()
        input_path = self.file_path
        output_path = os.path.splitext(input_path)[0] + "." + output_ext
        
        # Проверяем, что файл существует
        if not os.path.exists(input_path):
            self.show_error("Файл не найден!")
            return
        
        # Отключаем кнопки
        self.convert_btn.setEnabled(False)
        self.drop_area.setEnabled(False)
        self.format_selector.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("Конвертация...")
        
        # Запускаем конвертацию в отдельном потоке
        self.conversion_thread = threading.Thread(
            target=self.convert_file,
            args=(input_path, output_path),
            daemon=True
        )
        self.conversion_thread.start()
        
        # Запускаем таймер для обновления прогресса
        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self.update_progress)
        self.progress_timer.start(200)
    
    def convert_file(self, input_path, output_path):
        """Конвертация файла"""
        try:
            input_ext = os.path.splitext(input_path)[1][1:].lower()
            output_ext = os.path.splitext(output_path)[1][1:].lower()
            
            # Получаем пути к инструментам из переменных окружения
            ffmpeg_path = os.environ.get('MEDIA_CONVERTER_FFMPEG', '/opt/homebrew/bin/ffmpeg')
            convert_path = os.environ.get('MEDIA_CONVERTER_CONVERT', '/opt/homebrew/bin/convert')
            
            # Собираем команду
            if input_ext in IMAGE_FORMATS or output_ext in IMAGE_FORMATS:
                cmd = [convert_path, input_path, output_path]
            else:
                cmd = [ffmpeg_path, '-i', input_path, '-y']
                
                if output_ext in VIDEO_FORMATS:
                    cmd.extend(['-c:v', 'libx264', '-preset', 'fast', '-crf', '23'])
                elif output_ext in AUDIO_FORMATS:
                    cmd.extend(['-c:a', 'aac', '-b:a', '192k'])
                
                cmd.append(output_path)
            
            # Выполняем команду
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Чтение вывода для прогресса
            for line in process.stderr:
                if line:
                    self.conversion_output = line
            
            process.wait()
            
            if process.returncode != 0:
                self.conversion_error = True
                self.conversion_message = f"Ошибка конвертации: {process.stderr.read()}"
            else:
                self.conversion_error = False
                self.conversion_message = f"Файл успешно сконвертирован в {output_ext}!"
                
        except Exception as e:
            self.conversion_error = True
            self.conversion_message = f"Ошибка: {str(e)}"
    
    def update_progress(self):
        """Обновление прогресса"""
        if not hasattr(self, 'conversion_thread') or not self.conversion_thread.is_alive():
            self.progress_timer.stop()
            
            # Включаем кнопки обратно
            self.convert_btn.setEnabled(True)
            self.drop_area.setEnabled(True)
            self.format_selector.setEnabled(True)
            
            if hasattr(self, 'conversion_error'):
                if self.conversion_error:
                    self.show_error(self.conversion_message)
                    self.status_label.setText("Ошибка конвертации")
                else:
                    self.status_label.setText(self.conversion_message)
                    self.progress_bar.setValue(100)
                    
                    # Очищаем выбор файла
                    self.drop_area.file_path = None
                    self.drop_area.file_label.setText("")
            
            return
        
        # Увеличиваем прогресс
        current = self.progress_bar.value()
        if current < 90:
            self.progress_bar.setValue(current + 1)
    
    def show_error(self, message):
        """Показать ошибку"""
        # Анимация ошибки
        self.status_label.setStyleSheet("color: rgba(255, 80, 100, 200); font-size: 12px;")
        self.status_label.setText(message)
        
        # Возвращаем цвет через 3 секунды
        QTimer.singleShot(3000, lambda: self.status_label.setStyleSheet(
            "color: rgba(255, 255, 255, 150); font-size: 12px;"
        ))
    
    def fade_in(self):
        """Анимация появления окна"""
        self.setWindowOpacity(0)
        self.show()
        
        animation = QPropertyAnimation(self, b"windowOpacity")
        animation.setDuration(500)
        animation.setStartValue(0)
        animation.setEndValue(1)
        animation.setEasingCurve(QEasingCurve.OutBack)
        animation.start()
    
    def mousePressEvent(self, event):
        """Перетаскивание окна"""
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        """Перетаскивание окна"""
        if event.buttons() == Qt.LeftButton and hasattr(self, 'drag_position'):
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Проверяем наличие FFmpeg
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
    except:
        print("ОШИБКА: FFmpeg не найден!")
        sys.exit(1)
    
    window = ConverterApp()
    sys.exit(app.exec())
