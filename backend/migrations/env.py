from alembic import context
from sqlalchemy import create_engine

from app import models  # noqa: F401
from app.core.config import get_settings
from app.db import Base

target_metadata = Base.metadata


def run() -> None:
    url = context.get_x_argument(as_dictionary=True).get("url") or get_settings().database_url
    engine = create_engine(url)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run()
