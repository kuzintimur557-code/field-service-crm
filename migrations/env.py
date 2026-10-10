"""Alembic environment wired to the application database configuration.

Migrations are plain portable SQL executed through op.execute(), so the
same revision runs on both SQLite (development) and PostgreSQL (production).
Autogenerate is intentionally disabled: the project uses raw SQL DDL.
"""

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_database_url():
    backend = str(os.getenv("DATABASE_BACKEND") or "").strip().lower()
    database_url = str(os.getenv("DATABASE_URL") or "").strip()

    if backend == "postgresql" or database_url.startswith(
        ("postgres://", "postgresql://")
    ):
        if not database_url:
            raise RuntimeError(
                "DATABASE_URL is required for postgresql migrations"
            )
        if database_url.startswith("postgres://"):
            database_url = "postgresql://" + database_url[len("postgres://"):]
        return database_url.replace(
            "postgresql://", "postgresql+psycopg://", 1
        )

    data_dir = Path(os.getenv("DATA_DIR", "."))
    db_path = data_dir / "crm.db"
    return f"sqlite:///{db_path}"


def run_migrations_offline():
    context.configure(
        url=get_database_url(),
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = create_engine(get_database_url())

    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)

        with context.begin_transaction():
            context.run_migrations()

    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
