from alembic import context
from sqlalchemy import MetaData, text

from app.bootstrap import build_container
from app.platform.database import SCHEMAS, Base
from app.platform.settings import Settings

container = build_container(Settings())
with container.db.engine.connect() as connection:
    postgres = connection.dialect.name == "postgresql"
    if postgres:
        for schema in SCHEMAS:
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        connection.commit()
    metadata = Base.metadata
    if not postgres:
        metadata = MetaData(naming_convention=Base.metadata.naming_convention)
        for table in Base.metadata.sorted_tables:
            table.to_metadata(metadata, schema=None)
    context.configure(
        connection=connection,
        target_metadata=metadata,
        include_schemas=postgres,
        version_table_schema="platform" if postgres else None,
    )
    with context.begin_transaction():
        context.run_migrations()
