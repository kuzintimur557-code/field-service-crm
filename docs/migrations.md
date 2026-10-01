# Миграции схемы базы данных

Схема управляется Alembic. `app/database.py::init_db()` — замороженный
bootstrap: создаёт схему с нуля для свежих dev-баз, **новые изменения схемы
в него не добавляются**.

## Правила

1. Любое изменение схемы (таблица, колонка, индекс) — отдельная Alembic-миграция.
2. Миграции пишутся переносимым SQL через `op.execute(...)` — один и тот же
   код работает на SQLite и PostgreSQL (тот же диалектный подход, что и в
   коде приложения: `?`-placeholders, `datetime('now')` и т.д. — запрещены
   конструкции, не проходящие через `app/postgres_adapter.py`).
3. Миграция должна быть идемпотентной по замыслу Alembic: одна схема — один
   прогон `upgrade`.
4. `downgrade` обязателен и откатывает изменение.

## Создание миграции

```bash
alembic revision -m "add example column"
# отредактировать migrations/versions/<rev>_<slug>.py
```

```python
def upgrade():
    op.execute(
        "ALTER TABLE tasks ADD COLUMN example_field TEXT"
    )

def downgrade():
    op.execute(
        "ALTER TABLE tasks DROP COLUMN example_field"
    )
```

## Применение

- Локально (SQLite): `alembic upgrade head`
- PostgreSQL: `DATABASE_BACKEND=postgresql DATABASE_URL=... alembic upgrade head`

## Существующие базы

Базы, созданные до внедрения Alembic, содержат схему из `init_db()`:

```bash
alembic stamp 0001
```

Свежие базы: `init_db()` создаёт схему, затем `alembic stamp 0001`.

## Проверки

`tests/smoke_migrations.py` гоняет stamp/upgrade/current на временной
SQLite-базе; шаг `Run Alembic migrations on PostgreSQL` в CI проверяет
миграции на PostgreSQL 16 после полного прогона приложения.
