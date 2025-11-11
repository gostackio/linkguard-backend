import asyncio
from httpx import AsyncClient, ASGITransport
from main import app
from auth.auth import create_access_token
import os

# Ensure test mode
os.environ.setdefault('TESTING', '1')

async def main():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        # Use the test user email from tests/test_settings
        token = create_access_token({"sub": "test@example.com"})
        headers = {"Authorization": f"Bearer {token}"}
        link = {"url": "https://www.github.com", "name": "GitHub", "description": "desc", "check_frequency": 60}
        resp = await client.post('/api/links', json=link, headers=headers)
        print('STATUS', resp.status_code)
        try:
            print('JSON:', resp.json())
        except Exception:
            print('TEXT:', resp.text)

if __name__ == '__main__':
    asyncio.run(main())
