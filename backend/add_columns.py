import sqlite3
import os

db_path = "storage/app.db"

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE documents ADD COLUMN document_type VARCHAR DEFAULT 'sonstiges'")
    except sqlite3.OperationalError:
        pass
        
    try:
        cur.execute("ALTER TABLE documents ADD COLUMN summary TEXT")
    except sqlite3.OperationalError:
        pass
        
    try:
        cur.execute("ALTER TABLE documents ADD COLUMN financials_json TEXT")
    except sqlite3.OperationalError:
        pass
        
    try:
        cur.execute("ALTER TABLE documents ADD COLUMN tax_data_json TEXT")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()
    print("Database updated!")
else:
    print("No existing local database found to update.")
