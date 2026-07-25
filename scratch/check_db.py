import sqlite3
import os

db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "bot.db")
print("DB Path:", db_path)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Tables:", [t[0] for t in tables])
    
    if ("cross_guild_message_mappings",) in tables:
        cursor.execute("SELECT * FROM cross_guild_message_mappings;")
        rows = cursor.fetchall()
        print("Rows in cross_guild_message_mappings:", len(rows))
        for row in rows[:10]:
            print(row)
    else:
        print("cross_guild_message_mappings table does not exist!")
except Exception as e:
    print("Error:", e)
finally:
    conn.close()
