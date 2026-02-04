
from flask import render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from . import admin_bp
from models import AuditLog, Site
import pytz
from services.audit_archive_service import archive_audit_logs_keep_last_3_months

from .utils import _admin_required, _to_int



@admin_bp.route('/audit-logs')
@login_required
def admin_audit_logs():
    if current_user.role != 'admin':
        flash('Access denied', 'danger')
        return redirect(url_for('admin_bp.admin_dashboard'))

    # Filters
    role = request.args.get('role')
    site_id = request.args.get('site_id')

    query = AuditLog.query

    if role:
        query = query.filter(AuditLog.role == role)

    if site_id:
        query = query.filter(AuditLog.site_id == site_id)

    logs = query.order_by(AuditLog.created_at.desc()).limit(500).all()

    sites = Site.query.filter_by(
        company_id=current_user.company_id,
        is_active=True
    ).all()

    return render_template(
    'admin_audit_logs.html',
    logs=logs,
    sites=sites,
    selected_role=role,
    selected_site=site_id,
    pytz=pytz   
    )
#----------MANUAL METHOD archive_audit_logs(days=180)---------------------------
@admin_bp.route('/audit/archive-now', methods=['POST'])
@login_required
def archive_audit_now():
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))

    count = archive_audit_logs_keep_last_3_months()


    flash(f'{count} audit logs archived successfully.', 'success')
    return redirect(url_for('admin_bp.admin_audit_logs'))

