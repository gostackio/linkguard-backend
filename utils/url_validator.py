from typing import Optional
from pydantic import BaseModel, HttpUrl, validator
from urllib.parse import urlparse
import re

class URLValidator:
    @staticmethod
    def is_valid_url(url: str) -> bool:
        """
        Validate if a URL is properly formatted and uses supported protocols
        """
        try:
            result = urlparse(url)
            return all([result.scheme in ['http', 'https'], result.netloc])
        except:
            return False

    @staticmethod
    def is_valid_domain(domain: str) -> bool:
        """
        Validate if a domain name is properly formatted
        """
        domain_pattern = re.compile(
            r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
        )
        return bool(domain_pattern.match(domain))

    @staticmethod
    def normalize_url(url: str) -> str:
        """
        Normalize a URL by adding https:// if no scheme is provided
        """
        if not url.startswith(('http://', 'https://')):
            return f'https://{url}'
        return url

    @staticmethod
    def sanitize_url(url: str) -> str:
        """
        Sanitize a URL by removing potentially dangerous characters
        """
        # Remove whitespace
        url = url.strip()
        
        # Remove any unsafe characters
        url = re.sub(r'[<>"\'\\]', '', url)
        
        # Ensure proper scheme
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}'
        
        return url

    @staticmethod
    def extract_domain(url: str) -> Optional[str]:
        """
        Extract domain from URL
        """
        try:
            parsed = urlparse(url)
            return parsed.netloc
        except:
            return None

    @staticmethod
    def is_ip_address(domain: str) -> bool:
        """
        Check if the domain is an IP address
        """
        ip_pattern = re.compile(
            r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
            r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
        )
        return bool(ip_pattern.match(domain))

class ValidatedURL(BaseModel):
    url: HttpUrl
    
    @validator('url')
    def validate_url(cls, v):
        # Convert to string for additional validation
        url_str = str(v)
        
        # Check for IP addresses (optional: block them if needed)
        domain = URLValidator.extract_domain(url_str)
        if domain and URLValidator.is_ip_address(domain):
            raise ValueError("IP addresses are not allowed")
        
        # Additional custom validation can be added here
        return v

    class Config:
        json_encoders = {
            HttpUrl: str
        }