# 🐳 Docker Production Guide

Руководство по развертыванию F1 News Bot в продакшене с использованием Docker.

## 🚀 Быстрый запуск в продакшене

### 1. Подготовка сервера

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Docker и Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Перезагрузка для применения изменений
sudo reboot
```

### 2. Клонирование и настройка

```bash
# Клонирование репозитория
git clone https://github.com/YOUR_USERNAME/f1-news-bot.git
cd f1-news-bot

# Создание .env файла
cp .env.example .env
nano .env  # Настройте с вашими данными
```

### 3. Настройка .env для продакшена

```env
# База данных (внешняя PostgreSQL)
DATABASE_URL=postgresql://f1_user:your_password@your_db_host:5432/f1_news
REDIS_URL=redis://your_redis_host:6379/0

# Ollama (внешний)
OLLAMA_BASE_URL=http://your_ollama_host:11434
OLLAMA_MODEL=llama3:latest

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHANNEL_ID=your_channel_id
TELEGRAM_ADMIN_ID=your_admin_id

# Telegram API (для сбора новостей)
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_PHONE=your_phone_number

# RSS фиды
RSS_FEEDS=https://www.formula1.com/en/latest/all.rss,https://www.motorsport.com/f1/rss/

# Telegram каналы
TELEGRAM_CHANNELS=@formula1,@f1_official,@motorsport

# Настройки
MIN_RELEVANCE_SCORE=0.1
TIMEZONE=Europe/Moscow
```

### 4. Запуск системы

```bash
# Запуск всех сервисов
docker compose up -d

# Проверка статуса
docker compose ps

# Просмотр логов
docker compose logs -f
```

## 📊 Мониторинг в продакшене

### Проверка логов

```bash
# Все логи
docker compose logs -f

# Логи основного приложения
docker compose logs -f f1-news-main

# Логи Telegram бота
docker compose logs -f f1-news-telegram

# Только ошибки
docker compose logs 2>&1 | grep -E "(ERROR|Exception|Error)"

# Быстрая обработка русских новостей
docker compose logs f1-news-main 2>&1 | grep "Fast processing Russian news"

# Статистика обработки
docker compose logs f1-news-main 2>&1 | grep "Processing completed.*successful"
```

### Проверка производительности

```bash
# Количество быстро обработанных новостей
docker compose logs f1-news-main 2>&1 | grep "Fast processing Russian news" | wc -l

# Последние 10 успешных обработок
docker compose logs f1-news-main 2>&1 | grep "Processing completed.*successful" | tail -10

# Статистика за последний час
docker compose logs f1-news-main --since 1h 2>&1 | grep "Processing completed"
```

### Проверка здоровья системы

```bash
# Статус контейнеров
docker compose ps

# Использование ресурсов
docker stats

# Проверка API
curl http://localhost:8000/health

# Проверка статистики
curl http://localhost:8000/api/stats
```

## 🔧 Управление сервисами

### Перезапуск сервисов

```bash
# Перезапуск всех сервисов
docker compose restart

# Перезапуск конкретного сервиса
docker compose restart f1-news-main
docker compose restart f1-news-telegram

# Полная перезагрузка
docker compose down
docker compose up -d
```

### Обновление системы

```bash
# Остановка сервисов
docker compose down

# Обновление кода
git pull origin main

# Перезапуск с новым кодом
docker compose up -d --build
```

### Очистка системы

```bash
# Остановка и удаление контейнеров
docker compose down

# Удаление неиспользуемых образов
docker image prune -f

# Полная очистка (ОСТОРОЖНО!)
docker system prune -a
```

## 📈 Мониторинг производительности

### Создание скрипта мониторинга

```bash
# Создание скрипта мониторинга
cat > monitor.sh << 'EOF'
#!/bin/bash

echo "=== F1 News Bot Status ==="
echo "Time: $(date)"
echo

echo "=== Container Status ==="
docker compose ps

echo
echo "=== Resource Usage ==="
docker stats --no-stream

echo
echo "=== Recent Processing ==="
docker compose logs f1-news-main --tail 20 2>&1 | grep -E "(Processing completed|Fast processing|ERROR)"

echo
echo "=== API Health ==="
curl -s http://localhost:8000/health | jq . || echo "API not responding"

echo
echo "=== Statistics ==="
curl -s http://localhost:8000/api/stats | jq . || echo "Stats not available"
EOF

chmod +x monitor.sh
```

### Автоматический мониторинг

```bash
# Добавление в crontab для мониторинга каждые 5 минут
crontab -e

# Добавьте строку:
*/5 * * * * /path/to/f1-news-bot/monitor.sh >> /var/log/f1-news-monitor.log 2>&1
```

## 🛠️ Устранение неполадок

### Проблемы с производительностью

```bash
# Проверка использования ресурсов
docker stats

# Проверка логов на ошибки
docker compose logs f1-news-main 2>&1 | grep -E "(ERROR|Exception|Error)" | tail -20

# Проверка подключений к внешним сервисам
docker compose exec f1-news-main curl -s http://your_ollama_host:11434/api/tags
docker compose exec f1-news-main curl -s http://your_redis_host:6379/ping
```

### Проблемы с базой данных

```bash
# Проверка подключения к БД
docker compose exec f1-news-main python -c "
import asyncio
from src.database import db_manager

async def check():
    try:
        stats = await db_manager.get_stats()
        print(f'DB OK: {stats.total_news_collected} news collected')
    except Exception as e:
        print(f'DB Error: {e}')

asyncio.run(check())
"
```

### Проблемы с Telegram

```bash
# Проверка логов Telegram бота
docker compose logs f1-news-telegram 2>&1 | grep -E "(ERROR|Exception|Error)" | tail -10

# Проверка подключения к Telegram API
docker compose exec f1-news-telegram python -c "
import asyncio
from telegram import Bot

async def check():
    try:
        bot = Bot('YOUR_BOT_TOKEN')
        me = await bot.get_me()
        print(f'Bot OK: {me.username}')
    except Exception as e:
        print(f'Bot Error: {e}')

asyncio.run(check())
"
```

## 🔄 Автоматическое обновление

### Скрипт автоматического обновления

```bash
# Создание скрипта обновления
cat > update.sh << 'EOF'
#!/bin/bash

echo "Starting F1 News Bot update..."

# Переход в директорию проекта
cd /path/to/f1-news-bot

# Остановка сервисов
echo "Stopping services..."
docker compose down

# Обновление кода
echo "Updating code..."
git pull origin main

# Перезапуск сервисов
echo "Starting services..."
docker compose up -d

# Проверка статуса
echo "Checking status..."
sleep 30
docker compose ps

echo "Update completed!"
EOF

chmod +x update.sh
```

### Настройка автоматического обновления

```bash
# Добавление в crontab для обновления каждую ночь в 3:00
crontab -e

# Добавьте строку:
0 3 * * * /path/to/f1-news-bot/update.sh >> /var/log/f1-news-update.log 2>&1
```

## 📋 Резервное копирование

### Скрипт резервного копирования

```bash
# Создание скрипта бэкапа
cat > backup.sh << 'EOF'
#!/bin/bash

BACKUP_DIR="/var/backups/f1-news-bot"
DATE=$(date +%Y%m%d_%H%M%S)

echo "Starting backup..."

# Создание директории для бэкапа
mkdir -p $BACKUP_DIR

# Бэкап базы данных
docker compose exec -T postgres pg_dump -U f1_user f1_news > $BACKUP_DIR/db_backup_$DATE.sql

# Бэкап конфигурации
cp .env $BACKUP_DIR/env_backup_$DATE

# Бэкап логов
tar -czf $BACKUP_DIR/logs_backup_$DATE.tar.gz logs/

# Удаление старых бэкапов (старше 7 дней)
find $BACKUP_DIR -name "*.sql" -mtime +7 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete

echo "Backup completed: $BACKUP_DIR"
EOF

chmod +x backup.sh
```

## 🎯 Рекомендации по продакшену

### 1. Мониторинг
- Настройте мониторинг логов
- Используйте внешние сервисы мониторинга (Prometheus, Grafana)
- Настройте алерты при ошибках

### 2. Безопасность
- Используйте сильные пароли для БД
- Ограничьте доступ к серверу
- Регулярно обновляйте систему

### 3. Производительность
- Мониторьте использование ресурсов
- Настройте автоматическое масштабирование
- Используйте SSD для базы данных

### 4. Резервное копирование
- Настройте автоматические бэкапы
- Тестируйте восстановление из бэкапов
- Храните бэкапы в безопасном месте

---

**Создано с ❤️ для F1 фанатов**
