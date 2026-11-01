# Task Management API

REST API для управления проектами и задачами (FastAPI, SQLAlchemy 2.0 Async, PostgreSQL).

## Установка

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Запуск

Рекомендуемый способ — `compose.yaml`. PostgreSQL работает в отдельном контейнере. Сервис `migrate` применяет Alembic-миграции (`alembic upgrade head`) после готовности базы. FastAPI стартует только после успешного завершения миграций. Данные PostgreSQL хранятся в именованном томе `task_management_api_compose_postgres_data`.

Старая конфигурация `docker-compose.yml` больше не поддерживается. Использовать нужно только `compose.yaml`. Старый том и уже запущенные контейнеры эта конфигурация сама не удаляет.

Создайте локальный env-файл из шаблона и запустите проект:

```powershell
Copy-Item .env.docker.example .env.docker
docker compose --env-file .env.docker up --build
```

`.env.docker.example` содержит только демонстрационные значения для локальной разработки. Файл `.env.docker` не нужно добавлять в Git: его уже скрывает `.gitignore`.

- Swagger: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health
- Проверка базы: http://127.0.0.1:8000/health/db
- PostgreSQL с хоста: `127.0.0.1:5433`
- Адрес базы внутри Compose для приложения: `db:5432`

`DOCKER_SECRET_KEY` в `.env.docker` подписывает JWT и обязателен (минимум 32 символа). Сгенерировать:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

`ACCESS_TOKEN_EXPIRE_MINUTES` — время жизни access-токена в минутах (по умолчанию 30). `DB_ECHO=true` включает логирование SQL-запросов (по умолчанию выключено).

## Тесты

```powershell
pytest
```

Тесты не требуют запущенной PostgreSQL: зависимость `get_db` подменяется, а тесты аутентификации
используют SQLite в памяти и отдельный тестовый `SECRET_KEY` (см. `tests/conftest.py`).
