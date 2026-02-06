# models.py
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy import Index, UniqueConstraint

from extensions import db

class Plan(db.Model):
    __tablename__ = 'plans'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    price = db.Column(db.Integer, nullable=False)

    max_sites = db.Column(db.Integer, nullable=False)
    max_labours = db.Column(db.Integer, nullable=False)

    export_level = db.Column(
        db.Enum('monthly', 'all', name='export_level_enum'),
        nullable=False,
        default='monthly'
    )

    allow_audit = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # ✅ This NOW works because Company.plan_id exists
    companies = db.relationship(
        'Company',
        backref='plan',
        lazy='select'
    )

    def __repr__(self):
        return f"<Plan {self.name} ₹{self.price}>"


class Company(db.Model):
    __tablename__ = 'companies'

    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(150), nullable=False, unique=True)

    plan_id = db.Column(
        db.Integer,
        db.ForeignKey('plans.id'),
        nullable=False
    )

    plan_expires_at = db.Column(db.Date, nullable=True)

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    users = db.relationship('User', backref='company', lazy='select')
    sites = db.relationship('Site', backref='company', lazy='select')

    def __repr__(self):
        return f"<Company {self.company_name}>"


class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False)

    # ✅ THIS FK IS REQUIRED
    company_id = db.Column(
        db.Integer,
        db.ForeignKey('companies.id'),
        nullable=True
    )

    site_id = db.Column(
        db.Integer,
        db.ForeignKey('sites.id'),
        nullable=True
    )

    site = db.relationship('Site', back_populates='users')

    def __repr__(self):
        return f"<User {self.username}>"

class Site(db.Model):
    __tablename__ = 'sites'
    id = db.Column(db.Integer, primary_key=True)
    site_name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(512), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    location = db.Column(db.String(255), nullable=True)
    company_id = db.Column(
        db.Integer,
        db.ForeignKey('companies.id'),
        nullable=False
    )

    labours = db.relationship('Labour', back_populates='site', lazy='select')
    payments = db.relationship('Payment', back_populates='site', lazy='select')
    users = db.relationship('User', back_populates='site', lazy='select')

    allow_morning_shift = db.Column(db.Boolean, default=True)
    allow_day_shift     = db.Column(db.Boolean, default=True)
    allow_night_shift   = db.Column(db.Boolean, default=True)


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

    company_id = db.Column(
        db.Integer,
        db.ForeignKey('companies.id'),
        nullable=False
    )


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

class Payment(db.Model):
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    labour_id = db.Column(db.Integer, db.ForeignKey('labours.id'), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=False)

    date = db.Column(db.Date, nullable=True)
    advance = db.Column(db.Float, nullable=True)
    note = db.Column(db.String(255), nullable=True)

    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_by = db.relationship('User', lazy='joined')

    labour = db.relationship('Labour', back_populates='payments', lazy='joined')
    site = db.relationship('Site', back_populates='payments', lazy='joined')
    company = db.relationship('Company')


    def __repr__(self):
        return f"<Payment {self.id} labour={self.labour_id} advance={self.advance}>"

class Attendance(db.Model):
    __tablename__ = 'attendance'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    labour_id = db.Column(db.Integer, db.ForeignKey('labours.id'), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=False)

    date = db.Column(db.Date, nullable=False)
    
    morning_shift_flag = db.Column(db.Boolean, nullable=False, default=False)
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
    company = db.relationship('Company')

    __table_args__ = (
        UniqueConstraint('labour_id', 'date', name='uniq_labour_date'),
        Index('idx_attendance_site_date', 'site_id', 'date'),
        Index('idx_attendance_labour_date', 'labour_id', 'date'),
    )




class LabourMonthlyExpenses(db.Model):
    __tablename__ = 'labour_monthly_expenses'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    labour_id = db.Column(db.Integer, db.ForeignKey('labours.id'), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=False)
    month = db.Column(db.String(7), nullable=False)  # YYYY-MM
    mess_amount = db.Column(db.Float, nullable=False)
    canteen_amount = db.Column(db.Float, nullable=False)
    entered_by = db.Column(db.Integer, nullable=True)
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at = db.Column(db.DateTime, nullable=True)

    labour = db.relationship('Labour', back_populates='monthly_expenses', lazy='joined')
    company = db.relationship('Company')
    site = db.relationship('Site')


    def __repr__(self):
        return f"<LabourMonthlyExpenses {self.id} labour={self.labour_id} month={self.month}>"

class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    user_id = db.Column(db.Integer, nullable=True)
    username = db.Column(db.String(100), nullable=True)
    role = db.Column(db.String(50), nullable=True)
    site_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    def __repr__(self):
        return f"<AuditLog {self.id} action={self.action}>"

class AuditLogArchive(db.Model):
    __tablename__ = 'audit_log_archive'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    user_id = db.Column(db.Integer, nullable=True)
    username = db.Column(db.String(100), nullable=True)
    role = db.Column(db.String(50), nullable=True)
    site_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    def __repr__(self):
        return f"<AuditLogArchive {self.id} action={self.action}>"
