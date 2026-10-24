import sqlite3

import pytest

from backend.app import database


def _create_legacy_database(path):
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE customers (
                customer_id TEXT PRIMARY KEY,
                customer_name TEXT NOT NULL
            );
            CREATE TABLE customer_purchases (
                purchase_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL REFERENCES customers(customer_id)
            );
            CREATE TABLE user_purchases (
                user_purchase_id TEXT PRIMARY KEY,
                user_name TEXT NOT NULL
            );
            INSERT INTO customers VALUES ('C001', 'Legacy Customer');
            INSERT INTO customer_purchases VALUES ('CP001', 'C001');
            INSERT INTO user_purchases VALUES ('UP001', 'Legacy Staff');
            """
        )


def _create_customer_tables(path):
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE customers (
                customer_id TEXT PRIMARY KEY,
                customer_name TEXT NOT NULL
            );
            CREATE TABLE customer_purchases (
                purchase_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL REFERENCES customers(customer_id)
            );
            """
        )


def _create_user_tables(path):
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE user_purchases (
                user_purchase_id TEXT PRIMARY KEY,
                user_name TEXT NOT NULL
            )
            """
        )


def test_migration_preserves_records_and_is_safe_to_rerun(tmp_path, monkeypatch):
    legacy_path = tmp_path / "stocksense.db"
    customer_path = tmp_path / "customers.db"
    user_path = tmp_path / "users.db"
    _create_legacy_database(legacy_path)
    _create_customer_tables(customer_path)
    _create_user_tables(user_path)

    monkeypatch.setattr(database, "DB_PATH", str(legacy_path))
    monkeypatch.setattr(database, "CUSTOMER_DB_PATH", str(customer_path))
    monkeypatch.setattr(database, "USER_DB_PATH", str(user_path))

    database.migrate_customer_user_data()
    database.migrate_customer_user_data()

    with sqlite3.connect(customer_path) as connection:
        assert connection.execute("SELECT customer_name FROM customers").fetchone()[0] == "Legacy Customer"
        assert connection.execute("SELECT customer_id FROM customer_purchases").fetchone()[0] == "C001"
    with sqlite3.connect(user_path) as connection:
        assert connection.execute("SELECT user_name FROM user_purchases").fetchone()[0] == "Legacy Staff"
    with sqlite3.connect(legacy_path) as connection:
        assert not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='customers'"
        ).fetchone()


def test_migration_does_not_drop_legacy_data_when_destination_is_incomplete(
    tmp_path, monkeypatch
):
    legacy_path = tmp_path / "stocksense.db"
    customer_path = tmp_path / "customers.db"
    user_path = tmp_path / "users.db"
    _create_legacy_database(legacy_path)
    _create_customer_tables(customer_path)
    with sqlite3.connect(user_path) as connection:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")

    monkeypatch.setattr(database, "DB_PATH", str(legacy_path))
    monkeypatch.setattr(database, "CUSTOMER_DB_PATH", str(customer_path))
    monkeypatch.setattr(database, "USER_DB_PATH", str(user_path))

    with pytest.raises(RuntimeError, match="Cannot safely migrate"):
        database.migrate_customer_user_data()

    with sqlite3.connect(legacy_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM user_purchases").fetchone()[0] == 1
