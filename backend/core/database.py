from sqlalchemy import Connection, create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from core.config import DATABASE_URL
from core.database_models import Base
from core.logger import get_logger

logger = get_logger(__name__)

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be configured")

engine_options = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema(bind_target=None) -> None:
    """Create missing tables and backfill newly added columns on existing databases."""
    target = bind_target or engine
    Base.metadata.create_all(bind=target)

    # Backfill columns that may be absent on pre-existing local SQLite/Postgres DBs
    inspector = inspect(target)
    is_sqlite = target.dialect.name == "sqlite"
    json_type = "TEXT" if is_sqlite else "JSONB"
    bool_false = "0" if is_sqlite else "FALSE"

    column_migrations = {
        "products": [
            ("min_price", "FLOAT"),
            ("max_price", "FLOAT"),
            ("stock_on_hand", "INTEGER DEFAULT 0"),
            ("lead_time_days", "INTEGER NOT NULL DEFAULT 7"),
            ("service_level", "FLOAT NOT NULL DEFAULT 0.95"),
            ("holding_cost_per_unit", "FLOAT"),
            ("reorder_cost", "FLOAT"),
            ("updated_at", "TIMESTAMP"),
        ],
        "training_jobs": [
            ("model_name", "VARCHAR"),
            ("metrics", json_type),
            ("error_message", "TEXT"),
            ("updated_at", "TIMESTAMP"),
        ],
        "predictions": [
            ("inventory_recommendations", json_type),
            ("model_summary", json_type),
        ],
    }

    def _apply_alter(conn):
        existing_tables = set(inspector.get_table_names())
        for table_name, cols in column_migrations.items():
            if table_name not in existing_tables:
                continue
            existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
            for col_name, col_type in cols:
                if col_name not in existing_cols:
                    logger.info(f"Adding column {table_name}.{col_name} ({col_type})")
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"))

        if "users" in existing_tables:
            user_cols = {c["name"] for c in inspector.get_columns("users")}
            if "is_admin" not in user_cols:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT {bool_false}"))

    if isinstance(target, Connection):
        _apply_alter(target)
    else:
        with target.begin() as conn:
            _apply_alter(conn)
