#!/bin/bash

# F1 News Bot - Docker запуск всей системы
echo "🚀 Запуск F1 News Bot через Docker..."

# Проверяем наличие .env файла
if [ ! -f .env ]; then
    echo "❌ Файл .env не найден!"
    echo "📝 Создайте .env файл на основе config.env.example"
    exit 1
fi

# Загружаем переменные окружения
export $(cat .env | grep -v '^#' | xargs)

# Проверяем обязательные переменные
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "❌ TELEGRAM_BOT_TOKEN не установлен в .env"
    exit 1
fi

if [ -z "$TELEGRAM_CHANNEL_ID" ]; then
    echo "❌ TELEGRAM_CHANNEL_ID не установлен в .env"
    exit 1
fi

if [ -z "$TELEGRAM_ADMIN_ID" ]; then
    echo "❌ TELEGRAM_ADMIN_ID не установлен в .env"
    exit 1
fi

echo "✅ Переменные окружения загружены"

# Создаем директорию для логов
mkdir -p logs

# Запускаем основное приложение
echo "1️⃣ Запуск основного приложения..."
docker-compose up -d

# Ждем запуска
echo "⏳ Ожидание запуска основного приложения..."
sleep 10

# Запускаем Telegram бота
echo "2️⃣ Запуск Telegram бота..."
docker-compose -f docker-compose-bot.yml up -d

echo ""
echo "✅ Система запущена!"
echo "🌐 Основное приложение: http://localhost:8000"
echo "📚 API документация: http://localhost:8000/docs"
echo "🤖 Telegram бот: Проверьте бота в Telegram"
echo ""
echo "📊 Статус контейнеров:"
docker-compose ps
echo ""
echo "📋 Логи основного приложения:"
echo "docker-compose logs -f f1-news-bot"
echo ""
echo "📋 Логи Telegram бота:"
echo "docker-compose -f docker-compose-bot.yml logs -f f1-news-bot-telegram"
echo ""
echo "🛑 Остановка системы:"
echo "docker-compose down && docker-compose -f docker-compose-bot.yml down"
