import os
import tempfile

# Isolated DB, no Telegram, no real admin token — must be set before any app import
_tmp = tempfile.mkdtemp(prefix="macrosniper-test-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp}/test.db"
os.environ["DATA_DIR"] = _tmp
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_CHANNEL_ID"] = ""
os.environ["ADMIN_API_TOKEN"] = "test-admin-token"
os.environ["FMP_API_KEY"] = ""
os.environ["TELEGRAM_ADMIN_IDS"] = ""

import pytest  # noqa: E402

from app.core.db import Base, engine, init_db  # noqa: E402


@pytest.fixture(autouse=True)
async def fresh_db():
    await init_db()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
