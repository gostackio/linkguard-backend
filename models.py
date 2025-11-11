from pydantic import BaseModel, EmailStr, HttpUrl
from typing import Optional, List
from datetime import datetime

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    website: Optional[str] = None

class User(BaseModel):
    id: str
    name: str
    email: str
    website: Optional[str] = None

class Link(BaseModel):
    id: str
    url: HttpUrl
    title: str
    page: str
    status: str
    lastChecked: str
    clicks: int = 0
    revenue: float = 0.0
    userId: str

class LinkCreate(BaseModel):
    url: HttpUrl
    title: str
    page: str

class LinkUpdate(BaseModel):
    url: Optional[HttpUrl] = None
    title: Optional[str] = None
    page: Optional[str] = None

class Alert(BaseModel):
    id: str
    type: str  # 'broken', 'warning', 'info'
    message: str
    time: str
    read: bool = False
    userId: str
    linkId: Optional[str] = None

class AlertCreate(BaseModel):
    type: str
    message: str
    linkId: Optional[str] = None

class AlertSettings(BaseModel):
    emailNotifications: bool = True
    brokenLinks: bool = True
    priceChanges: bool = True
    monthlyReports: bool = True