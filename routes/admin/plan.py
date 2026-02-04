from flask import render_template, abort
from flask_login import login_required, current_user
from . import admin_bp
from services.plan_service import is_plan_expired


@admin_bp.route('/plan-expired')
@login_required
def plan_expired():
    if current_user.role not in ['admin', 'manager']:
        abort(403)

    if not is_plan_expired(current_user.company):
        return redirect(url_for('admin_bp.admin_dashboard'))

    return render_template('admin_plan_expired.html')
