from flask_login import current_user
from datetime import datetime, timedelta, date
import pytz
import re

from services.image_service import save_and_compress_image

def admin_required():
    return current_user.is_authenticated and current_user.role == 'admin'



MAX_FILE_SIZE = 1 * 1024 * 1024   # 1 MB per file
MAX_WIDTH = 1200                 # resize width
JPEG_QUALITY = 75                # compression quality






IST = pytz.timezone("Asia/Kolkata")

def to_ist(dt):
    if not dt:
        return None
    return dt.astimezone(IST)


# --------------------------------------ALL HELPERS------------------------------
def _admin_required():
    if not current_user.is_authenticated or getattr(current_user, 'role', None) != 'admin':
        flash('Unauthorized', 'danger')
        return False
    return True

def _to_int(v):
    try:
        return int(v)
    except Exception:
        return None
