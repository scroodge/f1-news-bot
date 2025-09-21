# Настройка Git репозитория

## 1. Создание репозитория на GitHub

1. Перейдите на https://github.com
2. Нажмите кнопку "New repository" или "+" → "New repository"
3. Заполните данные:
   - **Repository name**: `f1-news-bot`
   - **Description**: `Automated F1 news collection, AI processing, and Telegram publication system`
   - **Visibility**: Public или Private (на ваш выбор)
   - **НЕ** добавляйте README, .gitignore или лицензию (они уже есть)
4. Нажмите "Create repository"

## 2. Подключение локального репозитория к GitHub

После создания репозитория на GitHub, выполните команды:

```bash
# Добавить удаленный репозиторий (замените YOUR_USERNAME на ваш GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/f1-news-bot.git

# Переименовать ветку в main (если еще не сделано)
git branch -M main

# Отправить код на GitHub
git push -u origin main
```

## 3. Альтернативный способ через SSH (если настроен)

```bash
# Если у вас настроен SSH ключ
git remote add origin git@github.com:YOUR_USERNAME/f1-news-bot.git
git branch -M main
git push -u origin main
```

## 4. Проверка

После выполнения команд:
- Перейдите на https://github.com/YOUR_USERNAME/f1-news-bot
- Убедитесь, что все файлы загружены
- Проверьте, что README.md отображается корректно

## 5. Дополнительные настройки (опционально)

### Настройка GitHub Actions для CI/CD

Создайте файл `.github/workflows/ci.yml`:

```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: f1_news_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
      
      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379

    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install pytest pytest-asyncio
    
    - name: Run tests
      run: |
        pytest tests/ -v
      env:
        DATABASE_URL: postgresql://postgres:postgres@localhost:5432/f1_news_test
        REDIS_URL: redis://localhost:6379/0
        OLLAMA_BASE_URL: http://localhost:11434
```

### Настройка Issues и Projects

1. В репозитории перейдите в "Issues" → "Labels"
2. Добавьте метки:
   - `bug` - для ошибок
   - `enhancement` - для улучшений
   - `feature` - для новых функций
   - `documentation` - для документации
   - `help wanted` - для помощи

### Настройка веток

```bash
# Создать ветку для разработки
git checkout -b develop
git push -u origin develop

# Создать ветку для новой функции
git checkout -b feature/new-source
git push -u origin feature/new-source
```

## 6. Полезные команды Git

```bash
# Посмотреть статус
git status

# Добавить изменения
git add .

# Сделать коммит
git commit -m "Описание изменений"

# Отправить на GitHub
git push

# Получить изменения с GitHub
git pull

# Посмотреть историю коммитов
git log --oneline

# Создать новую ветку
git checkout -b имя-ветки

# Переключиться на ветку
git checkout имя-ветки

# Слить ветку в main
git checkout main
git merge имя-ветки
```
