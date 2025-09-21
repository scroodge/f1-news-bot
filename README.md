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

## 🚀 Быстрый запуск

### Способ 1: Docker (рекомендуется)

```bash
# Клонирование репозитория
git clone https://github.com/YOUR_USERNAME/f1-news-bot.git
cd f1-news-bot

# Настройка окружения
cp config.env.example .env
# Отредактируйте .env файл с вашими данными

# Запуск всех сервисов
docker-compose up -d

# Проверка статуса
docker-compose ps

# Просмотр логов
docker-compose logs -f f1-news-bot
```

**Сервисы будут доступны:**
- API: http://localhost:8000
- n8n: http://localhost:5678 (admin/admin123)
- Ollama: http://localhost:11434

### Способ 2: Локальная установка

#### 1. Клонирование и настройка

```bash
git clone https://github.com/YOUR_USERNAME/f1-news-bot.git
cd f1-news-bot

# Создание виртуального окружения
python -m venv venv
source venv/bin/activate  # macOS/Linux
# или venv\Scripts\activate  # Windows

# Установка зависимостей
pip install -r requirements.txt
```

#### 2. Настройка окружения

```bash
cp config.env.example .env
```

**Обязательные настройки в .env:**

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

# Внешние API (опционально)
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
TWITTER_BEARER_TOKEN=your_twitter_bearer_token
```

#### 3. Установка зависимых сервисов

**PostgreSQL и Redis:**
```bash
# macOS
brew install postgresql redis

# Ubuntu/Debian
sudo apt-get install postgresql redis-server

# Создание базы данных
createdb f1_news
```

**Ollama:**
```bash
# Установка
curl -fsSL https://ollama.ai/install.sh | sh

# Запуск
ollama serve

# Установка модели
ollama pull llama2
```

**n8n:**
```bash
npm install -g n8n
n8n start
```

#### 4. Запуск приложения

```bash
# Запуск API сервера
python run.py

# В другом терминале - запуск Telegram Bot
python -m src.telegram.bot
```

## 🔧 Первая настройка

### 1. Настройка Telegram

#### Создание бота:
1. Откройте [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте `/newbot`
3. Введите имя бота (например: "F1 News Bot")
4. Введите username бота (например: "f1_news_bot")
5. Сохраните полученный токен

#### Получение API данных:
1. Перейдите на [my.telegram.org](https://my.telegram.org)
2. Войдите с вашим номером телефона
3. Перейдите в "API development tools"
4. Создайте новое приложение:
   - App title: "F1 News Bot"
   - Short name: "f1_news_bot"
   - Platform: "Desktop"
5. Сохраните `api_id` и `api_hash`

#### Настройка канала:
1. Создайте канал в Telegram
2. Добавьте бота в канал как администратора
3. Дайте боту права на публикацию сообщений
4. Получите ID канала:
   - Перешлите любое сообщение из канала в [@userinfobot](https://t.me/userinfobot)
   - ID канала будет в формате `-1001234567890`

#### Настройка .env:
```env
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890
TELEGRAM_PHONE=+1234567890
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHANNEL_ID=-1001234567890
```

### 2. Настройка внешних API (опционально)

#### Reddit API:
1. Перейдите на [reddit.com/prefs/apps](https://reddit.com/prefs/apps)
2. Нажмите "Create App" или "Create Another App"
3. Выберите "script" как тип приложения
4. Заполните название и описание
5. Сохраните `client_id` и `client_secret`

#### Twitter API:
1. Перейдите на [developer.twitter.com](https://developer.twitter.com)
2. Создайте новое приложение
3. Получите Bearer Token в разделе "Keys and Tokens"

#### Настройка в .env:
```env
# Reddit (опционально)
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
REDDIT_USER_AGENT=F1NewsBot/1.0

# Twitter (опционально)
TWITTER_BEARER_TOKEN=your_twitter_bearer_token
```

### 3. Настройка n8n

1. Откройте http://localhost:5678
2. Логин: `admin` / `admin123`
3. Импортируйте workflow из `n8n_workflows/f1_news_workflow.json`
4. Настройте Telegram уведомления в workflow

### 4. Проверка работы

**API Endpoints:**
- http://localhost:8000 - главная страница
- http://localhost:8000/health - статус системы
- http://localhost:8000/docs - документация API

**Telegram Bot команды:**
- `/start` - начало работы
- `/help` - справка
- `/status` - статус системы
- `/queue` - очередь публикаций
- `/publish` - публикация следующей новости

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

## 📊 Мониторинг и управление

### Логи

**Docker:**
```bash
# Просмотр логов всех сервисов
docker-compose logs -f

# Логи конкретного сервиса
docker-compose logs -f f1-news-bot
docker-compose logs -f ollama
docker-compose logs -f postgres
```

**Локально:**
- `logs/f1_news_bot.log` - основные логи
- `logs/error_f1_news_bot.log` - ошибки

### Статистика

Доступна через API endpoint `/api/stats`:

```bash
curl http://localhost:8000/api/stats
```

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

### Управление сервисами

**Docker:**
```bash
# Остановка всех сервисов
docker-compose down

# Перезапуск сервиса
docker-compose restart f1-news-bot

# Обновление и перезапуск
docker-compose pull
docker-compose up -d

# Очистка данных (ОСТОРОЖНО!)
docker-compose down -v
```

**Проверка статуса:**
```bash
# Статус контейнеров
docker-compose ps

# Использование ресурсов
docker stats

# Проверка здоровья
curl http://localhost:8000/health
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

## 🔧 Troubleshooting

### Частые проблемы

#### 1. **Ollama не отвечает**

**Docker:**
```bash
# Проверить статус контейнера
docker-compose ps ollama

# Перезапустить Ollama
docker-compose restart ollama

# Проверить логи
docker-compose logs ollama

# Установить модель вручную
docker-compose exec ollama ollama pull llama2
```

**Локально:**
```bash
# Проверить статус
ollama list

# Перезапустить
ollama serve

# Установить модель
ollama pull llama2
```

#### 2. **Ошибки Telegram API**

- Проверьте правильность токенов в `.env`
- Убедитесь, что бот добавлен в канал с правами на публикацию
- Проверьте, что канал ID указан правильно (начинается с `-100`)

#### 3. **Проблемы с базой данных**

**Docker:**
```bash
# Проверить статус PostgreSQL
docker-compose ps postgres

# Подключиться к базе
docker-compose exec postgres psql -U f1_user -d f1_news

# Пересоздать базу данных
docker-compose down
docker volume rm tg_bot_f1_postgres_data
docker-compose up -d
```

**Локально:**
```bash
# Проверить подключение
psql -d f1_news -c "SELECT 1;"

# Перезапустить Redis
redis-server
```

#### 4. **Проблемы с Docker**

```bash
# Очистить все контейнеры и образы
docker-compose down
docker system prune -a

# Пересобрать образы
docker-compose build --no-cache
docker-compose up -d

# Проверить использование диска
docker system df
```

#### 5. **Проблемы с n8n**

```bash
# Проверить статус
docker-compose ps n8n

# Перезапустить
docker-compose restart n8n

# Очистить данные n8n
docker-compose down
docker volume rm tg_bot_f1_n8n_data
docker-compose up -d
```

### Диагностика

**Проверка всех сервисов:**
```bash
# Статус контейнеров
docker-compose ps

# Проверка здоровья API
curl http://localhost:8000/health

# Проверка Ollama
curl http://localhost:11434/api/tags

# Проверка Redis
docker-compose exec redis redis-cli ping
```

**Логи для диагностики:**
```bash
# Все логи
docker-compose logs

# Логи конкретного сервиса
docker-compose logs f1-news-bot
docker-compose logs ollama
docker-compose logs postgres
docker-compose logs redis
```

### Восстановление после сбоя

```bash
# Полная переустановка (ОСТОРОЖНО - удалит все данные!)
docker-compose down -v
docker system prune -a
docker-compose up -d

# Мягкий перезапуск
docker-compose restart
```

## 🎯 Первая публикация

После настройки системы:

1. **Дождитесь сбора новостей** (15 минут после запуска)
2. **Проверьте очередь** в Telegram: `/queue`
3. **Опубликуйте новость**: `/publish` в Telegram
4. **Одобрите или отклоните** контент через кнопки

## 📈 Производительность

- **Сбор новостей**: каждые 15 минут
- **Обработка AI**: до 1 минуты на новость
- **Модерация**: автоматическая
- **Публикация**: до 5 постов в час
- **Мониторинг**: каждые 5 минут

## 🔄 Обновления

```bash
# Обновление кода
git pull origin main

# Перезапуск сервисов (Docker)
docker-compose down
docker-compose up -d

# Обновление зависимостей
pip install -r requirements.txt --upgrade
```

## 📝 Логи и отладка

**Проверка работы системы:**
```bash
# Статус всех сервисов
docker-compose ps

# Проверка здоровья
curl http://localhost:8000/health

# Статистика
curl http://localhost:8000/api/stats
```

**Просмотр логов:**
```bash
# Все логи
docker-compose logs -f

# Конкретный сервис
docker-compose logs -f f1-news-bot
```

## 🤝 Вклад в проект

1. Fork репозитория
2. Создайте ветку для новой функции
3. Внесите изменения
4. Создайте Pull Request

## 📄 Лицензия

MIT License

## 🆘 Поддержка

- **Issues**: [GitHub Issues](https://github.com/YOUR_USERNAME/f1-news-bot/issues)
- **Документация**: [README.md](README.md)
- **Примеры**: [examples/](examples/)

---

**Создано с ❤️ для F1 фанатов**
