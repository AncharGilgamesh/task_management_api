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
```

`DB_ECHO=true` включает логирование SQL-запросов (по умолчанию выключено).
Файл `.env` не попадает в Git, не добавляйте в репозиторий реальные пароли.

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

## Тесты

```powershell
pytest
```

Тесты `/health/db` используют подмену зависимости `get_db` и не требуют запущенной PostgreSQL.
