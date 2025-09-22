# 🤖 Telegram Bot Integration Guide

## 📋 Обзор архитектуры

Telegram бот работает как **отдельное приложение**, которое взаимодействует с основным F1 News Bot через **Redis** для получения обработанных новостей и модерации.

## 🔄 Схема взаимодействия

```
┌─────────────────┐    Redis     ┌─────────────────┐
│   Main App      │◄────────────►│  Telegram Bot   │
│                 │              │                 │
│ • RSS Collector │              │ • Moderation    │
│ • AI Processor  │              │ • Publishing    │
│ • News Storage  │              │ • User Commands │
└─────────────────┘              └─────────────────┘
```

## 🚀 Запуск системы

### 1. Основное приложение
```bash
cd /Users/way/Development/TG_BOT_F1
source venv/bin/activate
python start_local.py
```

### 2. Telegram бот (отдельно)
```bash
cd /Users/way/Development/TG_BOT_F1
source venv/bin/activate
python telegram_bot_standalone.py
```

### 3. Автоматический запуск обоих
```bash
cd /Users/way/Development/TG_BOT_F1
source venv/bin/activate
python run_all.py
```

## 🔧 Конфигурация

### Переменные окружения (.env)
```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHANNEL_ID=your_channel_id
TELEGRAM_ADMIN_ID=your_admin_id

# Redis (связь между приложениями)
REDIS_URL=redis://localhost:6379/0

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/f1_news
```

## 📡 Redis Integration

### Основное приложение → Telegram Bot
```python
# В content_processor.py
await redis_service.add_news_to_moderation_queue(processed_news_item)
```

### Telegram Bot ← Основное приложение
```python
# В bot.py - _redis_sync_loop()
redis_news = await redis_service.get_news_from_moderation_queue(limit=5)
for news_item in redis_news:
    if not any(item.id == news_item.id for item in self.pending_publications):
        self.pending_publications.append(news_item)
```

## 🎯 Команды бота

### Основные команды
- `/start` - Приветствие и инструкции
- `/help` - Справка по командам
- `/status` - Статус системы
- `/queue` - Показать очередь публикаций
- `/publish` - Опубликовать следующую новость

### Тестовые команды
- `/test` - Тест кнопок (для отладки)
- `/ping` - Ping-pong тест

## 🔄 Workflow модерации

### 1. Сбор новостей
```
RSS Feeds → Main App → AI Processing → Redis Queue
```

### 2. Модерация
```
Redis Queue → Telegram Bot → Admin Review → Decision
```

### 3. Публикация
```
Admin Decision → Channel Publication → Database Update
```

## 📊 Структура данных

### ProcessedNewsItem (в Redis)
```python
{
    "id": "uuid",
    "title": "News Title",
    "summary": "News Summary",
    "content": "Full Content",
    "url": "https://...",
    "source": "Source Name",
    "source_type": "RSS",
    "published_at": "2024-01-01T00:00:00Z",
    "relevance_score": 0.95,
    "keywords": ["F1", "Formula 1"],
    "processed": true,
    "published": false,
    "key_points": ["Point 1", "Point 2"],
    "sentiment": "positive",
    "importance_level": 4,
    "formatted_content": "Formatted for Telegram",
    "tags": ["F1", "News"]
}
```

## 🔧 Настройка Redis

### Ключи Redis
- `f1_news:moderation_queue` - Очередь новостей для модерации
- `f1_news:published:{news_id}` - Статус опубликованных новостей

### Операции Redis
```python
# Добавить в очередь модерации
await redis_service.add_news_to_moderation_queue(news_item)

# Получить из очереди модерации
news_items = await redis_service.get_news_from_moderation_queue(limit=5)

# Отметить как опубликованную
await redis_service.mark_news_as_published(news_id, telegram_message_id)
```

## 🐛 Отладка

### Логи
```bash
# Основное приложение
tail -f logs/f1_news_bot.log

# Telegram бот
tail -f logs/telegram_bot.log
```

### Проверка Redis
```bash
redis-cli
> LLEN f1_news:moderation_queue
> LRANGE f1_news:moderation_queue 0 -1
```

### Проверка статуса
```bash
# Проверить процессы
ps aux | grep -E "(start_local|telegram_bot)"

# Проверить порты
lsof -i :8000  # Main app
lsof -i :6379  # Redis
```

## ⚠️ Важные моменты

### 1. Порядок запуска
- Сначала Redis
- Затем основное приложение
- Потом Telegram бот

### 2. Синхронизация
- Telegram бот синхронизируется с Redis каждые 30 секунд
- Новости не дублируются в очереди

### 3. Обработка ошибок
- Все ошибки логируются
- Бот продолжает работать при ошибках Redis
- Автоматический перезапуск при критических ошибках

### 4. Безопасность
- Все данные в Redis временные
- Нет хранения чувствительных данных
- Логирование всех операций

## 🔄 Обновление системы

### Обновление основного приложения
```bash
# Остановить основное приложение
pkill -f start_local.py

# Обновить код
git pull

# Запустить заново
python start_local.py
```

### Обновление Telegram бота
```bash
# Остановить бота
pkill -f telegram_bot_standalone.py

# Обновить код
git pull

# Запустить заново
python telegram_bot_standalone.py
```

## 📈 Мониторинг

### Метрики
- Количество новостей в очереди модерации
- Время обработки новостей
- Успешность публикации
- Активность пользователей

### Алерты
- Ошибки Redis соединения
- Превышение лимита новостей в очереди
- Ошибки публикации в канал
- Недоступность AI сервиса

## 🎯 Лучшие практики

1. **Мониторинг очереди** - Регулярно проверяйте размер очереди модерации
2. **Резервное копирование** - Настройте бэкап базы данных
3. **Логирование** - Включите детальное логирование для отладки
4. **Тестирование** - Используйте тестовые команды для проверки работы
5. **Обновления** - Регулярно обновляйте зависимости

## 🆘 Устранение неполадок

### Бот не отвечает на команды
1. Проверьте, что бот запущен
2. Проверьте токен бота
3. Проверьте логи на ошибки

### Новости не появляются в боте
1. Проверьте Redis соединение
2. Проверьте, что основное приложение работает
3. Проверьте очередь модерации в Redis

### Кнопки не работают
1. Проверьте логи на ошибки callback
2. Проверьте, что CallbackQueryHandler зарегистрирован
3. Проверьте формат callback_data

### Ошибки публикации
1. Проверьте права бота в канале
2. Проверьте ID канала
3. Проверьте формат сообщений
