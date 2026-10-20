"""
Lightweight, additive-only auto-migration for local/dev use.

This project intentionally has no Alembic migration chain (it's a fast-
moving prototype, not a production deployment yet). That means whenever a
model gains a new column (e.g. `is_simulated`), an existing local SQLite
file created before that change is missing it, and
`Base.metadata.create_all()` does NOT help - it only creates tables that
don't exist yet, it never alters ones that do.

`run_auto_migrate()` closes that gap: for every table that already exists,
it compares the model's declared columns against what the DB actually has
and issues `ALTER TABLE ... ADD COLUMN` for anything missing. It never
drops, renames, or alters an existing column - only additive changes are
supported, which covers "pulled a newer version of the app, my old
smart_warehouse.db doesn't have column X yet" without needing to delete
your local database every time the schema evolves.

For Postgres or any real deployment, replace this with proper Alembic
migrations before going further - this is a convenience for local dev only.
"""
import logging

from sqlalchemy import inspect, text

from .database import Base, engine

logger = logging.getLogger("smart_warehouse.migrate")


def _default_clause(column) -> str:
    """Best-effort DDL DEFAULT for a column's Python-side default, so
    existing rows get backfilled with a sensible value instead of NULL
    (e.g. is_simulated=False for pre-existing boxes/movements)."""
    default = column.default
    if default is None or not getattr(default, "is_scalar", False):
        return ""
    value = default.arg
    if isinstance(value, bool):
        return f" DEFAULT {1 if value else 0}"
    if isinstance(value, (int, float)):
        return f" DEFAULT {value}"
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f" DEFAULT '{escaped}'"
    return ""


def run_auto_migrate() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # brand new table - create_all() already made it in full

            existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_cols:
                    continue

                col_type = column.type.compile(dialect=engine.dialect)
                default_clause = _default_clause(column)

                logger.warning(
                    "Auto-migrating: adding missing column %s.%s (%s) to your local database.",
                    table.name, column.name, col_type,
                )
                conn.execute(
                    text(f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" {col_type}{default_clause}')
                )
