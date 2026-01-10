import os
from PIL import Image
from werkzeug.utils import secure_filename
from flask import current_app

MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 MB
MAX_WIDTH = 1200
JPEG_QUALITY = 85


def save_and_compress_image(file, labour_id, filename):
    if not file or not file.filename:
        return None

    # ---- HARD SIZE CHECK ----
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)

    if size > MAX_FILE_SIZE:
        raise ValueError("File size must be less than 1 MB")

    # ---- Upload directory ----
    upload_dir = os.path.join(
        current_app.root_path,
        'static', 'uploads', 'labours', str(labour_id)
    )
    os.makedirs(upload_dir, exist_ok=True)

    safe_name = secure_filename(filename)
    full_path = os.path.join(upload_dir, safe_name)

    # ---- Image processing ----
    img = Image.open(file)

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    if img.width > MAX_WIDTH:
        ratio = MAX_WIDTH / img.width
        img = img.resize(
            (MAX_WIDTH, int(img.height * ratio)),
            Image.LANCZOS
        )

    img.save(
        full_path,
        format="JPEG",
        quality=JPEG_QUALITY,
        optimize=True
    )

    return f"uploads/labours/{labour_id}/{safe_name}"
