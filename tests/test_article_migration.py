"""Exercise the actual additive revision and its rollback on a legacy schema."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_article_revision_upgrades_and_downgrades_with_legacy_rows():
    path = Path(__file__).parents[1] / "alembic/versions/0004_article_evidence_and_stories.py"
    spec = importlib.util.spec_from_file_location("article_revision", path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            sa.text("CREATE TABLE news_items (id VARCHAR PRIMARY KEY, created_at DATETIME)")
        )
        connection.execute(sa.text("INSERT INTO news_items (id) VALUES ('legacy')"))
        revision.op = Operations(MigrationContext.configure(connection))
        revision.upgrade()
        columns = {c["name"] for c in sa.inspect(connection).get_columns("news_items")}
        assert {"story_id", "collection_info"} <= columns
        assert (
            connection.execute(sa.text("SELECT collection_info FROM news_items")).scalar() is None
        )
        revision.downgrade()
        columns = {c["name"] for c in sa.inspect(connection).get_columns("news_items")}
        assert columns == {"id", "created_at"}
        assert connection.execute(sa.text("SELECT id FROM news_items")).scalar() == "legacy"
    engine.dispose()
