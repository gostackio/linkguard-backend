from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from databases import Database
import os
from dotenv import load_dotenv

# Load environment variables based on test mode
is_test = os.getenv("TESTING", "0") == "1"
if is_test:
    load_dotenv(".env.test")
else:
    load_dotenv()

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")

# Allow missing DATABASE_URL during module load (will fail at startup if truly missing)
if not DATABASE_URL:
    DATABASE_URL = "postgresql://localhost/linkguard_placeholder"
    print("⚠️  WARNING: DATABASE_URL not set, using placeholder. This will fail at startup.")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Add SSL mode for Supabase and remote databases
if "supabase" in DATABASE_URL or ("@" in DATABASE_URL and "localhost" not in DATABASE_URL):
    # Add SSL requirement for remote connections
    if "?" not in DATABASE_URL:
        DATABASE_URL += "?sslmode=require"
    elif "sslmode" not in DATABASE_URL:
        DATABASE_URL += "&sslmode=require"

print(f"🗄️  Database URL configured (host: {DATABASE_URL.split('@')[1].split('/')[0] if '@' in DATABASE_URL else 'local'})")

# SQLAlchemy engine
try:
    engine = create_engine(
        DATABASE_URL, 
        pool_pre_ping=True,
        echo=False,
        connect_args={"timeout": 10} if "sqlite" in DATABASE_URL else {}
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except Exception as e:
    print(f"⚠️  WARNING: Failed to create engine: {str(e)}")
    engine = None
    SessionLocal = None

# Async database instance
database = Database(DATABASE_URL)

# Base class for models
Base = declarative_base()
metadata = MetaData()

# Dependency to get database session
def get_db():
    if SessionLocal is None:
        raise RuntimeError("Database engine not initialized. Check DATABASE_URL.")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Initialize database connection
async def connect_to_db():
    await database.connect()

# Close database connection
async def close_db_connection():
    await database.disconnect()