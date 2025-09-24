#!/bin/bash

echo "🔐 Настройка Telegram авторизации для Docker..."

# Проверка наличия .env файла
if [ ! -f ".env" ]; then
    echo "❌ Файл .env не найден. Создайте его на основе .env.example"
    exit 1
fi

# Проверка переменных Telegram API
source .env
if [ -z "$TELEGRAM_API_ID" ] || [ -z "$TELEGRAM_API_HASH" ] || [ -z "$TELEGRAM_PHONE" ]; then
    echo "❌ Не настроены переменные Telegram API в .env:"
    echo "   TELEGRAM_API_ID"
    echo "   TELEGRAM_API_HASH" 
    echo "   TELEGRAM_PHONE"
    echo ""
    echo "📝 Получите их на https://my.telegram.org/apps"
    exit 1
fi

echo "✅ Переменные Telegram API настроены"

# Активация виртуального окружения
if [ -d "venv" ]; then
    echo "🔄 Активация виртуального окружения..."
    source venv/bin/activate
else
    echo "❌ Виртуальное окружение не найдено. Создайте его:"
    echo "   python3 -m venv venv"
    echo "   source venv/bin/activate"
    echo "   pip install -r requirements.txt"
    exit 1
fi

# Проверка наличия setup_telegram_api.py
if [ ! -f "setup_telegram_api.py" ]; then
    echo "❌ Файл setup_telegram_api.py не найден"
    exit 1
fi

echo "🚀 Запуск авторизации Telegram..."
echo "📱 Введите код из SMS когда появится запрос"
echo ""

# Запуск авторизации
python setup_telegram_api.py

# Проверка создания файла сессии
if [ -f "telegram_session.session" ]; then
    echo "✅ Файл сессии создан: telegram_session.session"
    
    # Проверка Docker
    if command -v docker &> /dev/null; then
        echo "🐳 Docker найден. Копирование сессии в контейнер..."
        
        # Остановка контейнеров
        echo "⏹️ Остановка Docker контейнеров..."
        docker compose down

        #пересборка образа
        docker compose build --no-cache
        
        # Запуск контейнеров
        echo "🚀 Запуск Docker контейнеров..."
        docker compose up -d
        
        # Ожидание запуска
        echo "⏳ Ожидание запуска контейнеров..."
        sleep 10
        
        # Проверка статуса
        echo "📊 Статус контейнеров:"
        docker compose ps
        
        echo ""
        echo "✅ Настройка завершена!"
        echo "📋 Проверьте логи:"
        echo "   docker compose logs f1-news-main"
        echo "   docker compose logs f1-news-telegram"
        
    else
        echo "🐳 Docker не найден. Файл сессии готов для ручного копирования."
        echo "📋 Для Docker выполните:"
        echo "   docker cp telegram_session.session container_name:/app/telegram_session.session"
    fi
    
else
    echo "❌ Файл сессии не создан. Проверьте авторизацию."
    exit 1
fi
