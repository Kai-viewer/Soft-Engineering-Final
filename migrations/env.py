from alembic import context

from app.accounts import models as accounts_models  # noqa: F401
from app.bookings import models as booking_models  # noqa: F401
from app.core.db import Base, database_url, make_engine
from app.scheduling import models as scheduling_models  # noqa: F401
from app.spaces import models as space_models  # noqa: F401

if context.is_offline_mode():
    context.configure(url=database_url(), target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = make_engine()
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
