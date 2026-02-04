from flask_login import login_required
from . import admin_bp
from .utils import _admin_required, _to_int

from services.site_service import (
    get_company_sites,
    create_site,
    update_site,
    deactivate_site,
    toggle_site_status
)
from datetime import datetime, timedelta, date
from flask import render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from models import User, Site, Attendance, Labour
from .utils import _admin_required
from services.site_dashboard_service import get_admin_site_dashboard
from extensions import db
from sqlalchemy import func, and_ , or_


@admin_bp.route('/sites')
@login_required
def admin_sites():
    if not _admin_required():
        return redirect(url_for('auth.login'))

    sites = get_company_sites(current_user.company_id)
    return render_template('admin_sites.html', sites=sites)

@admin_bp.route('/sites/add', methods=['GET', 'POST'])
@login_required
def admin_add_site():
    if not _admin_required():
        return redirect(url_for('auth.login'))

    managers = User.query.filter_by(
        role='manager',
        company_id=current_user.company_id
    ).all()

    if request.method == 'POST':
        try:
            create_site(
                company_id=current_user.company_id,
                site_name=request.form.get('site_name'),
                location=request.form.get('location'),
                address=request.form.get('address'),
                manager_id=request.form.get('manager_id')
            )
            flash('Site added successfully', 'success')
            return redirect(url_for('admin_bp.admin_sites'))
        except ValueError as e:
            flash(str(e), 'danger')

    return render_template(
        'admin_add_site.html',
        managers=managers
    )


@admin_bp.route('/sites/edit/<int:site_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_site(site_id):
    if not _admin_required():
        return redirect(url_for('auth.login'))

    site = Site.query.filter_by(
        id=site_id,
        company_id=current_user.company_id
    ).first_or_404()

    managers = User.query.filter_by(
        role='manager',
        company_id=current_user.company_id
    ).all()

    if request.method == 'POST':
        update_site(
            company_id=current_user.company_id,
            site_id=site_id,
            site_name=request.form.get('site_name'),
            location=request.form.get('location'),
            manager_id=request.form.get('manager_id')
        )
        flash('Site updated successfully', 'success')
        return redirect(url_for('admin_bp.admin_sites'))

    return render_template(
        'admin_edit_site.html',
        site=site,
        managers=managers
    )


@admin_bp.route('/sites/<int:site_id>/delete', methods=['POST'])
@login_required
def delete_site(site_id):
    if not _admin_required():
        return redirect(url_for('auth.login'))

    deactivate_site(
        company_id=current_user.company_id,
        site_id=site_id
    )
    flash('Site deactivated', 'info')
    return redirect(url_for('admin_bp.admin_sites'))


@admin_bp.route('/sites/toggle/<int:site_id>', methods=['POST'])
@login_required
def toggle_site(site_id):
    if not _admin_required():
        return redirect(url_for('auth.login'))

    toggle_site_status(
        company_id=current_user.company_id,
        site_id=site_id
    )
    flash('Site status updated', 'success')
    return redirect(url_for('admin_bp.admin_sites'))


@admin_bp.route('/sites/<int:site_id>')
@login_required
def admin_site_dashboard(site_id):
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))

    dashboard = get_admin_site_dashboard(site_id)

    if not dashboard:
        abort(404)

    return render_template(
        'admin_site_dashboard.html',
        dashboard=dashboard
    )


#-------------------VIEW MONTHLY ATTANDANCE---------------
