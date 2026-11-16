"""Exercise Alembic's real env.py on an explicitly disposable empty database.

Run with DATABASE_URL targeting a database whose name ends in _migration_test.
Never drops databases or existing schemas; an occupied target is refused.
"""

from pathlib import Path
import sys

# Support `python scripts/check_migrations.py` from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url

from app import models  # noqa: F401
from app.config import settings
from app.db import Base


def main() -> None:
    url = make_url(settings.database_url)
    if not url.database or not url.database.endswith("_migration_test"):
        raise SystemExit("Refusing target: database name must end in _migration_test.")
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            if inspect(connection).get_table_names():
                raise SystemExit("Refusing target: migration test database must be empty.")
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        command.upgrade(config, "head")
        command.downgrade(config, "-1")
        command.upgrade(config, "head")
        with engine.connect() as connection:
            differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
            if differences:
                raise SystemExit("Migration schema differs from SQLAlchemy models.")
        print("Alembic upgrade/downgrade/upgrade and schema comparison passed.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
