"""Pytest configuration and fixtures for backend tests."""

import asyncio
import uuid
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.api_key import generate_api_key, hash_api_key
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.models.device import Device
from app.db.models.user import User
from app.db.session import get_db
from app.main import app

# Test database URL (override via TEST_DATABASE_URL env var)
import os

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/dronecds_test",
)


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Create a test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    # Create all tables
    async with engine.begin() as conn:
        # Enable PostGIS
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis_topology"))
        # Drop and recreate all tables
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Clean up
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async_session = sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create a test HTTP client with database session override."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """Create an admin user for testing."""
    user = User(
        email="admin@test.com",
        role="admin",
        password_hash=hash_password("adminpass123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def operator_user(db_session: AsyncSession) -> User:
    """Create an operator user for testing."""
    user = User(
        email="operator@test.com",
        role="operator",
        password_hash=hash_password("operatorpass123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def viewer_user(db_session: AsyncSession) -> User:
    """Create a viewer user for testing."""
    user = User(
        email="viewer@test.com",
        role="viewer",
        password_hash=hash_password("viewerpass123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_token(admin_user: User) -> str:
    """Generate JWT token for admin user."""
    return create_access_token(data={"sub": str(admin_user.id), "email": admin_user.email})


@pytest_asyncio.fixture
async def operator_token(operator_user: User) -> str:
    """Generate JWT token for operator user."""
    return create_access_token(data={"sub": str(operator_user.id), "email": operator_user.email})


@pytest_asyncio.fixture
async def viewer_token(viewer_user: User) -> str:
    """Generate JWT token for viewer user."""
    return create_access_token(data={"sub": str(viewer_user.id), "email": viewer_user.email})


@pytest_asyncio.fixture
async def test_device(db_session: AsyncSession) -> tuple[Device, str]:
    """Create a test device and return it with its plain API key."""
    api_key = generate_api_key()
    device = Device(
        name="Test Drone",
        device_type="drone",
        api_key_hash=hash_api_key(api_key),
        status="offline",
    )
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    return device, api_key


@pytest_asyncio.fixture
async def test_detection_data() -> dict:
    """Sample detection data for testing."""
    return {
        "client_detection_id": str(uuid.uuid4()),
        "latitude": 37.7749,
        "longitude": -122.4194,
        "severity": "high",
        "confidence": 0.95,
        "bbox": {"x1": 100.0, "y1": 100.0, "x2": 200.0, "y2": 200.0},
        "model_version": "v1.0",
        "detected_at": "2026-09-21T10:00:00Z",
        "is_interpolated": False,
    }
