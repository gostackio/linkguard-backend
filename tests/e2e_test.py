import asyncio
import httpx
import json
import os
from datetime import datetime
import sys
from typing import Dict, List, Optional
import logging
import uuid
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LinkGuardTestAgent:
    def __init__(self):
        self.base_url = "http://localhost:8000"  # Backend URL
        self.frontend_url = "http://localhost:5173"  # Frontend URL
        self.client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        self.access_token = None
        self.test_user = {
            "email": f"tester_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Test@123!",
            "name": "Test User"
        }
        self.test_links = [
            {
                "url": "https://www.github.com",
                "name": "GitHub",
                "description": "Code hosting platform"
            },
            {
                "url": "https://www.python.org",
                "name": "Python",
                "description": "Python programming language"
            },
            {
                "url": "https://notarealwebsite.com",  # Should fail
                "name": "Invalid Site",
                "description": "Testing error handling"
            }
        ]

    async def run_tests(self):
        """Run all tests in sequence"""
        try:
            logger.info("Starting end-to-end tests...")
            
            # Authentication tests
            await self.test_signup()
            await self.test_login()
            await self.test_get_me()
            await self.test_forgot_password()
            
            # Link management tests
            created_links = await self.test_create_links()
            await self.test_get_links()
            await self.test_check_links(created_links)
            await self.test_update_link(created_links[0])
            await self.test_delete_link(created_links[-1])
            
            # Alert management tests
            await self.test_get_alerts()
            await self.test_alert_settings()
            
            # Bulk operations test
            await self.test_bulk_upload()
            
            # Admin functionality tests
            await self.test_admin_dashboard()
            await self.test_admin_failed_checks()
            
            logger.info("All tests completed successfully!")
            return True
            
        except Exception as e:
            logger.error(f"Test suite failed: {str(e)}")
            return False
        finally:
            await self.client.aclose()

    async def test_signup(self):
        """Test user registration"""
        logger.info(f"Testing signup with email: {self.test_user['email']}")
        response = await self.client.post(
            f"{self.base_url}/api/auth/signup",
            json=self.test_user
        )
        
        assert response.status_code == 200, f"Signup failed: {response.text}"
        data = response.json()
        assert data["success"] is True
        assert "token" in data
        assert "user" in data
        self.access_token = data["token"]
        logger.info("✓ Signup test passed")

    async def test_login(self):
        """Test user login"""
        logger.info("Testing login")
        response = await self.client.post(
            f"{self.base_url}/api/auth/login",
            data={
                "username": self.test_user["email"],
                "password": self.test_user["password"]
            }
        )
        
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        self.access_token = data["access_token"]
        logger.info("✓ Login test passed")

    async def test_get_me(self):
        """Test getting current user info"""
        logger.info("Testing get current user")
        response = await self.client.get(
            f"{self.base_url}/api/auth/me",
            headers={"Authorization": f"Bearer {self.access_token}"}
        )
        
        assert response.status_code == 200, f"Get me failed: {response.text}"
        data = response.json()
        assert data["email"] == self.test_user["email"]
        logger.info("✓ Get current user test passed")

    async def test_forgot_password(self):
        """Test password reset functionality"""
        logger.info("Testing forgot password")
        response = await self.client.post(
            f"{self.base_url}/api/auth/forgot-password",
            json={"email": self.test_user["email"]}
        )
        
        assert response.status_code == 200, f"Forgot password failed: {response.text}"
        logger.info("✓ Forgot password test passed")

    async def test_create_links(self) -> List[Dict]:
        """Test creating links"""
        logger.info("Testing link creation")
        created_links = []
        
        for link_data in self.test_links:
            response = await self.client.post(
                f"{self.base_url}/api/links",
                json=link_data,
                headers={"Authorization": f"Bearer {self.access_token}"}
            )
            
            assert response.status_code == 200, f"Create link failed: {response.text}"
            created_links.append(response.json())
            
        logger.info(f"✓ Created {len(created_links)} links successfully")
        return created_links

    async def test_get_links(self):
        """Test retrieving links"""
        logger.info("Testing get links")
        response = await self.client.get(
            f"{self.base_url}/api/links",
            headers={"Authorization": f"Bearer {self.access_token}"}
        )
        
        assert response.status_code == 200, f"Get links failed: {response.text}"
        links = response.json()
        assert len(links) >= len(self.test_links)
        logger.info("✓ Get links test passed")

    async def test_check_links(self, links: List[Dict]):
        """Test link checking functionality"""
        logger.info("Testing link checks")
        for link in links:
            response = await self.client.post(
                f"{self.base_url}/api/links/{link['id']}/check",
                headers={"Authorization": f"Bearer {self.access_token}"}
            )
            
            assert response.status_code == 200, f"Check link failed: {response.text}"
            status = response.json()
            logger.info(f"Link {link['url']} status: {'✓ Healthy' if status['is_available'] else '✗ Unhealthy'}")
            
            # Give the server time to process any notifications
            await asyncio.sleep(1)

    async def test_update_link(self, link: Dict):
        """Test updating a link"""
        logger.info("Testing link update")
        update_data = {
            "name": f"{link['name']} Updated",
            "description": f"{link['description']} - Updated"
        }
        
        response = await self.client.put(
            f"{self.base_url}/api/links/{link['id']}",
            json=update_data,
            headers={"Authorization": f"Bearer {self.access_token}"}
        )
        
        assert response.status_code == 200, f"Update link failed: {response.text}"
        updated_link = response.json()
        assert updated_link["name"] == update_data["name"]
        logger.info("✓ Update link test passed")

    async def test_delete_link(self, link: Dict):
        """Test deleting a link"""
        logger.info("Testing link deletion")
        response = await self.client.delete(
            f"{self.base_url}/api/links/{link['id']}",
            headers={"Authorization": f"Bearer {self.access_token}"}
        )
        
        assert response.status_code == 200, f"Delete link failed: {response.text}"
        logger.info("✓ Delete link test passed")

    async def test_get_alerts(self):
        """Test retrieving alerts"""
        logger.info("Testing get alerts")
        response = await self.client.get(
            f"{self.base_url}/api/alerts",
            headers={"Authorization": f"Bearer {self.access_token}"}
        )
        
        assert response.status_code == 200, f"Get alerts failed: {response.text}"
        alerts = response.json()
        logger.info(f"Found {len(alerts)} alerts")
        
        # Test marking alerts as read
        if alerts:
            response = await self.client.put(
                f"{self.base_url}/api/alerts/read-all",
                headers={"Authorization": f"Bearer {self.access_token}"}
            )
            assert response.status_code == 200
            logger.info("✓ Mark all alerts read test passed")

    async def test_alert_settings(self):
        """Test alert settings management"""
        logger.info("Testing alert settings")
        settings = {
            "email_notifications": True,
            "broken_links": True,
            "status_changes": True,
            "weekly_report": True
        }
        
        response = await self.client.put(
            f"{self.base_url}/api/alerts/settings",
            json=settings,
            headers={"Authorization": f"Bearer {self.access_token}"}
        )
        
        assert response.status_code == 200, f"Update alert settings failed: {response.text}"
        logger.info("✓ Alert settings test passed")

    async def test_bulk_upload(self):
        """Test bulk link upload"""
        logger.info("Testing bulk upload")
        # Create a test CSV file
        csv_content = "url,name,description\n"
        csv_content += "https://www.google.com,Google,Search Engine\n"
        csv_content += "https://www.microsoft.com,Microsoft,Technology Company"
        
        files = {
            'file': ('test.csv', csv_content, 'text/csv')
        }
        
        response = await self.client.post(
            f"{self.base_url}/api/links/bulk-upload",
            files=files,
            headers={"Authorization": f"Bearer {self.access_token}"}
        )
        
        assert response.status_code == 200, f"Bulk upload failed: {response.text}"
        result = response.json()
        assert result["success"] > 0
        logger.info(f"✓ Bulk upload test passed: {result['success']} links created")

    async def test_admin_dashboard(self):
        """Test admin dashboard"""
        logger.info("Testing admin dashboard")
        response = await self.client.get(
            f"{self.base_url}/api/admin/dashboard",
            headers={"Authorization": f"Bearer {self.access_token}"}
        )
        
        if response.status_code == 200:
            data = response.json()
            logger.info("Admin Dashboard Stats:")
            logger.info(f"- Total Links: {data['link_check_stats']['total_checks']}")
            logger.info(f"- Success Rate: {data['link_check_stats']['successful_checks']}/{data['link_check_stats']['total_checks']}")
            logger.info(f"- Active Users: {data['user_stats']['active_users']}")
        else:
            logger.warning("Admin dashboard access denied (expected if not admin)")

    async def test_admin_failed_checks(self):
        """Test failed checks monitoring"""
        logger.info("Testing failed checks monitoring")
        response = await self.client.get(
            f"{self.base_url}/api/admin/failed-checks",
            headers={"Authorization": f"Bearer {self.access_token}"}
        )
        
        if response.status_code == 200:
            failed_checks = response.json()
            logger.info(f"Found {len(failed_checks)} failed checks")
        else:
            logger.warning("Failed checks access denied (expected if not admin)")

async def main():
    agent = LinkGuardTestAgent()
    await agent.run_tests()

if __name__ == "__main__":
    asyncio.run(main())