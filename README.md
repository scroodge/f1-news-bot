# F1 News Bot 🏎️

Автоматический сервис для сбора, обработки и публикации новостей Formula 1 в Telegram канал.

## Возможности

- 🔍 **Сбор новостей** из множества источников (RSS, Telegram, Reddit, Twitter)
- 🤖 **AI обработка** с помощью Ollama для анализа и форматирования контента
- 🛡️ **Модерация** и фильтрация контента по релевантности и качеству
- 📅 **Планировщик публикаций** с учетом оптимального времени для F1 аудитории
- 📱 **Telegram Bot** для управления и публикации
- 🔄 **n8n интеграция** для автоматизации workflow
- 📊 **Мониторинг** системы и статистика

## Архитектура

```
[Источники] → [Сборщик] → [Ollama AI] → [Модерация] → [n8n] → [Telegram Bot] → [Канал]
     ↓              ↓           ↓            ↓         ↓
[Web RSS]    [Telegram API] [Обработка]  [Проверка] [Workflow] [Автопостинг]
[Reddit]     [Twitter API]  [Фильтрация] [Форматирование]
[News sites]
```

## Установка

### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd TG_BOT_F1
```

### 2. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 3. Настройка окружения

Скопируйте файл конфигурации и заполните необходимые параметры:

```bash
cp config.env.example .env
```

Отредактируйте `.env` файл:

```env
# Telegram Configuration
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_PHONE=your_phone_number
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHANNEL_ID=your_channel_id

# Database Configuration
DATABASE_URL=postgresql://user:password@localhost:5432/f1_news
REDIS_URL=redis://localhost:6379/0

# Ollama Configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama2

# External APIs (опционально)
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
TWITTER_BEARER_TOKEN=your_twitter_bearer_token
```

### 4. Настройка базы данных

```bash
# PostgreSQL
createdb f1_news

# Redis
redis-server
```

### 5. Настройка Ollama

```bash
# Установка Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Запуск Ollama
ollama serve

# Установка модели
ollama pull llama2
```

## Запуск

### 1. Запуск основного приложения

```bash
python run.py
```

API будет доступен по адресу: http://localhost:8000

### 2. Запуск Telegram Bot

```bash
python -m src.telegram.bot
```

### 3. Настройка n8n

1. Установите n8n:
```bash
npm install -g n8n
```

2. Запустите n8n:
```bash
n8n start
```

3. Импортируйте workflow из файла `n8n_workflows/f1_news_workflow.json`

## API Endpoints

- `GET /` - Главная страница
- `GET /health` - Проверка состояния системы
- `POST /api/collect-news` - Запуск сбора новостей
- `POST /api/process-news` - Запуск обработки новостей
- `POST /api/moderate-news` - Запуск модерации
- `POST /api/schedule-publication` - Запуск планирования публикаций
- `GET /api/stats` - Статистика системы

## Конфигурация

### Источники новостей

По умолчанию настроены следующие источники:

- **RSS**: Formula 1 Official, Motorsport.com, Autosport
- **Telegram**: @formula1, @f1_official, @motorsport
- **Reddit**: r/formula1, r/F1Technical, r/motorsports

### Настройка модерации

Система автоматически фильтрует контент по:

- Релевантности F1 тематике
- Качеству контента
- Отсутствию спама
- Длине и форматированию

### Планировщик публикаций

- Максимум 5 постов в час
- Приоритизация по важности
- Оптимальное время для F1 аудитории

## Мониторинг

### Логи

Логи сохраняются в:
- `logs/f1_news_bot.log` - основные логи
- `logs/error_f1_news_bot.log` - ошибки

### Статистика

Доступна через API endpoint `/api/stats`:

```json
{
  "database_stats": {
    "total_news_collected": 150,
    "total_news_processed": 120,
    "total_news_published": 80
  },
  "processing_stats": {
    "processing_rate": 0.8,
    "pending_processing": 30
  },
  "queue_status": {
    "queue_length": 5,
    "can_publish_now": true
  }
}
```

## Разработка

### Структура проекта

```
src/
├── ai/                 # AI обработка (Ollama)
├── collectors/         # Сборщики новостей
├── moderator/          # Модерация и планирование
├── telegram/           # Telegram Bot
├── utils/              # Утилиты (логирование, мониторинг)
├── config.py           # Конфигурация
├── database.py         # База данных
├── models.py           # Модели данных
└── main.py             # Основное приложение
```

### Добавление новых источников

1. Создайте новый класс в `src/collectors/`
2. Наследуйтесь от `BaseCollector`
3. Реализуйте метод `collect_news()`
4. Добавьте в `NewsCollector`

### Кастомизация AI обработки

Отредактируйте промпты в `src/ai/ollama_client.py` для изменения логики обработки.

## Troubleshooting

### Частые проблемы

1. **Ollama не отвечает**
   - Проверьте, что Ollama запущен: `ollama list`
   - Убедитесь, что модель установлена: `ollama pull llama2`

2. **Ошибки Telegram API**
   - Проверьте правильность токенов в `.env`
   - Убедитесь, что бот добавлен в канал

3. **Проблемы с базой данных**
   - Проверьте подключение к PostgreSQL
   - Убедитесь, что Redis запущен

### Логи

Все ошибки записываются в логи. Проверьте файлы в папке `logs/` для диагностики проблем.

## Лицензия

MIT License

## Поддержка

Для вопросов и предложений создавайте issues в репозитории.
