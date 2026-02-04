from flask_login import login_required, current_user
from flask import render_template, redirect, url_for
from . import admin_bp
from services.dashboard_service import get_admin_dashboard_data
from .utils import _admin_required, _to_int


@admin_bp.route('/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))

    dashboard = get_admin_dashboard_data(current_user.company_id)

    return render_template(
        "admin_dashboard.html",
        dashboard=dashboard
    )
