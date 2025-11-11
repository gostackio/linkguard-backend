from pydantic import BaseModel, EmailStr, HttpUrl
from typing import Optional, List
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    website: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    is_active: bool
    is_premium: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class TokenData(BaseModel):
    email: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class LinkBase(BaseModel):
    url: HttpUrl
    name: str
    description: Optional[str] = None
    check_frequency: int = 60  # Default check frequency in minutes

class LinkCreate(LinkBase):
    pass

class LinkUpdate(BaseModel):
    url: Optional[HttpUrl] = None
    name: Optional[str] = None
    description: Optional[str] = None
    check_frequency: Optional[int] = None
    is_active: Optional[bool] = None

class LinkResponse(LinkBase):
    id: int
    is_active: bool
    last_checked: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    owner_id: int

    class Config:
        from_attributes = True

class AlertBase(BaseModel):
    type: str
    message: str
    link_id: int

class AlertCreate(AlertBase):
    pass

class AlertResponse(AlertBase):
    id: int
    user_id: int
    created_at: datetime
    is_read: bool

    class Config:
        from_attributes = True

class LinkStatusBase(BaseModel):
    status_code: int
    response_time: int  # in milliseconds
    is_available: bool

class LinkStatusCreate(LinkStatusBase):
    link_id: int

class LinkStatusResponse(LinkStatusBase):
    id: int
    link_id: int
    checked_at: datetime

    class Config:
        from_attributes = True

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordReset(BaseModel):
    token: str
    password: str

class AlertSettings(BaseModel):
    email_notifications: bool = True
    broken_links: bool = True
    price_changes: bool = True
    monthly_reports: bool = True