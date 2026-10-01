"""baseline

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-01 09:00:00

Baseline revision: the schema up to this point is created by
``app.database.init_db()`` (bootstrap for fresh databases). Existing
databases are stamped, not migrated:

    alembic stamp 0001

All schema changes after this revision live in Alembic migrations with
portable SQL (``op.execute``) that runs on both SQLite and PostgreSQL.
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Schema already exists: created by init_db() for fresh databases and
    # stamped via `alembic stamp 0001` for existing ones.
    pass


def downgrade():
    pass
