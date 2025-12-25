import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    # --------------------
    # CORE SETTINGS
    # --------------------
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret-key-change-me"
    DEBUG = False
    TESTING = False

    # --------------------
    # DATABASE (MySQL)
    # --------------------
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL")
        or "mysql+pymysql://root:Admin%40123@localhost/labour_db"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --------------------
    # SESSION / SECURITY
    # --------------------
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False  # True only when HTTPS

    # --------------------
    # LOGIN
    # --------------------
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_DURATION = 60 * 60 * 24 * 7  # 7 days

    # --------------------
    # TIMEZONE
    # --------------------
    APP_TIMEZONE = "Asia/Kolkata"



