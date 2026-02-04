from flask_login import login_required, current_user
from flask import render_template, redirect, url_for
from routes.manager import manager_bp
from services.manager_dashboard_service import get_manager_dashboard_data


@manager_bp.route('/dashboard')
@login_required
def manager_dashboard():
    if current_user.role != 'manager':
        return redirect(url_for('auth.login'))

    dashboard = get_manager_dashboard_data(current_user.site_id)

    return render_template(
        'manager_dashboard.html',
        dashboard=dashboard
    )
