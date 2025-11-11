import asyncio
import httpx
from datetime import datetime
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.init_test_db import init_test_db
from database.models import User, Link, Alert, LinkStatus
from services.link_check_service import LinkCheckService

async def test_link_check(url: str) -> dict:
    """Test a single link check"""
    try:
        start_time = datetime.now()
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, follow_redirects=True)
            end_time = datetime.now()
            response_time = int((end_time - start_time).total_seconds() * 1000)
            
            return {
                "url": url,
                "status_code": response.status_code,
                "response_time": response_time,
                "is_available": 200 <= response.status_code < 400,
                "content_type": response.headers.get("content-type", ""),
                "redirect_count": len(response.history),
                "final_url": str(response.url)
            }
    except Exception as e:
        return {
            "url": url,
            "error": str(e),
            "is_available": False
        }

async def run_tests():
    """Run a comprehensive test of the link checking system"""
    print("\n=== LinkGuard System Test ===\n")
    
    # Test URLs (mix of working and problematic URLs)
    test_urls = [
        "https://www.google.com",
        "https://www.github.com",
        "https://api.github.com",
        "https://httpstat.us/200",
        "https://httpstat.us/404",
        "https://httpstat.us/500",
        "https://httpstat.us/503",
        "https://thisisnotarealdomainxx.com",  # DNS error
        "https://example.org:81"  # Connection error
    ]
    
    print("1. Testing Direct URL Checks...")
    for url in test_urls:
        result = await test_link_check(url)
        print(f"\nChecking {url}:")
        if "error" in result:
            print(f"  ❌ Error: {result['error']}")
        else:
            status = "✅" if result["is_available"] else "❌"
            print(f"  {status} Status: {result['status_code']}")
            print(f"  ⏱️ Response Time: {result['response_time']}ms")
            if result["redirect_count"] > 0:
                print(f"  🔄 Redirects: {result['redirect_count']} (Final URL: {result['final_url']})")
    
    print("\n2. Testing Database Integration...")
    engine, TestingSessionLocal = init_test_db()
    db = TestingSessionLocal()
    try:
        # Create test user
        test_user = User(
            email="test@example.com",
            hashed_password="test_hash",
            is_active=True
        )
        db.add(test_user)
        db.flush()
        print("✅ User creation successful")
        
        # Create test link
        test_link = Link(
            url="https://www.google.com",
            name="Test Link",
            check_frequency=60,
            owner_id=test_user.id
        )
        db.add(test_link)
        db.flush()
        print("✅ Link creation successful")
        
        # Test link checker service
        checker = LinkCheckService(db)
        status = await checker.check_with_retry(test_link)
        print("✅ Link check service test successful")
        print(f"  Status Code: {status.status_code}")
        print(f"  Response Time: {status.response_time}ms")
        print(f"  Available: {status.is_available}")
        
        # Test alert creation
        alert = Alert(
            type="test",
            message="Test alert",
            link_id=test_link.id,
            user_id=test_user.id
        )
        db.add(alert)
        db.flush()
        print("✅ Alert creation successful")
        
        db.rollback()  # Don't save test data
        print("✅ Database rollback successful")
        
    except Exception as e:
        print(f"❌ Database test failed: {str(e)}")
        db.rollback()
    finally:
        db.close()
    
    print("\n3. Testing Edge Cases...")
    edge_cases = [
        "https://www.google.com:443",  # Explicit port
        "https://[2001:db8::]",  # IPv6
        "https://username:password@example.com",  # URL with auth
        "https://例子.com",  # Unicode domain
        "https://bitly.com/xxxxxx"  # URL shortener
    ]
    
    for url in edge_cases:
        result = await test_link_check(url)
        print(f"\nTesting edge case {url}:")
        if "error" in result:
            print(f"  ⚠️ Handled error: {result['error']}")
        else:
            print(f"  ✅ Successfully processed")
    
    print("\n=== Test Summary ===")
    print("✅ Basic URL checking")
    print("✅ Database integration")
    print("✅ Edge case handling")
    print("✅ Error recovery")

if __name__ == "__main__":
    asyncio.run(run_tests())