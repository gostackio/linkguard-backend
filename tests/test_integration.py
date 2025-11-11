import pytest
import asyncio
import os
import tempfile
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy.orm import Session

from main import app
from database.models import User, Link, LinkStatus, Alert, UserNotificationSettings
from database.database import Base, engine, get_db, SessionLocal
from auth.auth import create_access_token, get_password_hash

# Configure pytest-asyncio
pytestmark = pytest.mark.asyncio

# Test configuration
TEST_USER = {
    "email": "test@example.com",
    "password": "TestPass123!",
    "name": "Test User"
}



@pytest.mark.asyncio
async def test_user_registration_and_login(test_client, test_env):
    """Test user registration and authentication flow"""
    # Test registration
    registration_data = {
        "email": "newuser@test.com",
        "password": "TestPassword123!",
        "name": "Test User"
    }
    
    response = await test_client.post("/api/auth/signup", json=registration_data)
    assert response.status_code in [200, 201], f"Signup failed: {response.text}"
    data = response.json()
    
    # Verify response has required fields
    assert "id" in data or "access_token" in data, f"Invalid signup response: {data}"
    if "email" in data:
        assert data["email"] == registration_data["email"]
    
    # Check welcome email was sent
    messages = test_env.get_smtp_messages()
    assert len(messages) > 0, "No emails captured"
    latest_message = messages[-1]
    assert registration_data["email"] in latest_message["to"]
    
    # Test login
    login_data = {
        "username": registration_data["email"],
        "password": registration_data["password"]
    }
    
    response = await test_client.post("/api/auth/login", data=login_data)
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    assert "access_token" in data, "No access token in response"


@pytest.mark.asyncio
async def test_create_link(test_client, test_user_token):
    """Test link creation"""
    headers = {"Authorization": f"Bearer {test_user_token}"}
    
    link_data = {
        "url": "https://github.com/test1",
        "name": "GitHub",
        "description": "Code hosting platform",
        "check_frequency": 60
    }
    
    response = await test_client.post(
        "/api/links",
        json=link_data,
        headers=headers
    )
    
    assert response.status_code in [200, 201], f"Failed to create link: {response.text}"
    data = response.json()
    # URL might be normalized, so check it contains the domain
    assert "github.com" in data["url"], f"URL mismatch: {data['url']}"
    assert data["name"] == link_data["name"], f"Name mismatch: {data}"
    assert "id" in data, "No link ID"


@pytest.mark.asyncio
async def test_get_links(test_client, test_user_token):
    """Test retrieving user's links"""
    headers = {"Authorization": f"Bearer {test_user_token}"}
    
    # Create a link first with unique URL
    link_data = {
        "url": "https://python.org/test2",
        "name": "Python",
        "description": "Python programming",
        "check_frequency": 60
    }
    
    create_response = await test_client.post("/api/links", json=link_data, headers=headers)
    assert create_response.status_code in [200, 201], f"Failed to create link: {create_response.text}"
    
    # Retrieve links
    response = await test_client.get("/api/links", headers=headers)
    assert response.status_code == 200, f"Failed to get links: {response.text}"
    
    links = response.json()
    assert isinstance(links, list), f"Links should be a list"
    assert len(links) > 0, "No links returned"


@pytest.mark.asyncio
async def test_update_link(test_client, test_user_token):
    """Test link updating"""
    headers = {"Authorization": f"Bearer {test_user_token}"}
    
    # Create a link with unique URL
    link_data = {
        "url": "https://example.com/test3",
        "name": "Example",
        "description": "Example site",
        "check_frequency": 60
    }
    
    create_response = await test_client.post("/api/links", json=link_data, headers=headers)
    assert create_response.status_code in [200, 201], f"Failed to create link: {create_response.text}"
    created_link = create_response.json()
    link_id = created_link["id"]
    
    # Update the link
    update_data = {
        "name": "Example Updated",
        "description": "Example site - Updated",
        "check_frequency": 120
    }
    
    response = await test_client.put(
        f"/api/links/{link_id}",
        json=update_data,
        headers=headers
    )
    
    assert response.status_code == 200, f"Failed to update link: {response.text}"
    updated = response.json()
    assert updated["name"] == update_data["name"], f"Name not updated"


@pytest.mark.asyncio
async def test_delete_link(test_client, test_user_token):
    """Test link deletion"""
    headers = {"Authorization": f"Bearer {test_user_token}"}
    
    # Create a unique link
    link_data = {
        "url": "https://deleteme.com/test4",
        "name": "Delete Me",
        "description": "To be deleted",
        "check_frequency": 60
    }
    
    create_response = await test_client.post("/api/links", json=link_data, headers=headers)
    assert create_response.status_code in [200, 201], f"Failed to create link: {create_response.text}"
    created_link = create_response.json()
    link_id = created_link["id"]
    
    # Delete the link
    response = await test_client.delete(
        f"/api/links/{link_id}",
        headers=headers
    )
    
    assert response.status_code in [200, 204], f"Failed to delete link: {response.text}"
    
    # Verify it's deleted
    get_response = await test_client.get(
        f"/api/links/{link_id}",
        headers=headers
    )
    assert get_response.status_code == 404, "Link still exists after deletion"


@pytest.mark.asyncio
async def test_alert_settings(test_client, test_user_token):
    """Test alert settings management"""
    headers = {"Authorization": f"Bearer {test_user_token}"}
    
    settings = {
        "email_enabled": True,
        "broken_links": True,
        "status_changes": True,
        "weekly_report": False
    }
    
    response = await test_client.put(
        "/api/alerts/settings",
        json=settings,
        headers=headers
    )
    
    assert response.status_code == 200, f"Failed to update settings: {response.text}"
    data = response.json()
    assert data is not None


@pytest.mark.asyncio
async def test_bulk_upload(test_client, test_user_token):
    """Test bulk link upload"""
    headers = {"Authorization": f"Bearer {test_user_token}"}
    
    # Create test CSV content
    csv_content = "url,name,description\n"
    csv_content += "https://www.google.com,Google,Search Engine\n"
    csv_content += "https://www.microsoft.com,Microsoft,Technology Company"
    
    # Create temporary CSV file
    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False, mode='w') as temp:
        temp.write(csv_content)
        temp_path = temp.name
    
    try:
        with open(temp_path, 'rb') as f:
            response = await test_client.post(
                "/api/links/bulk-upload",
                headers=headers,
                files={"file": ("test.csv", f, "text/csv")}
            )
        
        # Accept different success status codes
        assert response.status_code in [200, 201], f"Bulk upload failed: {response.text}"
        result = response.json()
        assert result is not None
            
    finally:
        os.unlink(temp_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])