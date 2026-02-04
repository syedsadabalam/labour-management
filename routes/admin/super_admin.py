from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from datetime import date, timedelta

from extensions import db
from models import Company, User, Plan
from . import admin_bp


def super_admin_required():
    return current_user.is_authenticated and current_user.role == 'super_admin'


@admin_bp.route('/super-admin/companies', methods=['GET'])
@login_required
def super_admin_companies():
    if not super_admin_required():
        abort(403)

    companies = Company.query.order_by(Company.created_at.desc()).all()
    return render_template(
        'super_admin_companies.html',
        companies=companies
    )


@admin_bp.route('/super-admin/companies/create', methods=['GET', 'POST'])
@login_required
def super_admin_create_company():
    if not super_admin_required():
        abort(403)

    plans = Plan.query.order_by(Plan.price).all()

    if request.method == 'POST':
        company_name = request.form.get('company_name', '').strip()
        plan_id = request.form.get('plan_id', type=int)
        plan_months = request.form.get('plan_months', type=int)

        admin_username = request.form.get('admin_username', '').strip()
        admin_password = request.form.get('admin_password', '').strip()

        if not all([company_name, plan_id, plan_months, admin_username, admin_password]):
            flash('All fields are required', 'danger')
            return redirect(request.url)

        try:
            # ---- CREATE COMPANY ----
            company = Company(
                company_name=company_name,
                plan_id=plan_id,
                plan_expires_at=date.today() + timedelta(days=30 * plan_months),
                is_active=True
            )
            db.session.add(company)
            db.session.flush()  # get company.id safely

            # ---- CREATE COMPANY ADMIN ----
            admin_user = User(
                username=admin_username,
                password=generate_password_hash(admin_password),
                role='admin',
                company_id=company.id
            )
            db.session.add(admin_user)

            db.session.commit()
            flash('Company and Admin created successfully', 'success')
            return redirect(url_for('admin_bp.super_admin_companies'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
            return redirect(request.url)

    return render_template(
        'super_admin_create_company.html',
        plans=plans
    )
