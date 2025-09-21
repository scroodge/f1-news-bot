#!/bin/bash

# F1 News Bot - Локальный запуск
# Использует локальные PostgreSQL, Redis, Ollama и n8n

echo "🏎️ Запуск F1 News Bot с локальными сервисами..."

# Проверка локальных сервисов
echo "🔍 Проверка локальных сервисов..."

# Проверка PostgreSQL
if ! pg_isready -h localhost -p 5432 -U f1_user -d f1_news > /dev/null 2>&1; then
    echo "❌ PostgreSQL не доступен. Убедитесь, что он запущен и настроен."
    echo "   Запуск: sudo systemctl start postgresql"
    exit 1
fi
echo "✅ PostgreSQL доступен"

# Проверка Redis
if ! redis-cli ping > /dev/null 2>&1; then
    echo "❌ Redis не доступен. Убедитесь, что он запущен."
    echo "   Запуск: sudo systemctl start redis-server"
    exit 1
fi
echo "✅ Redis доступен"

# Проверка Ollama
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "❌ Ollama не доступен. Убедитесь, что он запущен."
    echo "   Запуск: ollama serve"
    exit 1
fi
echo "✅ Ollama доступен"

# Проверка n8n
if ! curl -s http://localhost:5678 > /dev/null 2>&1; then
    echo "❌ n8n не доступен. Убедитесь, что он запущен."
    echo "   Запуск: n8n start"
    exit 1
fi
echo "✅ n8n доступен"

# Создание виртуального окружения если не существует
if [ ! -d "venv" ]; then
    echo "📦 Создание виртуального окружения..."
    python3 -m venv venv
fi

# Активация виртуального окружения
echo "🔧 Активация виртуального окружения..."
source venv/bin/activate

# Установка зависимостей
echo "📥 Установка зависимостей..."
pip install -r requirements.txt

# Создание папки для логов
mkdir -p logs

# Проверка .env файла
if [ ! -f ".env" ]; then
    echo "⚙️ Создание .env файла..."
    cp config.env.example .env
    echo "📝 Пожалуйста, отредактируйте .env файл с вашими настройками"
    echo "   nano .env"
    exit 1
fi

# Запуск приложения
echo "🚀 Запуск F1 News Bot..."
echo "   API будет доступен: http://localhost:8000"
echo "   Документация: http://localhost:8000/docs"
echo "   Для остановки нажмите Ctrl+C"

python run.py
