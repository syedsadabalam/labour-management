from datetime import datetime
from dateutil.relativedelta import relativedelta
from extensions import db
from models import AuditLog, AuditLogArchive

def archive_audit_logs_keep_last_3_months(company_id=None):
    now = datetime.utcnow()
    first_day_current_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    cutoff = first_day_current_month - relativedelta(months=2)

    query = AuditLog.query.filter(AuditLog.created_at < cutoff)
    if company_id:
        query = query.filter(AuditLog.company_id == company_id)

    old_logs = query.all()

    if not old_logs:
        return 0

    for log in old_logs:
        archived = AuditLogArchive(
            company_id=log.company_id,
            user_id=log.user_id,
            username=log.username,
            role=log.role,
            site_id=log.site_id,
            action=log.action,
            details=log.details,
            ip_address=log.ip_address,
            created_at=log.created_at
        )
        db.session.add(archived)
        db.session.delete(log)

    db.session.commit()
    return len(old_logs)
