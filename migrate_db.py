from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app()

with app.app_context():
    try:
        db.session.execute(text("ALTER TABLE attendance MODIFY morning_shift_flag FLOAT DEFAULT 0.0;"))
        db.session.execute(text("ALTER TABLE attendance MODIFY day_shift_flag FLOAT DEFAULT 0.0;"))
        db.session.execute(text("ALTER TABLE attendance MODIFY night_shift_flag FLOAT DEFAULT 0.0;"))
        db.session.commit()
        print("Database migrated successfully!")
    except Exception as e:
        print("Error:", str(e))
        db.session.rollback()
