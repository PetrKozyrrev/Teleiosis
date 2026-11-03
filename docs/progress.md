# Progress

## Этап 1. Фундамент — завершён

- [x] 1.1 Окружение: Python, Git, VS Code, GitHub
- [x] 1.2 Структура проекта, .venv, .gitignore, .env.example
- [x] 1.3 Git и приватный репозиторий на GitHub
- [x] 1.4 FastAPI-каркас, эндпоинт /health, requirements.txt
- [x] 1.5 Первые документы в docs

## Текущее состояние
Запускается: `uvicorn app.main:app --reload`
Проверка: http://127.0.0.1:8000/health → {"status":"ok"}

## Следующий этап
Этап 2. База данных: проектирование схемы, PostgreSQL, миграции.

## Этап 2. База данных — в работе
- [x] 2.1 PostgreSQL в Docker
- [x] 2.2 Проектирование схемы (docs/database.md)
- [ ] 2.3 SQLAlchemy-модели
- [ ] 2.4 Миграции Alembic
- [ ] 2.5 Проверка схемы и ограничений