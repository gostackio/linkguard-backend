import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from httpx import Response, Request
from services.link_check_service import LinkCheckService, LinkCheckResult
from services.link_checker import LinkCheckerScheduler
from database.models import Link, User, LinkStatus, Alert, UserNotificationSettings
from sqlalchemy.orm import Session
import ssl
import dns.resolver

@pytest.fixture
def mock_db():
    """Create a mock database session"""
    return Mock(spec=Session)

@pytest.fixture
def mock_email_service():
    """Create a mock email service"""
    return AsyncMock()

@pytest.fixture
def test_user():
    """Create a test user"""
    return User(
        id=1,
        email="test@example.com",
        name="Test User",
        is_active=True
    )

@pytest.fixture
def test_link(test_user):
    """Create a test link"""
    return Link(
        id=1,
        url="https://example.com",
        name="Test Link",
        description="Test Description",
        owner_id=test_user.id,
        owner=test_user,
        is_active=True,
        check_frequency=60
    )

@pytest.fixture
def link_check_service(mock_db):
    """Create a LinkCheckService instance with mocked db"""
    return LinkCheckService(mock_db)

@pytest.mark.asyncio
async def test_validate_domain_success(link_check_service):
    """Test successful domain validation"""
    with patch('dns.resolver.Resolver.resolve') as mock_resolve:
        mock_resolve.return_value = Mock()
        result = await link_check_service._validate_domain("https://example.com")
        assert result is True

@pytest.mark.asyncio
async def test_validate_domain_failure(link_check_service):
    """Test domain validation failure"""
    with patch('dns.resolver.Resolver.resolve') as mock_resolve:
        mock_resolve.side_effect = dns.resolver.NXDOMAIN()
        result = await link_check_service._validate_domain("https://nonexistent.example")
        assert result is False

@pytest.mark.asyncio
async def test_check_ssl_valid(link_check_service):
    """Test SSL certificate validation"""
    with patch('ssl.create_default_context') as mock_context:
        mock_context.return_value = Mock()
        mock_context.return_value.wrap_socket.return_value.__enter__.return_value.getpeercert.return_value = {
            'notAfter': 'Dec 31 23:59:59 2025 GMT',
            'issuer': [(['CN', 'Test CA'],)]
        }
        result = await link_check_service._check_ssl("https://example.com")
        assert result["valid"] is True

@pytest.mark.asyncio
async def test_perform_check_success(link_check_service):
    """Test successful link check"""
    with patch('httpx.AsyncClient.head') as mock_head:
        mock_response = Response(200, request=Request('HEAD', 'https://example.com'))
        mock_head.return_value = mock_response
        
        result = await link_check_service._perform_check("https://example.com")
        assert isinstance(result, LinkCheckResult)
        assert result.success is True
        assert result.status_code == 200

@pytest.mark.asyncio
async def test_perform_check_failure(link_check_service):
    """Test failed link check"""
    with patch('httpx.AsyncClient.head') as mock_head:
        mock_response = Response(404, request=Request('HEAD', 'https://example.com'))
        mock_head.return_value = mock_response
        
        result = await link_check_service._perform_check("https://example.com")
        assert isinstance(result, LinkCheckResult)
        assert result.success is False
        assert result.status_code == 404

@pytest.mark.asyncio
async def test_check_with_retry_and_notification(link_check_service, test_link, mock_db):
    """Test link check with retry and notification"""
    # Mock the notification settings
    mock_settings = Mock(spec=UserNotificationSettings)
    mock_settings.email_enabled = True
    mock_settings.broken_links = True
    mock_db.query.return_value.filter.return_value.first.return_value = mock_settings
    
    with patch('services.link_check_service.LinkCheckService._perform_check') as mock_check:
        mock_check.return_value = LinkCheckResult(
            success=False,
            status_code=404,
            response_time=100,
            error_type="HTTP_ERROR",
            error_message="Not Found"
        )
        
        result = await link_check_service.check_with_retry(test_link)
        assert isinstance(result, LinkStatus)
        assert result.is_available is False
        assert result.status_code == 404
        mock_db.add.assert_called()
        mock_db.commit.assert_called()

@pytest.mark.asyncio
async def test_batch_check_links(link_check_service, test_link):
    """Test batch link checking"""
    links = [test_link] * 3  # Create a batch of 3 identical links
    
    with patch('services.link_check_service.LinkCheckService.check_with_retry') as mock_check:
        mock_check.return_value = Mock(spec=LinkStatus)
        results = await link_check_service.batch_check_links(links, max_concurrent=2)
        assert len(results) == 3
        assert mock_check.call_count == 3

@pytest.mark.asyncio
async def test_scheduler_metrics(mock_db):
    """Test scheduler metrics tracking"""
    scheduler = LinkCheckerScheduler()
    
    # Mock some link check results
    results = [
        LinkStatus(is_available=True, response_time=100),
        LinkStatus(is_available=True, response_time=200),
        LinkStatus(is_available=False, response_time=300)
    ]
    
    scheduler.update_metrics(results)
    health = scheduler.health_check
    
    assert health["total_checks"] == 3
    assert health["successful_checks"] == 2
    assert health["success_rate"] == pytest.approx(0.666, rel=0.01)
    assert health["avg_response_time"] == 200

@pytest.mark.asyncio
async def test_error_handling_and_backoff(link_check_service, test_link):
    """Test error handling and backoff strategy"""
    with patch('services.link_check_service.LinkCheckService._perform_check') as mock_check:
        # Simulate a connection error
        mock_check.side_effect = Exception("Connection failed")
        
        result = await link_check_service.check_with_retry(test_link)
        assert result.is_available is False
        assert result.error_type == "UNKNOWN_ERROR"
        assert "Connection failed" in result.error_message

@pytest.mark.asyncio
async def test_notification_throttling(link_check_service, test_link, mock_db):
    """Test notification throttling for repeated failures"""
    mock_settings = Mock(spec=UserNotificationSettings)
    mock_settings.email_enabled = True
    mock_settings.broken_links = True
    mock_db.query.return_value.filter.return_value.first.return_value = mock_settings
    
    # Simulate multiple failures
    for _ in range(3):
        with patch('services.link_check_service.LinkCheckService._perform_check') as mock_check:
            mock_check.return_value = LinkCheckResult(
                success=False,
                status_code=500,
                response_time=100,
                error_type="SERVER_ERROR",
                error_message="Internal Server Error"
            )
            
            await link_check_service.check_with_retry(test_link)
    
    # Verify that notifications were throttled
    alert_calls = mock_db.add.call_args_list
    alerts = [call[0][0] for call in alert_calls if isinstance(call[0][0], Alert)]
    assert len(alerts) <= 2  # Should be throttled after initial alerts

if __name__ == "__main__":
    pytest.main([__file__, "-v"])