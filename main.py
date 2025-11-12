from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import List
import httpx
import os
import csv
import io
import asyncio
import logging
import jwt
from datetime import datetime, timezone, timedelta
from datetime import datetime, timezone, timedelta
from jwt.exceptions import PyJWTError
from database.database import SessionLocal
from database.models import UserNotificationSettings
from auth.auth import create_access_token, get_current_user, get_current_active_user, verify_password, get_password_hash
from utils.url_validator import URLValidator

from services.email_service import email_service
from services.link_checker import schedule_link_checks
from services.link_check_service import LinkCheckService
from services.weekly_report_service import WeeklyReportService
from utils.url_validator import URLValidator
from utils.csv_validator import CSVValidator
from routers import admin

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# JWT Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"

from database.database import engine, get_db, database
from database.models import User, Link, Alert, LinkStatus
from schemas import (
    UserCreate, UserResponse, LinkCreate, LinkUpdate, LinkResponse,
    AlertCreate, AlertResponse, AlertSettings, PasswordResetRequest,
    PasswordReset, LinkCheck, LinkStatusResponse
)
from auth.auth import (
    get_current_user, get_current_active_user, verify_password,
    get_password_hash, create_access_token
)

# Initialize FastAPI app
app = FastAPI(title="LinkGuard API")

# Include admin router
app.include_router(admin.router)

# Weekly report scheduler
async def generate_weekly_reports():
    while True:
        try:
            db = SessionLocal()
            report_service = WeeklyReportService(db)
            await report_service.send_all_weekly_reports()
        except Exception as e:
            print(f"Error generating weekly reports: {str(e)}")
        finally:
            db.close()
        # Wait for next Monday
        await asyncio.sleep(get_seconds_until_next_monday())

def get_seconds_until_next_monday():
    now = datetime.now()
    next_monday = now + timedelta(days=(7 - now.weekday()))
    next_monday = next_monday.replace(hour=0, minute=0, second=0, microsecond=0)
    return (next_monday - now).total_seconds()

# Events to connect and disconnect from database
@app.on_event("startup")
async def startup():
    try:
        await database.connect()
        logger.info("✅ Database connected successfully")
    except Exception as e:
        logger.error(f"❌ Failed to connect to database: {str(e)}")
        raise
    
    # Start the link checker (in background, don't block startup)
    try:
        background_tasks = BackgroundTasks()
        schedule_link_checks(background_tasks)
        logger.info("✅ Link checker scheduled")
    except Exception as e:
        logger.warning(f"⚠️  Link checker scheduling failed: {str(e)}")
    
    # Start weekly report scheduler (in background, don't block startup)
    try:
        background_tasks.add_task(generate_weekly_reports)
        logger.info("✅ Weekly report scheduler started")
    except Exception as e:
        logger.warning(f"⚠️  Weekly report scheduler failed: {str(e)}")

@app.on_event("shutdown")
async def shutdown():
    try:
        await database.disconnect()
        logger.info("✅ Database disconnected successfully")
    except Exception as e:
        logger.error(f"❌ Error disconnecting from database: {str(e)}")

# CORS - Allow frontend origin
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3002")
cors_origins = [frontend_url, "http://localhost:3000", "http://localhost:3001", "http://localhost:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Authentication functions moved to auth.py module



# Auth endpoints
@app.post("/api/auth/signup", response_model=dict)
async def signup(user: UserCreate, db: Session = Depends(get_db)):
    try:
        # Input validation
        if len(user.password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")
        
        if not any(c.isupper() for c in user.password):
            raise HTTPException(status_code=400, detail="Password must contain at least one uppercase letter")
        
        if not any(c.islower() for c in user.password):
            raise HTTPException(status_code=400, detail="Password must contain at least one lowercase letter")
        
        if not any(c.isdigit() for c in user.password):
            raise HTTPException(status_code=400, detail="Password must contain at least one number")
        
        # Check if user exists
        db_user = db.query(User).filter(User.email == user.email).first()
        if db_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Create new user with bcrypt hashed password
        hashed_password = get_password_hash(user.password)
        db_user = User(
            email=user.email,
            hashed_password=hashed_password,
            name=user.name,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        # Create user and notification settings in a transaction
        try:
            db.add(db_user)
            db.flush()  # Get the user ID without committing
            
            # Create default notification settings
            notification_settings = UserNotificationSettings(
                user_id=db_user.id,
                email_enabled=True,
                broken_links=True,
                status_changes=True,
                weekly_report=True
            )
            db.add(notification_settings)
            db.commit()
            db.refresh(db_user)
            
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail="Failed to create user account. Please try again."
            )
        
        # Create access token with proper expiration
        access_token = create_access_token(
            data={"sub": user.email},
            expires_delta=timedelta(minutes=30)
        )
        
        # Send welcome email
        try:
            await email_service.send_email(
                user.email,
                "Welcome to LinkGuard!",
                f"""
                <h2>Welcome to LinkGuard, {user.name}!</h2>
                <p>Your account has been successfully created. You can now:</p>
                <ul>
                    <li>Add links to monitor</li>
                    <li>Set up custom alerts</li>
                    <li>View detailed analytics</li>
                </ul>
                <p>If you have any questions, feel free to contact our support team.</p>
                """
            )
        except Exception as e:
            print(f"Failed to send welcome email: {str(e)}")
            # Don't fail the signup if email fails
            
        return {
            "success": True,
            "access_token": access_token,
            "token_type": "bearer",
            "user": UserResponse.model_validate(db_user)
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        print(f"Error in signup: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Please try again."
        )

@app.post("/api/auth/forgot-password")
async def forgot_password(
    request: PasswordResetRequest,
    db: Session = Depends(get_db)
):
    try:
        user = db.query(User).filter(User.email == request.email).first()
        if not user:
            # Don't reveal whether email exists
            return {"message": "If your email is registered, you will receive reset instructions"}
        
        # Check if a reset was requested in the last 5 minutes
        if user.last_reset_request and (datetime.now(timezone.utc) - user.last_reset_request) < timedelta(minutes=5):
            return {"message": "If your email is registered, you will receive reset instructions"}
        
        # Generate secure reset token with expiration
        reset_token = create_access_token(
            data={
                "sub": user.email,
                "type": "reset",
                "jti": os.urandom(16).hex()  # Add unique identifier
            },
            expires_delta=timedelta(hours=1)
        )
        
        # Update user's reset token info
        user.password_reset_token = reset_token
        user.password_reset_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        user.last_reset_request = datetime.now(timezone.utc)
        db.commit()
        
        # Send reset email
        try:
            frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3002")
            await email_service.send_password_reset(user.email, reset_token, frontend_url)
        except Exception as e:
            print(f"Failed to send password reset email: {str(e)}")
            db.rollback()
            # Update failed attempts but don't reveal the error
            pass
        
        return {"message": "If your email is registered, you will receive reset instructions"}
        
    except Exception as e:
        print(f"Password reset error: {str(e)}")
        return {"message": "If your email is registered, you will receive reset instructions"}

@app.post("/api/auth/reset-password")
async def reset_password(
    reset_data: PasswordReset,
    db: Session = Depends(get_db)
):
    try:
        # Verify token and get user
        try:
            payload = jwt.decode(reset_data.token, SECRET_KEY, algorithms=[ALGORITHM])
            if payload.get("type") != "reset":
                raise HTTPException(status_code=400, detail="Invalid reset token")
            email = payload.get("sub")
        except PyJWTError:
            raise HTTPException(status_code=400, detail="Invalid or expired reset token")
        
        # Get user and verify token
        user = db.query(User).filter(User.email == email).first()
        if not user or user.password_reset_token != reset_data.token:
            raise HTTPException(status_code=400, detail="Invalid reset token")
        
        # Check if token is expired
        if not user.password_reset_expires or user.password_reset_expires < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Reset token has expired")
        
        # Validate new password
        if len(reset_data.new_password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")
        
        if not any(c.isupper() for c in reset_data.new_password):
            raise HTTPException(status_code=400, detail="Password must contain at least one uppercase letter")
        
        if not any(c.islower() for c in reset_data.new_password):
            raise HTTPException(status_code=400, detail="Password must contain at least one lowercase letter")
        
        if not any(c.isdigit() for c in reset_data.new_password):
            raise HTTPException(status_code=400, detail="Password must contain at least one number")
        
        # Update password
        user.hashed_password = get_password_hash(reset_data.new_password)
        user.password_reset_token = None
        user.password_reset_expires = None
        user.last_password_change = datetime.now(timezone.utc)
        user.failed_login_attempts = 0
        user.is_locked = False
        user.locked_until = None
        db.commit()
        
        # Send confirmation email
        try:
            await email_service.send_email(
                user.email,
                "Password Reset Successful",
                """
                <h2>Password Reset Successful</h2>
                <p>Your password has been successfully reset.</p>
                <p>If you did not perform this action, please contact support immediately.</p>
                """
            )
        except Exception as e:
            print(f"Failed to send password reset confirmation: {str(e)}")
            # Don't fail the reset if email fails
        
        return {"message": "Password has been reset successfully"}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Reset password error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while resetting your password"
        )

@app.post("/api/auth/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    try:
        # Find user and check if they exist
        user = db.query(User).filter(User.email == form_data.username).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Check if user is active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is disabled. Please contact support.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Verify password
        if not verify_password(form_data.password, user.hashed_password):
            # Update login attempts
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            user.last_failed_login = datetime.now(timezone.utc)
            
            # Lock account after 5 failed attempts
            if user.failed_login_attempts >= 5:
                user.is_locked = True
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
                db.commit()
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Account locked due to too many failed attempts. Try again in 30 minutes.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Check if account is locked
        if user.is_locked:
            if user.locked_until and user.locked_until > datetime.now(timezone.utc):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Account is locked. Try again later.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            else:
                # Unlock account if lock period has expired
                user.is_locked = False
                user.locked_until = None
        
        # Reset failed attempts on successful login
        user.failed_login_attempts = 0
        user.last_login = datetime.now(timezone.utc)
        db.commit()
        
        # Create access token with proper expiration
        access_token = create_access_token(
            data={"sub": user.email},
            expires_delta=timedelta(minutes=30)
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": UserResponse.model_validate(user)
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Login error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your request"
        )

@app.get("/api/auth/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_active_user)):
    return current_user

# Links endpoints
@app.get("/api/links", response_model=List[LinkResponse])
async def get_links(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    return db.query(Link).filter(Link.owner_id == current_user.id).all()

@app.get("/api/links/{link_id}", response_model=LinkResponse)
async def get_link(
    link_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    link = db.query(Link).filter(Link.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    
    if link.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this link")
    
    return link

@app.post("/api/links/{link_id}/check", response_model=LinkStatusResponse)
async def check_link_endpoint(
    link_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    link = db.query(Link).filter(Link.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    
    if link.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to check this link")
    
    return await check_link_status(link, db)

@app.post("/api/links", response_model=LinkResponse)
async def create_link(
    link_data: LinkCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    try:
        # Validate URL
        url_validator = URLValidator()
        sanitized_url = url_validator.sanitize_url(str(link_data.url))
        
        if not url_validator.is_valid_url(sanitized_url):
            raise HTTPException(
                status_code=400,
                detail="Invalid URL format"
            )
        
        # Check if URL already exists for this user
        existing_link = db.query(Link).filter(
            Link.owner_id == current_user.id,
            Link.url == sanitized_url
        ).first()
        
        if existing_link:
            raise HTTPException(
                status_code=400,
                detail="You already have this URL in your links"
            )
        
        # Validate check frequency
        if not 1 <= link_data.check_frequency <= 1440:
            raise HTTPException(
                status_code=400,
                detail="Check frequency must be between 1 and 1440 minutes"
            )
        
        # Create link
        db_link = Link(
            url=sanitized_url,
            name=link_data.name,
            description=link_data.description,
            check_frequency=link_data.check_frequency,
            owner_id=current_user.id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        db.add(db_link)
        db.commit()
        db.refresh(db_link)
        
        # Schedule initial check
        background_tasks = BackgroundTasks()
        background_tasks.add_task(check_link_status, db_link, db)
        
        return db_link
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating link: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="An error occurred while creating the link"
        )

@app.put("/api/links/{link_id}", response_model=LinkResponse)
async def update_link(
    link_id: int,
    link_update: LinkUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    link = db.query(Link).filter(Link.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    
    if link.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this link")
    
    for field, value in link_update.dict(exclude_unset=True).items():
        setattr(link, field, value)
    
    link.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(link)
    return link

@app.delete("/api/links/{link_id}")
async def delete_link(
    link_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    link = db.query(Link).filter(Link.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    
    if link.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this link")
    
    db.delete(link)
    db.commit()
    return {"success": True}

@app.post("/api/links/bulk-upload")
async def bulk_upload_links(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=400,
            detail="Only CSV files are supported"
        )
    
    # Read and validate file
    content = await file.read()
    csv_validator = CSVValidator()
    is_valid, error_message, valid_rows = await csv_validator.process_csv_file(content)
    
    if not is_valid:
        raise HTTPException(
            status_code=400,
            detail=error_message
        )
    
    results = {
        'success': [],
        'failed': []
    }
    
    # Process valid rows
    link_check_service = LinkCheckService(db)
    
    for row_num, row in enumerate(valid_rows, start=2):
        try:
            # Check if link already exists
            existing_link = db.query(Link).filter(
                Link.owner_id == current_user.id,
                Link.url == row['url']
            ).first()
            
            if existing_link:
                results['failed'].append({
                    'row': row_num,
                    'data': row,
                    'error': f"Link already exists: {row['url']}"
                })
                continue
            
            # Create link
            db_link = Link(
                url=row['url'],
                name=row['name'],
                description=row.get('description', ''),
                check_frequency=row.get('check_frequency', 60),
                owner_id=current_user.id,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            
            db.add(db_link)
            db.flush()  # Get ID without committing
            
            # Perform initial check
            try:
                status = await link_check_service.check_with_retry(db_link)
                db_link.last_checked = status.checked_at
                db_link.last_status = status.is_available
            except Exception as e:
                logger.error(f"Error checking link {db_link.url}: {str(e)}")
                # Continue even if check fails
            
            db.commit()
            db.refresh(db_link)
            
            results['success'].append({
                'row': row_num,
                'link': LinkResponse.model_validate(db_link)
            })
            
        except Exception as e:
            logger.error(f"Error processing row {row_num}: {str(e)}")
            db.rollback()
            results['failed'].append({
                'row': row_num,
                'data': row,
                'error': str(e)
            })
    
    # Return detailed results
    return {
        'success': len(results['success']),
        'failed': len(results['failed']),
        'details': {
            'successful_links': [r['link'] for r in results['success']],
            'failed_rows': results['failed']
        }
    }

# Alerts endpoints
@app.get("/api/alerts", response_model=List[AlertResponse])
async def get_alerts(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    return (
        db.query(Alert)
        .filter(Alert.user_id == current_user.id)
        .order_by(Alert.created_at.desc())
        .all()
    )

@app.post("/api/alerts", response_model=AlertResponse)
async def create_alert(
    alert_data: AlertCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Verify the link exists and belongs to the user
    link = db.query(Link).filter(Link.id == alert_data.link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    if link.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to create alert for this link")

    db_alert = Alert(
        type=alert_data.type,
        message=alert_data.message,
        link_id=alert_data.link_id,
        user_id=current_user.id
    )
    db.add(db_alert)
    db.commit()
    db.refresh(db_alert)
    return db_alert

@app.put("/api/alerts/{alert_id}/read", response_model=AlertResponse)
async def mark_alert_read(
    alert_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    if alert.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this alert")
    
    alert.is_read = True
    db.commit()
    db.refresh(alert)
    return alert

@app.put("/api/alerts/read-all")
async def mark_all_alerts_read(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    db.query(Alert).filter(
        Alert.user_id == current_user.id,
        Alert.is_read == False
    ).update({"is_read": True})
    db.commit()
    return {"success": True}

@app.get("/api/alerts/settings", response_model=AlertSettings)
async def get_alert_settings(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    settings = db.query(UserNotificationSettings).filter(
        UserNotificationSettings.user_id == current_user.id
    ).first()
    
    if not settings:
        settings = UserNotificationSettings(user_id=current_user.id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    
    return AlertSettings(
        email_notifications=settings.email_enabled,
        broken_links=settings.broken_links,
        status_changes=settings.status_changes,
        weekly_report=settings.weekly_report
    )

@app.put("/api/alerts/settings", response_model=AlertSettings)
async def update_alert_settings(
    settings: AlertSettings,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    db_settings = db.query(UserNotificationSettings).filter(
        UserNotificationSettings.user_id == current_user.id
    ).first()
    
    if not db_settings:
        db_settings = UserNotificationSettings(user_id=current_user.id)
        db.add(db_settings)
    
    db_settings.email_enabled = settings.email_notifications
    db_settings.broken_links = settings.broken_links
    db_settings.status_changes = settings.status_changes
    db_settings.weekly_report = settings.weekly_report
    
    db.commit()
    db.refresh(db_settings)
    
    return settings

# Health check
@app.get("/")
async def root():
    return {"status": "LinkGuard API is running", "version": "1.0.0"}

@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

# Link checker
async def check_link_status(link: Link, db: Session) -> LinkStatusResponse:
    try:
        start_time = datetime.now()
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.head(str(link.url), follow_redirects=True)
            end_time = datetime.now()
            response_time = int((end_time - start_time).total_seconds() * 1000)
            
            status_code = response.status_code
            is_healthy = 200 <= status_code < 400
            
            # Create link status record
            link_status = LinkStatus(
                link_id=link.id,
                status_code=status_code,
                response_time=response_time,
                is_available=is_healthy
            )
            db.add(link_status)
            
            # Update link
            link.last_checked = datetime.now(timezone.utc)
            
            # Create alert if link is broken
            if not is_healthy:
                alert = Alert(
                    type="broken",
                    message=f"Link is broken: {link.name} (HTTP {status_code})",
                    link_id=link.id,
                    user_id=link.owner_id
                )
                db.add(alert)
            
            db.commit()
            return LinkStatusResponse.model_validate(link_status)
            
    except Exception as e:
        # Create error status record
        link_status = LinkStatus(
            link_id=link.id,
            status_code=0,
            response_time=0,
            is_available=False
        )
        db.add(link_status)
        
        # Update link
        link.last_checked = datetime.now(timezone.utc)
        
        # Create alert for error
        alert = Alert(
            type="error",
            message=f"Error checking link {link.name}: {str(e)}",
            link_id=link.id,
            user_id=link.owner_id
        )
        db.add(alert)
        
        db.commit()
        return LinkStatusResponse.model_validate(link_status)

@app.post("/api/check-link", response_model=LinkResponse)
async def check_link(link: LinkCheck):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.head(link.url, follow_redirects=True)
            status = response.status_code
            
            is_healthy = 200 <= status < 400
            reason = "Healthy" if is_healthy else f"HTTP {status}"
            
            return LinkResponse(
                url=link.url,
                healthy=is_healthy,
                status=status,
                reason=reason,
                checked_at=datetime.now(timezone.utc).isoformat()
            )
    except Exception as e:
        return LinkResponse(
            url=link.url,
            healthy=False,
            status=0,
            reason=f"Connection Error: {str(e)}",
            checked_at=datetime.now(timezone.utc).isoformat()
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

