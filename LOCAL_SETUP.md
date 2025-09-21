# Локальная настройка F1 News Bot

## Быстрый старт

### 1. Создание виртуального окружения
```bash
python3.11 -m venv venv
source venv/bin/activate
```

### 2. Установка зависимостей
```bash
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

### 3. Настройка переменных окружения
Создайте файл `.env` на основе `config.env.example`:
```bash
cp config.env.example .env
# Отредактируйте .env файл с вашими настройками
```

### 4. Запуск приложения
```bash
python start_local.py
```

## Проверка работы

После запуска приложение будет доступно по адресам:
- **API**: http://localhost:8000
- **Документация**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## Структура проекта

```
src/
├── main.py              # Главный файл FastAPI приложения
├── config.py            # Конфигурация
├── models.py            # Модели данных
├── database.py          # Работа с базой данных
├── collectors/          # Сборщики новостей
│   ├── rss_collector.py
│   ├── telegram_collector.py
│   └── reddit_collector.py
├── ai/                  # AI обработка
│   ├── ollama_client.py
│   └── content_processor.py
├── moderator/           # Модерация и планирование
│   ├── content_moderator.py
│   └── publication_scheduler.py
├── telegram_bot/        # Telegram бот
│   └── bot.py
└── utils/               # Утилиты
    ├── logger.py
    └── monitor.py
```

## Требования

- Python 3.11+
- PostgreSQL (для полной функциональности)
- Redis (для кэширования)
- Ollama (для AI обработки)

## Примечания

- Приложение работает с Python 3.11 для лучшей совместимости
- Все зависимости установлены и протестированы
- API готов к использованию
- Для полной работы требуется настройка внешних сервисов (PostgreSQL, Redis, Ollama, Telegram Bot)
