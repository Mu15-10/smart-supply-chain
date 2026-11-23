import os
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command


@pytest.mark.postgres
@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires a real PostgreSQL TEST_DATABASE_URL")
def test_migration_round_trip():
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    url = os.environ["TEST_DATABASE_URL"]
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    config.attributes["database_url"] = url
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
