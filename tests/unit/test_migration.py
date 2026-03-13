"""Tests for Alembic migration — validates migration script is importable and valid."""

import importlib
import importlib.util
from pathlib import Path


class TestMigration:
    def test_initial_migration_importable(self) -> None:
        migration_path = Path(__file__).parents[2] / "alembic" / "versions" / "001_initial_schema.py"
        spec = importlib.util.spec_from_file_location("migration_001", migration_path)
        assert spec is not None
        assert spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "upgrade")
        assert hasattr(mod, "downgrade")
        assert mod.revision == "001"
        assert mod.down_revision is None
