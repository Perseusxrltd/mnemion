"""Bounded cleanup of expired authentication material on an active API host."""

import logging

import anyio
import psycopg
from psycopg_pool import PoolTimeout

logger = logging.getLogger(__name__)


def prune_history(database):
    with database.pool.connection(timeout=3) as conn:
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='2s'")
            return conn.execute("SELECT * FROM mnemion.prune_sign_in_history()").fetchone()


async def maintain_history(database):
    while True:
        try:
            # Cancellation waits for the bounded query before the pool closes.
            await anyio.to_thread.run_sync(prune_history, database)
        except (psycopg.Error, PoolTimeout) as error:
            # Never put database connection strings or authentication rows in logs.
            logger.warning("Sign-in history cleanup deferred (%s)", type(error).__name__)
        await anyio.sleep(60)
