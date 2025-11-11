import os
# Set TESTING mode BEFORE any other imports that depend on environment variables
os.environ["TESTING"] = "1"

import asyncio
import aiosmtpd.controller
from aiohttp import web
import pytest
from typing import Dict, Any, Generator, AsyncGenerator
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.database import Base
from database.models import User, Link, UserNotificationSettings
from auth.auth import get_password_hash
from tests.test_settings import get_test_settings
from datetime import datetime, timezone
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_test_settings()

class TestEnvironment:
    def __init__(self):
        self.smtp_messages = []
        self.http_requests = []
        self.engine = None
        self.SessionLocal = None

    async def start(self):
        """Start all mock services"""
        await self.start_mock_smtp()
        await self.start_mock_http()
        self.setup_database()

    async def stop(self):
        """Stop all mock services"""
        await self.stop_mock_smtp()
        await self.stop_mock_http()
        await self.cleanup_database()

    def setup_database(self):
        """Set up test database"""
        self.engine = create_engine(settings.DATABASE_URL)
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    async def cleanup_database(self):
        """Clean up test database"""
        Base.metadata.drop_all(bind=self.engine)

    async def start_mock_smtp(self):
        """Start mock SMTP server"""
        class Handler:
            async def handle_RCPT(self2, server, session, envelope, address, rcpt_options):
                envelope.rcpt_tos.append(address)
                return '250 OK'

            async def handle_DATA(self2, server, session, envelope):
                self.smtp_messages.append({
                    'from': envelope.mail_from,
                    'to': envelope.rcpt_tos,
                    'content': envelope.content.decode('utf8')
                })
                return '250 Message accepted for delivery'

        self.smtp_controller = aiosmtpd.controller.Controller(
            Handler(),
            hostname=settings.MOCK_SERVICES['smtp']['host'],
            port=settings.MOCK_SERVICES['smtp']['port']
        )
        self.smtp_controller.start()

    async def stop_mock_smtp(self):
        """Stop mock SMTP server"""
        if hasattr(self, 'smtp_controller'):
            self.smtp_controller.stop()

    async def start_mock_http(self):
        """Start mock HTTP server for simulating external URLs"""
        routes = web.RouteTableDef()

        @routes.get('/')
        async def handle_root(request):
            return web.Response(text="Mock Server")

        @routes.get('/success')
        async def handle_success(request):
            return web.Response(text="Success")

        @routes.get('/error')
        async def handle_error(request):
            return web.Response(status=500, text="Server Error")

        @routes.get('/slow')
        async def handle_slow(request):
            await asyncio.sleep(5)
            return web.Response(text="Slow Response")

        @routes.get('/not-found')
        async def handle_not_found(request):
            return web.Response(status=404, text="Not Found")

        app = web.Application()
        app.add_routes(routes)
        
        self.http_runner = web.AppRunner(app)
        await self.http_runner.setup()
        self.http_site = web.TCPSite(
            self.http_runner,
            settings.MOCK_SERVICES['http']['host'],
            settings.MOCK_SERVICES['http']['port']
        )
        await self.http_site.start()

    async def stop_mock_http(self):
        """Stop mock HTTP server"""
        if hasattr(self, 'http_runner'):
            await self.http_runner.cleanup()

    async def create_test_user(self, user_type: str = "normal_user") -> User:
        """Create a test user"""
        user_data = settings.TEST_USERS[user_type]
        db = self.SessionLocal()
        
        try:
            user = User(
                email=user_data["email"],
                hashed_password=get_password_hash(user_data["password"]),
                name=user_data["name"],
                is_active=True,
                created_at=datetime.now(timezone.utc)
            )
            db.add(user)
            db.flush()

            # Create notification settings
            notification_settings = UserNotificationSettings(
                user_id=user.id,
                email_enabled=True,
                broken_links=True,
                status_changes=True,
                weekly_report=True
            )
            db.add(notification_settings)
            
            db.commit()
            db.refresh(user)
            return user
        finally:
            db.close()

    async def create_test_links(self, user: User, link_type: str = "valid") -> list[Link]:
        """Create test links for a user"""
        db = self.SessionLocal()
        created_links = []
        
        try:
            for link_data in settings.TEST_LINKS[link_type]:
                link = Link(
                    url=link_data["url"],
                    name=link_data["name"],
                    description=link_data["description"],
                    owner_id=user.id,
                    created_at=datetime.now(timezone.utc),
                    check_frequency=60
                )
                db.add(link)
                created_links.append(link)
            
            db.commit()
            for link in created_links:
                db.refresh(link)
            
            return created_links
        finally:
            db.close()

    def get_smtp_messages(self) -> list[Dict[str, Any]]:
        """Get captured SMTP messages"""
        return self.smtp_messages

    def clear_smtp_messages(self):
        """Clear captured SMTP messages"""
        self.smtp_messages = []

@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an event loop for the test session"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def test_env(event_loop) -> AsyncGenerator[TestEnvironment, None]:
    """Create and manage test environment"""
    env = TestEnvironment()
    await env.start()
    yield env
    await env.stop()

@pytest.fixture(scope="function")
async def test_user(test_env: TestEnvironment) -> AsyncGenerator[User, None]:
    """Create a test user for each test - clears database before each test"""
    # Clear ALL data before each test to ensure isolation
    from database.models import Link, Alert, LinkStatus, UserNotificationSettings
    
    db = test_env.SessionLocal()
    try:
        # Delete in correct order (respecting foreign keys)
        db.query(LinkStatus).delete()
        db.query(Alert).delete()
        db.query(Link).delete()
        db.query(UserNotificationSettings).delete()
        db.query(User).delete()
        db.commit()
    except Exception as e:
        logger.warning(f"Could not clear database: {e}")
        db.rollback()
    finally:
        db.close()
    
    # Now create a fresh test user
    user = await test_env.create_test_user()
    yield user

@pytest.fixture(scope="function")
async def test_links(test_env: TestEnvironment, test_user: User) -> AsyncGenerator[list[Link], None]:
    """Create test links for each test"""
    links = await test_env.create_test_links(test_user)
    yield links


@pytest.fixture(scope="function")
async def test_user_token(test_user: User) -> str:
    """Create a JWT token for test user - expects test_user fixture"""
    from auth.auth import create_access_token
    # test_user is passed in as a parameter, so it's already resolved
    return create_access_token({"sub": test_user.email})


@pytest.fixture(scope="function")
async def test_client(test_env: TestEnvironment):
    """Create an async HTTP client for testing"""
    from httpx import AsyncClient, ASGITransport
    from main import app
    from database.database import get_db
    
    # Override get_db dependency to use test database
    def override_get_db():
        db = test_env.SessionLocal()
        try:
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    
    # Clean up
    app.dependency_overrides.clear()
