import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.database import Database

async def main():
    db = Database()
    try:
        await db.connect()
        print("Successfully connected and created tables!")
        
        # Verify tables now
        async with db.db.execute("SELECT name FROM sqlite_master WHERE type='table';") as cursor:
            tables = await cursor.fetchall()
            print("Tables in bot.db after connect():", [t[0] for t in tables])
    except Exception as e:
        print("Error during database connection:", e)
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(main())
