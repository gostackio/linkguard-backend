import asyncio
from database.database import engine, Base, connect_to_db, close_db_connection
from database.models import User, Link, Alert, LinkStatus

async def init_db():
    print("Connecting to database...")
    await connect_to_db()
    
    print("Creating tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    print("Database initialized successfully!")
    await close_db_connection()

if __name__ == "__main__":
    asyncio.run(init_db())