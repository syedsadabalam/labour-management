# services/audit_service.py
from datetime import datetime
from extensions import db
from models import AuditLog

def log_audit(
    *,
    company_id,
    user_id=None,
    username=None,
    role=None,
    site_id=None,
    action,
    details=None,
    ip_address=None,
):
    entry = AuditLog(
        company_id=company_id,
        user_id=user_id,
        username=username,
        role=role,
        site_id=site_id,
        action=action,
        details=details,
        ip_address=ip_address,
        created_at=datetime.utcnow(),
    )
    db.session.add(entry)
    db.session.commit()
    return entry
