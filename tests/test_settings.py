from typing import Dict, Any
import os
from pydantic_settings import BaseSettings
from pydantic import PostgresDsn, EmailStr, HttpUrl, validator
from functools import lru_cache

class TestSettings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite:///D:/Projects/linkguard/backend/test.db"
    
    # Authentication
    SECRET_KEY: str = "test_secret_key"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Email
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 2525
    SMTP_USER: str = "test"
    SMTP_PASSWORD: str = "test"
    FROM_EMAIL: EmailStr = "test@example.com"
    
    # Link Checking
    CHECK_INTERVAL_MINUTES: int = 1
    MAX_CONCURRENT_CHECKS: int = 5
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 5
    CONNECTION_TIMEOUT: int = 10
    
    # Test Data
    TEST_USERS: Dict[str, Dict[str, Any]] = {
        "normal_user": {
            "email": "user@example.com",
            "password": "UserPass123!",
            "name": "Test User"
        },
        "premium_user": {
            "email": "premium@example.com",
            "password": "PremiumPass123!",
            "name": "Premium User"
        }
    }
    
    TEST_LINKS: Dict[str, list[Dict[str, Any]]] = {
        "valid": [
            {
                "url": "https://www.github.com",
                "name": "GitHub",
                "description": "Code hosting platform"
            },
            {
                "url": "https://www.python.org",
                "name": "Python",
                "description": "Python programming language"
            }
        ],
        "invalid": [
            {
                "url": "https://notarealwebsite.example.com",
                "name": "Invalid Site",
                "description": "Testing error handling"
            },
            {
                "url": "https://httpstat.us/500",
                "name": "Server Error",
                "description": "Testing server error handling"
            },
            {
                "url": "https://httpstat.us/404",
                "name": "Not Found",
                "description": "Testing 404 handling"
            }
        ],
        "slow": [
            {
                "url": "https://httpstat.us/200?sleep=5000",
                "name": "Slow Response",
                "description": "Testing timeout handling"
            }
        ]
    }
    
    # Mock Service Settings
    MOCK_SERVICES: Dict[str, Dict[str, Any]] = {
        "smtp": {
            "host": "localhost",
            "port": 2525
        },
        "http": {
            "host": "localhost",
            "port": 8080
        }
    }

    class Config:
        env_prefix = "TEST_"

@lru_cache()
def get_test_settings() -> TestSettings:
    return TestSettings()