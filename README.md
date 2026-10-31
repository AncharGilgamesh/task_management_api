# Task Management API

REST API для управления проектами и задачами (FastAPI, SQLAlchemy 2.0 Async, PostgreSQL).

## Установка

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Настройка окружения

Скопируйте шаблон и при необходимости отредактируйте значения:

```powershell
Copy-Item .env.example .env
```

Для локальной разработки с `docker-compose.yml` используйте:

```
DATABASE_URL=postgresql+asyncpg://task_user:task_password@localhost:5432/task_management
DB_ECHO=false
SECRET_KEY=<ваш секрет, см. ниже>
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

`DB_ECHO=true` включает логирование SQL-запросов (по умолчанию выключено).
Файл `.env` не попадает в Git, не добавляйте в репозиторий реальные пароли и секреты.

`SECRET_KEY` подписывает JWT и обязателен (минимум 32 символа, значения по умолчанию нет;
без него приложение и Alembic не запустятся). Сгенерировать:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

`ACCESS_TOKEN_EXPIRE_MINUTES` — время жизни access-токена в минутах (по умолчанию 30).

## Запуск PostgreSQL

```powershell
docker compose up -d
```

PostgreSQL доступен только с локальной машины (`127.0.0.1:5432`).

## Запуск приложения

```powershell
uvicorn app.main:app --reload
```

- Документация: http://127.0.0.1:8000/docs
- Проверка приложения: `GET /health`
- Проверка базы данных: `GET /health/db`
- Регистрация: `POST /auth/register`
- Вход: `POST /auth/login` (JSON `email`, `password`) возвращает `access_token`
- Текущий пользователь: `GET /auth/me` с заголовком `Authorization: Bearer <access_token>`

## Тесты

```powershell
pytest
```

Тесты не требуют запущенной PostgreSQL: зависимость `get_db` подменяется, а тесты аутентификации
используют SQLite в памяти и отдельный тестовый `SECRET_KEY` (см. `tests/conftest.py`).
