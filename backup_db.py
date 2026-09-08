# backup_db.py
import os
import sys
import subprocess
from datetime import datetime
from urllib.parse import urlparse, unquote

def backup_database():
    database_url = os.environ.get("DATABASE_URL")
    
    # If not set in env, check config.py default
    if not database_url:
        try:
            from config import Config
            database_url = Config.SQLALCHEMY_DATABASE_URI
        except Exception:
            database_url = "mysql+pymysql://root:Admin%40123@localhost/labour_db"

    # Handle sqlite
    if "sqlite" in database_url:
        print("ℹ️ SQLite detected. Copying database file...")
        db_path = database_url.replace("sqlite:///", "")
        if os.path.exists(db_path):
            backup_file = f"backup_sqlite_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            import shutil
            shutil.copy2(db_path, backup_file)
            print(f"✅ SQLite backup created successfully: {backup_file}")
            return
        else:
            print(f"⚠️ SQLite database file not found at: {db_path}")
            return

    # Normalize url format for urlparse
    url = database_url.replace("mysql+pymysql://", "mysql://").replace("mysql+mysqldb://", "mysql://")
    parsed = urlparse(url)

    user = unquote(parsed.username or "root")
    password = unquote(parsed.password or "")
    host = parsed.hostname or "localhost"
    port = str(parsed.port or 3306)
    dbname = parsed.path.lstrip("/")

    if not dbname:
        print("❌ Error: No database name found in connection string.")
        sys.exit(1)

    backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"{dbname}_backup_{timestamp}.sql")

    print("=" * 60)
    print(f"📦 Starting Database Backup for: {dbname} ({host}:{port})")
    print("=" * 60)

    cmd = [
        "mysqldump",
        f"--host={host}",
        f"--port={port}",
        f"--user={user}",
        "--single-transaction",
        "--quick",
        dbname
    ]

    env = os.environ.copy()
    if password:
        env["MYSQL_PWD"] = password

    try:
        with open(backup_file, "w") as f:
            result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, env=env, text=True)

        if result.returncode == 0 and os.path.getsize(backup_file) > 0:
            size_kb = os.path.getsize(backup_file) / 1024
            print(f"✅ Backup created successfully!")
            print(f"📁 File: {backup_file}")
            print(f"📊 Size: {size_kb:.2f} KB")
        else:
            print(f"❌ Backup failed with exit code {result.returncode}")
            if result.stderr:
                print(f"Error details: {result.stderr}")
            if os.path.exists(backup_file) and os.path.getsize(backup_file) == 0:
                os.remove(backup_file)
            sys.exit(1)
    except FileNotFoundError:
        print("⚠️ 'mysqldump' command not found in PATH.")
        print(f"\nYou can run this command directly on your server:")
        print(f"mysqldump -u {user} -p {dbname} > backup_{dbname}_{timestamp}.sql")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Backup error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    backup_database()
