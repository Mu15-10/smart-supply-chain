import os
import pytest

@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires a real PostgreSQL TEST_DATABASE_URL")
def test_migration_round_trip():
    from alembic import command
    from alembic.config import Config
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", os.environ["TEST_DATABASE_URL"])
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
