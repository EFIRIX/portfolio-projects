#!/bin/bash

# Установочный скрипт для Media Converter

echo "=== Установка Media Converter ==="
echo ""

# Устанавливаем FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "📦 Установка FFmpeg..."
    brew install ffmpeg
    if [ $? -ne 0 ]; then
        echo "❌ Ошибка установки FFmpeg"
        exit 1
    fi
    echo "✅ FFmpeg установлен"
else
    echo "✅ FFmpeg уже установлен"
fi

echo ""

# Устанавливаем ImageMagick
if ! command -v convert &> /dev/null; then
    echo "📦 Установка ImageMagick..."
    brew install imagemagick
    if [ $? -ne 0 ]; then
        echo "⚠️  ImageMagick не установлен (опционально для изображений)"
    else
        echo "✅ ImageMagick установлен"
    fi
else
    echo "✅ ImageMagick уже установлен"
fi

echo ""

# Устанавливаем Python зависимости
if [ -f "requirements.txt" ]; then
    echo "📦 Установка Python зависимостей..."
    pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "❌ Ошибка установки зависимостей"
        exit 1
    fi
    echo "✅ Зависимости установлены"
else
    echo "⚠️  requirements.txt не найден"
fi

echo ""
echo "=== Установка завершена! ==="
echo ""
echo "Запуск: python main.py [папка]"
echo "Пример: python main.py ~/Downloads"
