from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from .config import DATABASE_URL, DB_PATH, CUSTOMER_DB_PATH, USER_DB_PATH
from pathlib import Path
import sqlite3

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

# Enable SQLite foreign key constraints
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def create_auxiliary_database(path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    auxiliary_engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(auxiliary_engine, "connect")
    def set_auxiliary_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return auxiliary_engine


customer_engine = create_auxiliary_database(CUSTOMER_DB_PATH)
user_engine = create_auxiliary_database(USER_DB_PATH)
CustomerSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=customer_engine)
UserSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=user_engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_customer_db():
    db = CustomerSessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_user_db():
    db = UserSessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_customer_user_data():
    """Copy legacy customer and staff purchases into their dedicated SQLite files."""
    legacy_path = str(Path(DB_PATH).resolve())
    migrations = (
        (CUSTOMER_DB_PATH, "customers"),
        (CUSTOMER_DB_PATH, "customer_purchases"),
        (USER_DB_PATH, "user_purchases"),
    )
    for destination, table_name in migrations:
        target = sqlite3.connect(destination)
        try:
            target.execute("ATTACH DATABASE ? AS legacy", (legacy_path,))
            legacy_table = target.execute(
                "SELECT 1 FROM legacy.sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            ).fetchone()
            target_table = target.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            ).fetchone()
            if not legacy_table or not target_table:
                continue
            columns = [
                row[1]
                for row in target.execute(f"PRAGMA legacy.table_info({table_name})").fetchall()
            ]
            if not columns:
                continue
            column_list = ", ".join(f'"{column}"' for column in columns)
            target.execute(
                f'INSERT OR IGNORE INTO main."{table_name}" ({column_list}) '
                f'SELECT {column_list} FROM legacy."{table_name}"'
            )
            target.commit()
        finally:
            target.close()

    legacy_db = sqlite3.connect(str(Path(DB_PATH).resolve()))
    try:
        legacy_tables = {
            row[0]
            for row in legacy_db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if {"customers", "customer_purchases", "user_purchases"}.issubset(legacy_tables):
            for destination, table_name in migrations:
                target = sqlite3.connect(destination)
                try:
                    target.execute("ATTACH DATABASE ? AS legacy", (legacy_path,))
                    source_columns = target.execute(
                        f"PRAGMA legacy.table_info({table_name})"
                    ).fetchall()
                    target_columns = target.execute(
                        f"PRAGMA main.table_info({table_name})"
                    ).fetchall()
                    primary_keys = [
                        row[1]
                        for row in sorted(source_columns, key=lambda column: column[5])
                        if row[5]
                    ]
                    if not source_columns or not target_columns or not primary_keys:
                        raise RuntimeError(
                            f"Cannot safely migrate legacy table '{table_name}'."
                        )
                    matches = " AND ".join(
                        f'd."{column}" = s."{column}"' for column in primary_keys
                    )
                    missing_rows = target.execute(
                        f'SELECT COUNT(*) FROM legacy."{table_name}" AS s '
                        f'WHERE NOT EXISTS (SELECT 1 FROM main."{table_name}" AS d WHERE {matches})'
                    ).fetchone()[0]
                    if missing_rows:
                        raise RuntimeError(
                            f"Migration of '{table_name}' is incomplete; "
                            f"{missing_rows} legacy rows were not copied."
                        )
                finally:
                    target.close()
            legacy_db.execute("PRAGMA foreign_keys=OFF")
            legacy_db.execute("DROP TABLE customer_purchases")
            legacy_db.execute("DROP TABLE customers")
            legacy_db.execute("DROP TABLE user_purchases")
            legacy_db.commit()
    finally:
        legacy_db.close()
