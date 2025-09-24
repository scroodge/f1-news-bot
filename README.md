# F1 News Bot 🏎️

Автоматический сервис для сбора, обработки и публикации новостей Formula 1 в Telegram канал.

## 📋 Требования

- **Python 3.11+** (рекомендуется 3.11)
- **PostgreSQL 12+**
- **Redis 6+**
- **Ollama** (для AI обработки)
- **Telegram Bot Token** (от @BotFather)

### Установка Python 3.11

Если у вас нет Python 3.11, используйте один из способов:

**С pyenv (рекомендуется):**
```bash
# Установка pyenv
curl https://pyenv.run | bash

# Установка Python 3.11
pyenv install 3.11.0
pyenv local 3.11.0  # для этого проекта
```

**С Homebrew (macOS):**
```bash
brew install python@3.11
```

**С apt (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-dev
```

## Возможности

- 🔍 **Сбор новостей** из множества источников (RSS, Telegram, Reddit, Twitter)
- 🤖 **Умная AI обработка** с оптимизацией для русских новостей (пропуск Ollama)
- ⚡ **Быстрая обработка** русских новостей без использования AI
- 🌍 **Автоматический перевод** иностранных новостей на русский язык
- 🛡️ **Модерация** и фильтрация контента по релевантности и качеству
- 📅 **Планировщик публикаций** с учетом оптимального времени для F1 аудитории
- 📱 **Telegram Bot** для управления и публикации
- 🔄 **n8n интеграция** для автоматизации workflow
- 📊 **Мониторинг** системы и статистика

## 📚 Документация

- [**Telegram Bot Integration**](TELEGRAM_BOT_INTEGRATION.md) - Подробное руководство по интеграции Telegram бота
- [**Usage Guide**](USAGE_GUIDE.md) - Руководство пользователя
- [**Setup Guide**](SETUP_GIT.md) - Инструкции по настройке

## 🐳 Docker запуск (Рекомендуется)

### Быстрый старт

```bash
# 1. Клонирование
git clone https://github.com/yourusername/f1-news-bot.git
cd f1-news-bot

# 2. Настройка окружения
cp config.env.example .env
# Отредактируйте .env с вашими настройками

# 3. Настройка Telegram авторизации (обязательно!)
chmod +x setup_telegram_docker.sh
./setup_telegram_docker.sh

# 4. Запуск всей системы
./docker-run-all.sh
```

### Пошаговый запуск

```bash
# Запуск всей системы (Main App + Telegram Bot)
docker compose up -d
```

### Проверка работы

- **API**: http://localhost:8000
- **Документация**: http://localhost:8000/docs
- **Redis**: localhost:6379
- **Telegram бот**: Проверьте команды в боте

### Управление

```bash
# Просмотр логов основного приложения
docker compose logs -f f1-news-main

# Просмотр логов Telegram бота
docker compose logs -f f1-news-telegram

# Просмотр всех логов
docker compose logs -f

# Остановка
docker compose down
```

## Архитектура

```
[Источники] → [Сборщик] → [Умная обработка] → [Модерация] → [n8n] → [Telegram Bot] → [Канал]
     ↓              ↓              ↓              ↓         ↓
[Web RSS]    [Telegram API]  [Русские: Быстро]  [Проверка] [Workflow] [Автопостинг]
[Reddit]     [Twitter API]   [Иностранные: AI]  [Форматирование]
[News sites]                 [Перевод + AI]
```

### 🚀 Оптимизация производительности

**Умная обработка новостей:**
- **Русские новости**: Мгновенная обработка без AI (экономия ресурсов)
- **Иностранные новости**: Полная AI обработка с переводом на русский
- **Релевантность**: Автоматическая оценка по F1-ключевым словам
- **Теги**: Извлечение из заголовка и содержания
- **Summary**: Использование оригинального текста для русских новостей

## 🔧 Решение проблем с зависимостями

Если при запуске возникают ошибки типа `No module named 'async_timeout'`:

```bash
# Пересоздайте виртуальное окружение
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 🔐 Настройка Telegram авторизации для Docker

**Важно:** Telegram коллектор требует авторизацию с логином/паролем для чтения каналов.

### Автоматическая настройка:
```bash
chmod +x setup_telegram_docker.sh
./setup_telegram_docker.sh
```

### Ручная настройка:
```bash
# 1. Авторизация локально
python setup_telegram_api.py

# 2. Копирование сессии в Docker
docker cp telegram_session.session container_name:/app/telegram_session.session

# 3. Перезапуск контейнеров
docker compose down && docker compose up -d
```

**Примечание:** Файл `telegram_session.session` содержит авторизационные данные и должен быть защищен!

## 🚀 Быстрый запуск

### Способ 1: Локальная разработка (рекомендуется)

```bash
# Клонирование и настройка
git clone <your-repo-url>
cd TG_BOT_F1

# Проверка версии Python (должна быть 3.11+)
python3 --version  # или python3.11 --version

# Создание виртуального окружения (требуется Python 3.11+)
python3.11 -m venv venv  # или python3 -m venv venv если Python 3.11 по умолчанию
source venv/bin/activate  # На Windows: venv\Scripts\activate
pip install -r requirements.txt

# Настройка окружения
cp .env.example .env
# Отредактируйте .env с вашими настройками

# Запуск системы (основное приложение + Telegram бот)
python run_all.py

# Или запуск компонентов отдельно:
# Терминал 1: Основное приложение
python start_local.py

# Терминал 2: Telegram бот
python telegram_bot_standalone.py
```

**Доступ к API:**
- API: http://localhost:8000
- Документация: http://localhost:8000/docs
- Проверка здоровья: http://localhost:8000/health

### Способ 2: Ubuntu (рекомендуется для серверов)

```bash
# Клонирование репозитория
git clone https://github.com/YOUR_USERNAME/f1-news-bot.git
cd f1-news-bot

# Быстрая установка всех зависимостей
sudo apt update && sudo apt install -y python3 python3-pip python3-venv python3-dev postgresql postgresql-contrib redis-server build-essential libpq-dev curl screen

# Настройка базы данных
sudo -u postgres createdb f1_news
sudo -u postgres createuser f1_user
sudo -u postgres psql -c "ALTER USER f1_user PASSWORD 'f1_password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE f1_news TO f1_user;"

# Запуск сервисов
sudo systemctl start postgresql redis-server

# Настройка окружения
cp config.env.example .env
nano .env  # Отредактируйте с вашими данными

# Для случая с локальными Ollama и n8n используйте:
# OLLAMA_BASE_URL=http://localhost:11434
# (n8n уже запущен локально)

# Установка Python зависимостей (требуется Python 3.11+)
python3.11 -m venv venv  # или python3.11 -m venv venv  # или python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Проверка локальных сервисов (если уже установлены)
curl http://localhost:11434/api/tags  # Проверка Ollama
curl http://localhost:5678            # Проверка n8n
pg_isready -h localhost -p 5432       # Проверка PostgreSQL
redis-cli ping                        # Проверка Redis

# Если сервисы не установлены, установите их:
# sudo apt install postgresql postgresql-contrib redis-server
# curl -fsSL https://ollama.ai/install.sh | sh
# npm install -g n8n

# Автоматический запуск с проверкой
./run-local.sh

# Или ручной запуск в screen:
# screen -S f1-news-bot
# python run.py
# Ctrl+A, D для выхода из screen
```

### Способ 2: Docker (рекомендуется для разработки)

```bash
# Клонирование репозитория
git clone https://github.com/YOUR_USERNAME/f1-news-bot.git
cd f1-news-bot

# Настройка окружения
cp config.env.example .env
# Отредактируйте .env файл с вашими данными

# Запуск всех сервисов
docker compose up -d

# Проверка статуса
docker compose ps

# Просмотр логов
docker compose logs -f f1-news-bot
```

### Способ 2.1: Docker + локальные сервисы

Если у вас уже запущены PostgreSQL, Redis, Ollama и n8n локально:

```bash
# Клонирование репозитория
git clone https://github.com/YOUR_USERNAME/f1-news-bot.git
cd f1-news-bot

# Настройка окружения
cp config.env.example .env
# Отредактируйте .env файл:
# DATABASE_URL=postgresql://f1_user:f1_password@localhost:5432/f1_news
# REDIS_URL=redis://localhost:6379/0
# OLLAMA_BASE_URL=http://localhost:11434

# Запуск только Redis и F1 News Bot
docker compose -f docker-compose-minimal.yml up -d

# Проверка статуса
docker compose -f docker-compose-minimal.yml ps

# Просмотр логов
docker compose -f docker-compose-minimal.yml logs -f f1-news-bot
```

### Способ 2.2: Полностью локальный запуск (рекомендуется для серверов)

Если все сервисы уже установлены локально:

```bash
# Клонирование репозитория
git clone https://github.com/YOUR_USERNAME/f1-news-bot.git
cd f1-news-bot

# Автоматический запуск с проверкой сервисов
./run-local.sh

# Или ручной запуск:
# cp config.env.example .env
# nano .env  # Настройте с вашими данными
# python3.11 -m venv venv  # или python3 -m venv venv
# source venv/bin/activate
# pip install -r requirements.txt
# python run.py
```

**Преимущества полностью локального подхода:**
- Минимальное потребление ресурсов
- Нет Docker overhead
- Прямое подключение к сервисам
- Проще отладка и мониторинг

**Сервисы будут доступны:**
- API: http://localhost:8000
- n8n: http://localhost:5678 (admin/admin123)
- Ollama: http://localhost:11434

### Способ 3: Локальная установка (подробная)

#### 1. Клонирование и настройка

```bash
git clone https://github.com/YOUR_USERNAME/f1-news-bot.git
cd f1-news-bot

# Создание виртуального окружения
python3.11 -m venv venv  # или python3.11 -m venv venv  # или python3 -m venv venv
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

**Ubuntu/Debian:**
```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Python и pip
sudo apt install python3 python3-pip python3-venv python3-dev -y

# Установка PostgreSQL
sudo apt install postgresql postgresql-contrib -y

# Установка Redis
sudo apt install redis-server -y

# Установка системных зависимостей
sudo apt install build-essential libpq-dev curl -y

# Запуск сервисов
sudo systemctl start postgresql
sudo systemctl enable postgresql
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Создание базы данных
sudo -u postgres createdb f1_news
sudo -u postgres createuser f1_user
sudo -u postgres psql -c "ALTER USER f1_user PASSWORD 'f1_password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE f1_news TO f1_user;"
```

**macOS:**
```bash
# Установка через Homebrew
brew install postgresql redis

# Запуск сервисов
brew services start postgresql
brew services start redis

# Создание базы данных
createdb f1_news
```

**Ollama для Ubuntu:**
```bash
# Установка Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Добавление пользователя в группу docker (если нужно)
sudo usermod -aG docker $USER

# Перезагрузка сессии или выход/вход
# или выполните: newgrp docker

# Запуск Ollama в фоне
ollama serve &

# Установка модели (это может занять время)
ollama pull llama2

# Проверка установленных моделей
ollama list

# Проверка работы Ollama
curl http://localhost:11434/api/tags
```

**Ollama для macOS:**
```bash
# Установка через Homebrew
brew install ollama

# Запуск
ollama serve

# Установка модели
ollama pull llama2
```

**n8n для Ubuntu:**
```bash
# Установка Node.js
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Установка n8n
sudo npm install -g n8n

# Запуск n8n в фоне
n8n start &

# Или запуск с настройками
N8N_BASIC_AUTH_ACTIVE=true N8N_BASIC_AUTH_USER=admin N8N_BASIC_AUTH_PASSWORD=admin123 n8n start
```

**n8n для macOS:**
```bash
# Установка через Homebrew
brew install node
npm install -g n8n
n8n start
```

#### 4. Запуск приложения

**Для Ubuntu (рекомендуется использовать screen/tmux):**

```bash
# Установка screen для управления сессиями
sudo apt install screen -y

# Создание виртуального окружения
python3.11 -m venv venv  # или python3 -m venv venv


# Установка зависимостей
pip install -r requirements.txt

# Создание папки для логов
mkdir -p logs

# Запуск в screen сессии
screen -S f1-news-bot

# В screen сессии - запуск API сервера
python run.py

# Выйти из screen: Ctrl+A, затем D
# Вернуться в screen: screen -r f1-news-bot
```
source venv/bin/activate
**Для macOS:**
```bash
# Создание виртуального окружения
python3.11 -m venv venv  # или python3 -m venv venv
source venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt

# Запуск API сервера
python run.py

# В другом терминале - запуск Telegram Bot
python -m src.telegram.bot
```

**Альтернативный запуск через systemd (Ubuntu):**

Создайте systemd сервис для автоматического запуска:

```bash
# Создание сервисного файла
sudo nano /etc/systemd/system/f1-news-bot.service
```

Содержимое файла:
```ini
[Unit]
Description=F1 News Bot
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=mcdir
WorkingDirectory=/home/mcdir/f1-news-bot
Environment=PATH=/home/mcdir/f1-news-bot/venv/bin
ExecStart=/home/mcdir/f1-news-bot/venv/bin/python run.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# Перезагрузка systemd и запуск сервиса
sudo systemctl daemon-reload
sudo systemctl enable f1-news-bot
sudo systemctl start f1-news-bot

# Проверка статуса
sudo systemctl status f1-news-bot

# Просмотр логов
sudo journalctl -u f1-news-bot -f
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
