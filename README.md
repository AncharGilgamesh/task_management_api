# Task Management API

REST API для проектов и задач. Регистрация, вход, проекты и участники с ролями viewer, member, admin. Владелец хранится в `owner_id`. Чужой проект отвечает 404.

## Установка

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

В `.env` обязательны `DATABASE_URL` (`postgresql+asyncpg://`) и `SECRET_KEY` от 32 символов. `ACCESS_TOKEN_EXPIRE_MINUTES` по умолчанию 30, `DB_ECHO` по умолчанию выключен.

```powershell
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

`alembic.ini` сам по себе базу не указывает: адрес берётся из `DATABASE_URL`.

## Docker

```powershell
Copy-Item .env.docker.example .env.docker
docker compose --env-file .env.docker up --build
```

База в сервисе `db`, миграции делает `migrate`, API поднимается после них. С хоста Postgres на `127.0.0.1:5433`. Swagger: http://127.0.0.1:8000/docs

`DOCKER_SECRET_KEY` подписывает JWT, минимум 32 символа.

## Кто что может

Viewer читает проект, задачи и историю. Member ещё создаёт и меняет задачи. Admin меняет проект, удаляет задачи и управляет viewer и member, но не назначает admin. Удалить проект может только владелец. Не хватает прав — 403.

Новая задача всегда `todo`. Смена статуса пишется в историю. Исполнителем можно поставить только активного участника этого проекта.

## Тесты

```powershell
python -m pytest
```

Postgres для этого не нужен, база в тестах — SQLite в памяти.

## CI

Workflow `.github/workflows/tests.yml` запускает pytest на push в `main` и на pull request.
