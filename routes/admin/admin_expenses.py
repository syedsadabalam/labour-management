from .utils import _admin_required, _to_int

from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import Labour, LabourMonthlyExpenses, Site
from extensions import db
from . import admin_bp


@admin_bp.route('/monthly-expenses')
@login_required
def admin_monthly_expenses():
    if current_user.role != 'admin':
        flash('Only Admin can add or view expenses', 'danger')
        return redirect(url_for('manager_bp.manager_dashboard'))

    site_id = request.args.get('site_id', type=int)
    month = request.args.get('month')  # YYYY-MM

    sites = Site.query.filter_by(is_active=True, company_id=current_user.company_id).all()
    labours = []

    expenses_map = {}

    if site_id and month:
        labours = Labour.query.filter_by(site_id=site_id, is_active=True).all()

        expenses = LabourMonthlyExpenses.query.filter_by(
            site_id=site_id,
            month=month
        ).all()

        expenses_map = {e.labour_id: e for e in expenses}

    return render_template(
        'admin_monthly_expenses.html',
        sites=sites,
        labours=labours,
        expenses_map=expenses_map,
        selected_site=site_id,
        selected_month=month
    )


@admin_bp.route('/monthly-expenses/save', methods=['POST'])
@login_required
def save_monthly_expense():
    if current_user.role != 'admin':
        return jsonify({'status': 'error'}), 403

    data = request.get_json()

    labour_id = int(data['labour_id'])
    site_id = int(data['site_id'])          # ✅ FIX
    month = data['month']
    mess = float(data.get('mess', 0))
    canteen = float(data.get('canteen', 0))

    # Ensure site belongs to company
    site = Site.query.filter_by(id=site_id, company_id=current_user.company_id).first()
    if not site:
        return jsonify({'status': 'error', 'message': 'Invalid site'}), 400
        
    # Ensure labour belongs to company
    labour = Labour.query.filter_by(id=labour_id, company_id=current_user.company_id).first()
    if not labour:
        return jsonify({'status': 'error', 'message': 'Invalid labour'}), 400

    expense = LabourMonthlyExpenses.query.filter_by(
        labour_id=labour_id,
        site_id=site_id,
        company_id=current_user.company_id,
        month=month
    ).first()

    if expense:
        expense.mess_amount = mess
        expense.canteen_amount = canteen
        expense.entered_by = current_user.id
    else:
        expense = LabourMonthlyExpenses(
            labour_id=labour_id,
            site_id=site_id,
            company_id=current_user.company_id,
            month=month,
            mess_amount=mess,
            canteen_amount=canteen,
            entered_by=current_user.id
        )
        db.session.add(expense)

    db.session.commit()
    return jsonify({'status': 'ok'})
