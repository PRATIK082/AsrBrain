"""Unit tests for the registry migration runner (ADR-0003).

Migrations must be ordered, idempotent, transactional and tamper-evident: an
already-applied migration whose content changed is an error, not a silent
re-run.
"""
import pytest

from src.registry.migrator import (
    MigrationError,
    apply_migrations,
    current_version,
    migration_files,
)


def test_migration_files_are_ordered(tmp_path):
    for i, name in enumerate(["010_c.sql", "002_b.sql", "001_a.sql"], start=1):
        (tmp_path / name).write_text("SELECT 1;\n", encoding="utf-8")
    assert [p.name for p in migration_files(tmp_path)] == [
        "001_a.sql", "002_b.sql", "010_c.sql"]


def test_apply_migrations_creates_the_schema_and_records_versions(tmp_path):
    db = tmp_path / "registry.db"
    applied = apply_migrations(str(db))
    assert applied, "at least the shipped migrations must be applied"
    assert current_version(str(db)) == max(applied)
    assert applied == sorted(applied), "migrations must be applied in order"


def test_apply_migrations_is_idempotent(tmp_path):
    db = str(tmp_path / "registry.db")
    first = apply_migrations(db)
    version = current_version(db)
    second = apply_migrations(db)
    assert second == [], "an already-migrated database must not re-apply anything"
    assert current_version(db) == version
    assert first


def test_apply_migrations_creates_the_parent_directory(tmp_path):
    db = tmp_path / "nested" / "deeper" / "registry.db"
    apply_migrations(str(db))
    assert db.exists()


def test_editing_an_applied_migration_is_rejected(tmp_path):
    migrations = tmp_path / "m"
    migrations.mkdir()
    (migrations / "001_a.sql").write_text("CREATE TABLE a(id TEXT);\n", encoding="utf-8")
    db = str(tmp_path / "registry.db")
    apply_migrations(db, directory=migrations)
    # Tamper with the applied migration.
    (migrations / "001_a.sql").write_text("CREATE TABLE a(id TEXT, x TEXT);\n",
                                           encoding="utf-8")
    with pytest.raises(MigrationError):
        apply_migrations(db, directory=migrations)


def test_current_version_is_zero_for_an_unknown_database(tmp_path):
    assert current_version(str(tmp_path / "missing.db")) == 0


def test_shipped_migrations_cover_the_registry_spine(tmp_path):
    db = str(tmp_path / "registry.db")
    apply_migrations(db)
    import sqlite3
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    for required in ("projects", "workspaces", "artifacts", "artifact_versions",
                     "source_locations", "citations", "evidence_claims",
                     "validation_results", "jobs", "answer_audits", "schema_version"):
        assert required in tables, f"missing table: {required}"
