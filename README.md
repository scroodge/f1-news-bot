# 🏎️ F1 News Bot

Автоматический сервис для сбора, обработки и публикации новостей Formula 1 в Telegram канал с использованием AI.

## ✨ Возможности

- 🔍 **Сбор новостей** из множества источников (RSS, Telegram каналы)
- 🤖 **Умная AI обработка** с оптимизацией для русских новостей
- ⚡ **Быстрая обработка** русских новостей без использования AI
- 🌍 **Автоматический перевод** иностранных новостей на русский язык
- 🛡️ **Модерация** и фильтрация контента по релевантности
- 📱 **Telegram Bot** для управления и публикации
- 📊 **Мониторинг** системы и статистика

## 🚀 Быстрый старт

### Docker (Рекомендуется)

```bash
# 1. Клонирование
git clone https://github.com/yourusername/f1-news-bot.git
cd f1-news-bot

# 2. Настройка окружения
cp config.env.example .env
# Отредактируйте .env с вашими настройками

# 3. Настройка Telegram авторизации
chmod +x setup_telegram_docker.sh
./setup_telegram_docker.sh

# 4. Запуск системы
docker compose up -d
```

### Локальная установка

```bash
# 1. Клонирование
git clone https://github.com/yourusername/f1-news-bot.git
cd f1-news-bot

# 2. Создание виртуального окружения
python3.11 -m venv venv
source venv/bin/activate

# 3. Установка зависимостей
pip install -r requirements.txt

# 4. Настройка окружения
cp config.env.example .env
# Отредактируйте .env с вашими настройками

# 5. Запуск системы
python run_all.py
```

## 📋 Требования

- **Python 3.11+**
- **PostgreSQL 12+**
- **Redis 6+**
- **Ollama** (для AI обработки)
- **Telegram Bot Token**

## 🔧 Настройка

### 1. Telegram Bot

1. Создайте бота через [@BotFather](https://t.me/BotFather)
2. Получите API данные на [my.telegram.org](https://my.telegram.org)
3. Настройте канал и добавьте бота как администратора

### 2. База данных

```bash
# PostgreSQL
sudo -u postgres createdb f1_news
sudo -u postgres createuser f1_user
sudo -u postgres psql -c "ALTER USER f1_user PASSWORD 'f1_password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE f1_news TO f1_user;"
```

### 3. Ollama

```bash
# Установка Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Установка модели
ollama pull llama3.2
```

## 📁 Структура проекта

```
src/
├── ai/                 # AI обработка (Ollama)
├── collectors/         # Сборщики новостей
├── telegram_bot/       # Telegram Bot
├── services/           # Сервисы (Redis)
├── utils/              # Утилиты
├── config.py           # Конфигурация
├── database.py         # База данных
├── models.py           # Модели данных
└── main.py             # Основное приложение
```

## 🎯 Использование

### Telegram Bot команды

- `/start` - начало работы
- `/help` - справка
- `/status` - статус системы
- `/queue` - очередь публикаций
- `/publish` - публикация новости
- `/published` - опубликованные новости

### API Endpoints

- `GET /health` - проверка состояния
- `GET /docs` - документация API
- `POST /api/collect-news` - запуск сбора новостей
- `POST /api/process-news` - запуск обработки

## 🐳 Docker

### Управление контейнерами

```bash
# Запуск
docker compose up -d

# Просмотр логов
docker compose logs -f f1-news-main
docker compose logs -f f1-news-telegram

# Остановка
docker compose down
```

### Проверка работы

- **API**: http://localhost:8000
- **Документация**: http://localhost:8000/docs
- **Redis**: localhost:6379

## 🔍 Мониторинг

### Логи

```bash
# Docker
docker compose logs -f

# Локально
tail -f logs/f1_news_bot.log
```

### Статистика

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/stats
```

## 🚀 Оптимизация производительности

**Умная обработка новостей:**
- **Русские новости**: Мгновенная обработка без AI
- **Иностранные новости**: Полная AI обработка с переводом
- **Релевантность**: Автоматическая оценка по F1-ключевым словам

## 🔧 Troubleshooting

### Частые проблемы

1. **Ollama не отвечает**
   ```bash
   curl http://localhost:11434/api/tags
   ollama serve
   ```

2. **Ошибки Telegram API**
   - Проверьте токены в `.env`
   - Убедитесь, что бот добавлен в канал

3. **Проблемы с базой данных**
   ```bash
   psql -d f1_news -c "SELECT 1;"
   ```

## 📚 Документация

- [**Telegram Bot Integration**](TELEGRAM_BOT_INTEGRATION.md)
- [**Usage Guide**](USAGE_GUIDE.md)
- [**Local Setup**](LOCAL_SETUP.md)
- [**Docker Production**](DOCKER_PRODUCTION.md)
- [**Telegram Setup**](TELEGRAM_SETUP.md)

## 🤝 Вклад в проект

1. Fork репозитория
2. Создайте ветку для новой функции
3. Внесите изменения
4. Создайте Pull Request

## 📄 Лицензия

MIT License

---

**Создано с ❤️ для F1 фанатов**