from alembic import context
from sqlalchemy import engine_from_config,pool
from app.models import Base
from app.config import get_settings
config=context.config;config.set_main_option("sqlalchemy.url",get_settings().database_url);target_metadata=Base.metadata
def offline():
 context.configure(url=config.get_main_option("sqlalchemy.url"),target_metadata=target_metadata,literal_binds=True,dialect_opts={"paramstyle":"named"});
 with context.begin_transaction():context.run_migrations()
def online():
 connectable=engine_from_config(config.get_section(config.config_ini_section),prefix="sqlalchemy.",poolclass=pool.NullPool)
 with connectable.connect() as connection:
  context.configure(connection=connection,target_metadata=target_metadata)
  with context.begin_transaction():context.run_migrations()
offline() if context.is_offline_mode() else online()
