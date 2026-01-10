# models.py
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy import Index, UniqueConstraint

db = SQLAlchemy()

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=True)

    site = db.relationship('Site', back_populates='users', lazy='joined')

    def __repr__(self):
        return f"<User {self.id} {self.username}>"

class Site(db.Model):
    __tablename__ = 'sites'
    id = db.Column(db.Integer, primary_key=True)
    site_name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(512), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    location = db.Column(db.String(255), nullable=True)

    labours = db.relationship('Labour', back_populates='site', lazy='select')
    payments = db.relationship('Payment', back_populates='site', lazy='select')
    users = db.relationship('User', back_populates='site', lazy='select')

    def __repr__(self):
        return f"<Site {self.id} {self.site_name}>"

class Labour(db.Model):
    __tablename__ = 'labours'

    id = db.Column(db.Integer, primary_key=True)

    gate_pass_id = db.Column(db.String(50), nullable=True)

    # Identity
    name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20), nullable=False)

    #  DOCUMENT PATHS (FILES STORED ON DISK)
    photo_path = db.Column(db.String(255), nullable=True)
    aadhaar_front_path = db.Column(db.String(255), nullable=True)
    aadhaar_back_path = db.Column(db.String(255), nullable=True)

    gate_pass_front_path = db.Column(db.String(255), nullable=True)
    gate_pass_back_path = db.Column(db.String(255), nullable=True)

    # Finance
    bank_account = db.Column(db.String(50), nullable=True)
    ifsc_code = db.Column(db.String(20), nullable=True)
    daily_wage = db.Column(db.Numeric(10, 2), nullable=True)

    # Organisation
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)

    # Relationships
    site = db.relationship('Site', back_populates='labours', lazy='joined')
    attendances = db.relationship('Attendance', back_populates='labour', lazy='dynamic')
    payments = db.relationship('Payment', back_populates='labour', lazy='dynamic')
    monthly_expenses = db.relationship('LabourMonthlyExpenses', back_populates='labour', lazy='dynamic')

    # 🔒 DUPLICATE PREVENTION (PER SITE)
    __table_args__ = (
        db.UniqueConstraint('phone', 'site_id', name='uq_labour_phone_site'),
    )

    def __repr__(self):
        return f"<Labour {self.id} {self.name} ({self.phone})>"



class Attendance(db.Model):
    __tablename__ = 'attendance'

    id = db.Column(db.Integer, primary_key=True)
    labour_id = db.Column(db.Integer, db.ForeignKey('labours.id'), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=False)

    date = db.Column(db.Date, nullable=False)

    day_shift_flag = db.Column(db.Boolean, nullable=False, default=False)
    night_shift_flag = db.Column(db.Boolean, nullable=False, default=False)

    note = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    labour = db.relationship('Labour', back_populates='attendances')
    site = db.relationship('Site')

    __table_args__ = (
        UniqueConstraint('labour_id', 'date', name='uniq_labour_date'),
        Index('idx_attendance_site_date', 'site_id', 'date'),
        Index('idx_attendance_labour_date', 'labour_id', 'date'),
    )

class Payment(db.Model):
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)

    labour_id = db.Column(db.Integer, db.ForeignKey('labours.id'), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=False)

    date = db.Column(db.Date, nullable=True)
    advance = db.Column(db.Float, nullable=True)
    note = db.Column(db.String(255), nullable=True)

    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    labour = db.relationship('Labour', back_populates='payments', lazy='joined')
    site = db.relationship('Site', back_populates='payments', lazy='joined')
    created_by = db.relationship('User', lazy='joined')

    def __repr__(self):
        return f"<Payment {self.id} labour={self.labour_id} advance={self.advance}>"


class LabourMonthlyExpenses(db.Model):
    __tablename__ = 'labour_monthly_expenses'
    id = db.Column(db.Integer, primary_key=True)
    labour_id = db.Column(db.Integer, db.ForeignKey('labours.id'), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=False)
    month = db.Column(db.String(7), nullable=False)  # YYYY-MM
    mess_amount = db.Column(db.Float, nullable=False)
    canteen_amount = db.Column(db.Float, nullable=False)
    entered_by = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=True)

    labour = db.relationship('Labour', back_populates='monthly_expenses', lazy='joined')

    def __repr__(self):
        return f"<LabourMonthlyExpenses {self.id} labour={self.labour_id} month={self.month}>"

class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True)
    username = db.Column(db.String(100), nullable=True)
    role = db.Column(db.String(50), nullable=True)
    site_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f"<AuditLog {self.id} action={self.action}>"

# helper function — standalone so other modules can import log_event
def log_event(user_id=None, username=None, role=None, site_id=None,
              action=None, details=None, ip_address=None, commit=True):
    entry = AuditLog(
        user_id=user_id,
        username=username,
        role=role,
        site_id=site_id,
        action=action or '',
        details=str(details) if details is not None else None,
        ip_address=ip_address,
        created_at=datetime.utcnow()
    )
    db.session.add(entry)
    if commit:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
    return entry

class AuditLogArchive(db.Model):
    __tablename__ = 'audit_log_archive'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True)
    username = db.Column(db.String(100), nullable=True)
    role = db.Column(db.String(50), nullable=True)
    site_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f"<AuditLogArchive {self.id} action={self.action}>"
