# 🚀 Быстрый запуск F1 News Bot

## 1. Клонирование репозитория

```bash
git clone https://github.com/YOUR_USERNAME/f1-news-bot.git
cd f1-news-bot
```

## 2. Настройка окружения

```bash
# Скопировать конфигурацию
cp config.env.example .env

# Отредактировать .env файл
nano .env  # или любой другой редактор
```

### Обязательные настройки в .env:

```env
# Telegram (получить на https://my.telegram.org)
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_PHONE=your_phone_number
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHANNEL_ID=your_channel_id

# База данных
DATABASE_URL=postgresql://f1_user:f1_password@localhost:5432/f1_news
REDIS_URL=redis://localhost:6379/0

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama2
```

## 3. Запуск с Docker (рекомендуется)

```bash
# Запустить все сервисы
docker-compose up -d

# Посмотреть логи
docker-compose logs -f

# Остановить
docker-compose down
```

## 4. Запуск локально

### Установка зависимостей:

```bash
pip install -r requirements.txt
```

### Установка Ollama:

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.ai/install.sh | sh

# Запуск
ollama serve

# Установка модели
ollama pull llama2
```

### Установка PostgreSQL и Redis:

```bash
# macOS
brew install postgresql redis

# Ubuntu/Debian
sudo apt-get install postgresql redis-server

# Создание базы данных
createdb f1_news
```

### Запуск приложения:

```bash
python run.py
```

## 5. Настройка n8n

1. Откройте http://localhost:5678
2. Логин: admin / admin123
3. Импортируйте workflow из `n8n_workflows/f1_news_workflow.json`

## 6. Проверка работы

### API Endpoints:
- http://localhost:8000 - главная страница
- http://localhost:8000/health - статус системы
- http://localhost:8000/docs - документация API

### Telegram Bot:
- Найдите вашего бота в Telegram
- Отправьте `/start` для начала работы
- Используйте `/help` для списка команд

## 7. Мониторинг

### Логи:
```bash
# Docker
docker-compose logs -f f1-news-bot

# Локально
tail -f logs/f1_news_bot.log
```

### Статистика:
```bash
curl http://localhost:8000/api/stats
```

## 8. Первая публикация

1. Дождитесь сбора новостей (15 минут)
2. Проверьте очередь: `/queue` в Telegram
3. Опубликуйте: `/publish` в Telegram
4. Одобрите или отклоните контент

## 9. Настройка источников

Отредактируйте `src/config.py` для добавления новых источников:

```python
# RSS ленты
rss_feeds = [
    "https://www.formula1.com/en/latest/all.xml",
    "https://www.motorsport.com/f1/rss/",
    "https://www.autosport.com/rss/",
    # Добавьте свои источники
]

# Telegram каналы
telegram_channels = [
    '@formula1',
    '@f1_official',
    # Добавьте свои каналы
]
```

## 10. Troubleshooting

### Проблемы с Ollama:
```bash
# Проверить статус
ollama list

# Перезапустить
ollama serve
```

### Проблемы с базой данных:
```bash
# Проверить подключение
psql -d f1_news -c "SELECT 1;"

# Пересоздать таблицы
python -c "from src.database import db_manager; import asyncio; asyncio.run(db_manager.create_tables())"
```

### Проблемы с Telegram:
- Проверьте токены в .env
- Убедитесь, что бот добавлен в канал
- Проверьте права бота на публикацию

## 11. Полезные команды

```bash
# Очистить логи
rm -rf logs/*

# Перезапустить сервисы
docker-compose restart

# Обновить зависимости
pip install -r requirements.txt --upgrade

# Проверить статус всех сервисов
docker-compose ps
```

## 12. Следующие шаги

1. Настройте мониторинг (Prometheus, Grafana)
2. Добавьте новые источники новостей
3. Настройте уведомления (Slack, Discord)
4. Добавьте аналитику (Google Analytics)
5. Настройте резервное копирование

---

**Нужна помощь?** Создайте issue в репозитории или обратитесь к документации в README.md
