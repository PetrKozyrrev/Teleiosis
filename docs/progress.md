# Progress

## Этап 1. Фундамент — завершён

- [x] 1.1 Окружение: Python, Git, VS Code, GitHub
- [x] 1.2 Структура проекта, .venv, .gitignore, .env.example
- [x] 1.3 Git и приватный репозиторий на GitHub
- [x] 1.4 FastAPI-каркас, эндпоинт /health, requirements.txt
- [x] 1.5 Первые документы в docs

## Этап 2. База данных — завершён
- [x] 2.1 PostgreSQL в Docker
- [x] 2.2 Проектирование схемы (docs/database.md)
- [x] 2.3 SQLAlchemy-модели
- [x] 2.4 Миграции Alembic
- [x] 2.5 Тесты схемы (pytest, отдельная БД teleiosis_test)

## Как запустить тесты
python -m pytest -v

## Следующий этап
Этап 3. Backend API (ядро): пользователи, материалы, категории, статусы.