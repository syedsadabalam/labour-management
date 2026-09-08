from flask import render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from . import admin_bp
from .utils import _admin_required, _to_int

from models import User, Site
from extensions import db
from .utils import _admin_required, _to_int


@admin_bp.route('/managers')
@login_required
def admin_managers():
    if not _admin_required():
        return redirect(url_for('auth.login'))
    managers = User.query.filter_by(role='manager',company_id=current_user.company_id).order_by(User.id.desc()).all()
    return render_template('admin_managers.html', managers=managers)

# ================== ADD MANAGER ==================
@admin_bp.route('/managers/add', methods=['GET','POST'])
@login_required
def admin_add_manager():
    if not _admin_required():
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        username = request.form.get('username')
        from werkzeug.security import generate_password_hash
        pwd = generate_password_hash(request.form.get('password') or 'manager123')
        site_id = _to_int(request.form.get('site_id'))
        
        if site_id:
            site = Site.query.filter_by(id=site_id, company_id=current_user.company_id).first()
            if not site:
                flash("Invalid site selected.", "danger")
                return redirect(url_for('admin_bp.admin_add_manager'))

        m = User(
            username=username,
            password=pwd,
            role='manager',
            site_id=site_id,
            company_id=current_user.company_id
        )

        from sqlalchemy.exc import IntegrityError
        try:
            db.session.add(m)
            db.session.commit()
            flash('Manager added', 'success')
            return redirect(url_for('admin_bp.admin_managers'))
        except IntegrityError:
            db.session.rollback()
            flash('Username is already taken. Please choose another.', 'danger')
            return redirect(url_for('admin_bp.admin_add_manager'))
            
    sites = Site.query.filter_by(
        company_id=current_user.company_id,
        is_active=True
    ).all()
    return render_template('admin_add_manager.html', sites=sites)

# ================== EDIT MANAGER ==================
@admin_bp.route('/managers/edit/<int:manager_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_manager(manager_id):
    if not _admin_required():
        return redirect(url_for('auth.login'))

    manager = User.query.filter_by(id=manager_id, role='manager', company_id=current_user.company_id).first_or_404()
    sites = Site.query.filter_by(
        company_id=current_user.company_id,
        is_active=True
    ).all()

    if request.method == 'POST':
        from werkzeug.security import generate_password_hash
        manager.username = request.form.get('username')
        
        site_id = request.form.get('site_id')
        if site_id:
            site = Site.query.filter_by(id=site_id, company_id=current_user.company_id).first()
            if not site:
                flash("Invalid site selected.", "danger")
                return redirect(url_for('admin_bp.admin_edit_manager', manager_id=manager_id))
            manager.site_id = int(site_id)
        else:
            manager.site_id = None

        new_password = request.form.get('password', '').strip()
        if new_password:
            manager.password = generate_password_hash(new_password)

        from sqlalchemy.exc import IntegrityError
        try:
            db.session.commit()
            flash('Manager updated successfully', 'success')
            return redirect(url_for('admin_bp.admin_managers'))
        except IntegrityError:
            db.session.rollback()
            flash('Username is already taken. Please choose another.', 'danger')
            return redirect(url_for('admin_bp.admin_edit_manager', manager_id=manager_id))

    return render_template(
        'admin_edit_manager.html',
        manager=manager,
        sites=sites
    )


# ================== DELETE MANAGER ==================
@admin_bp.route('/managers/delete/<int:manager_id>', methods=['POST'])
@login_required
def delete_manager(manager_id):
    if not _admin_required():
        return redirect(url_for('auth.login'))

    manager = User.query.filter_by(id=manager_id, role='manager', company_id=current_user.company_id).first_or_404()
    db.session.delete(manager)
    db.session.commit()

    flash('Manager deleted successfully', 'success')
    return redirect(url_for('admin_bp.admin_managers'))
