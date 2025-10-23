"""
Database setup and session management.
Handles SQLAlchemy engine creation and session lifecycle.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.logging_config import get_logger
from app.storage.models import Base

logger = get_logger(__name__)


class Database:
    """Database manager class."""

    def __init__(self, database_url: str, echo: bool = False):
        """
        Initialize database manager.

        Args:
            database_url: Database connection URL
            echo: Whether to echo SQL queries
        """
        self.database_url = database_url
        self.echo = echo

        # For SQLite, use synchronous engine
        if database_url.startswith("sqlite"):
            # Use check_same_thread=False for SQLite to allow multiple threads
            self.engine = create_engine(
                database_url,
                echo=echo,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
            self.async_mode = False
            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine,
            )
        else:
            # For other databases, use async engine
            self.engine = create_async_engine(
                database_url,
                echo=echo,
            )
            self.async_mode = True
            self.SessionLocal = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

        logger.info(f"Database initialized: {database_url} (async={self.async_mode})")

    def create_tables(self):
        """Create all tables in the database."""
        if self.async_mode:
            raise NotImplementedError("Use create_tables_async for async engines")

        Base.metadata.create_all(bind=self.engine)
        logger.info("Database tables created successfully")

    async def create_tables_async(self):
        """Create all tables asynchronously."""
        if not self.async_mode:
            raise NotImplementedError("Use create_tables for sync engines")

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully (async)")

    def drop_tables(self):
        """Drop all tables from the database."""
        if self.async_mode:
            raise NotImplementedError("Use drop_tables_async for async engines")

        Base.metadata.drop_all(bind=self.engine)
        logger.warning("All database tables dropped")

    async def drop_tables_async(self):
        """Drop all tables asynchronously."""
        if not self.async_mode:
            raise NotImplementedError("Use drop_tables for sync engines")

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.warning("All database tables dropped (async)")

    def get_session(self) -> Session:
        """
        Get a database session.
        For synchronous operations only.

        Returns:
            SQLAlchemy Session
        """
        if self.async_mode:
            raise NotImplementedError("Use get_async_session for async engines")

        return self.SessionLocal()

    @asynccontextmanager
    async def get_async_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get an async database session.
        Use as async context manager.

        Yields:
            AsyncSession
        """
        if not self.async_mode:
            raise NotImplementedError("Use get_session for sync engines")

        async with self.SessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    def close(self):
        """Close the database engine."""
        if self.async_mode:
            raise NotImplementedError("Use close_async for async engines")

        self.engine.dispose()
        logger.info("Database connection closed")

    async def close_async(self):
        """Close the async database engine."""
        if not self.async_mode:
            raise NotImplementedError("Use close for sync engines")

        await self.engine.dispose()
        logger.info("Database connection closed (async)")


# Global database instance
_db: Database = None


def get_database(database_url: str = None, echo: bool = False) -> Database:
    """
    Get the global database instance.
    Creates it if it doesn't exist.

    Args:
        database_url: Database URL (required for first call)
        echo: Whether to echo SQL queries

    Returns:
        Database instance
    """
    global _db

    if _db is None:
        if database_url is None:
            raise ValueError("database_url must be provided for first call")
        _db = Database(database_url, echo)

    return _db


def init_database(database_url: str, echo: bool = False, recreate: bool = False):
    """
    Initialize the database and create tables.

    Args:
        database_url: Database connection URL
        echo: Whether to echo SQL queries
        recreate: If True, drop and recreate all tables
    """
    db = get_database(database_url, echo)

    if recreate:
        logger.warning("Recreating database tables...")
        db.drop_tables()

    db.create_tables()
    logger.info("Database initialization complete")


# Dependency for FastAPI
def get_db_session():
    """
    FastAPI dependency to get a database session.
    Use with Depends() in route handlers.

    Yields:
        Database session
    """
    db = get_database()
    session = db.get_session()
    try:
        yield session
    finally:
        session.close()
