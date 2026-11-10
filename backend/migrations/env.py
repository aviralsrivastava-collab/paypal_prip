from logging.config import fileConfig
from typing import Any

import sqlalchemy as sa
from alembic import context
from alembic.ddl.impl import DefaultImpl
from sqlalchemy import engine_from_config, pool

import backend.models  # noqa: F401
from backend.core.config import get_settings
from backend.core.database import Base, normalize_database_url


def _custom_version_table_impl(
    self: Any,
    *,
    version_table: str,
    version_table_schema: str | None,
    version_table_pk: bool,
    **kw: Any,
) -> sa.Table:
    """Generate Alembic version table with sufficient length for descriptive revision IDs."""
    vt = sa.Table(
        version_table,
        sa.MetaData(),
        sa.Column("version_num", sa.String(128), nullable=False),
        schema=version_table_schema,
    )
    if version_table_pk:
        vt.append_constraint(
            sa.PrimaryKeyConstraint("version_num", name=f"{version_table}_pkc")
        )
    return vt


DefaultImpl.version_table_impl = _custom_version_table_impl

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

settings = get_settings()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    raw_url = config.get_main_option("sqlalchemy.url") or settings.database_url
    url = normalize_database_url(raw_url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_num_length=128,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section, {})
    raw_url = config.get_main_option("sqlalchemy.url") or settings.database_url
    url = normalize_database_url(raw_url)
    configuration["sqlalchemy.url"] = url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(
                sa.text(
                    "DO $$ BEGIN "
                    "IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'alembic_version') THEN "
                    "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128); "
                    "END IF; "
                    "END $$;"
                )
            )
            connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_num_length=128,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
