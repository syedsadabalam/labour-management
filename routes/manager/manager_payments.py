from datetime import datetime, date
from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user

from models import Labour, Payment
from services.payment_service import create_manager_payment, PaymentError
from services.audit_service import log_audit
from . import manager_bp
from sqlalchemy import or_

# ============================
# MANAGER – ADD ADVANCE
# ============================
@manager_bp.route('/payments/add', methods=['GET', 'POST'])
@login_required
def manager_add_payment():

    # 🔐 Only active labours of THIS site
    labours = Labour.query.filter_by(
        company_id=current_user.company_id,
        site_id=current_user.site_id,
        is_active=True
    ).order_by(Labour.name.asc()).all()

    if request.method == 'POST':
        labour_id = request.form.get('labour_id')
        advance_str = request.form.get('advance')
        date_str = request.form.get('date')
        note = request.form.get('note')

        # ---------- VALIDATION ----------
        if not labour_id or not advance_str:
            flash("Labour and advance amount are required", "danger")
            return redirect(url_for('manager_bp.manager_add_payment'))

        try:
            advance = float(advance_str)
            if advance <= 0:
                raise ValueError
        except ValueError:
            flash("Advance amount must be a positive number", "danger")
            return redirect(url_for('manager_bp.manager_add_payment'))

        try:
            payment_date = (
                datetime.strptime(date_str, "%Y-%m-%d").date()
                if date_str else date.today()
            )
        except ValueError:
            flash("Invalid date", "danger")
            return redirect(url_for('manager_bp.manager_add_payment'))

        # ❌ Future date block
        if payment_date > date.today():
            flash("Future dates are not allowed", "danger")
            return redirect(url_for('manager_bp.manager_add_payment'))

        # 🔐 SECURITY: labour must belong to same site
        labour = Labour.query.filter_by(
            id=labour_id,
            company_id=current_user.company_id,
            site_id=current_user.site_id,
            is_active=True
        ).first()

        if not labour:
            flash("Invalid labour selected", "danger")
            return redirect(url_for('manager_bp.manager_add_payment'))

        # ---------- SAVE ----------
        try:
            create_manager_payment(
                company_id=current_user.company_id,
                user=current_user,
                labour_id=labour.id,
                site_id=current_user.site_id,
                date=payment_date,
                advance=advance,
                note=note,
                ip_address=request.remote_addr
            )
        except PaymentError as e:
            flash(str(e), "danger")
            return redirect(url_for('manager_bp.manager_add_payment'))

        # ---------- AUDIT ----------
        try:
            log_audit(
                company_id=current_user.company_id,
                user_id=current_user.id,
                username=current_user.username,
                role=current_user.role,
                site_id=current_user.site_id,
                action="manager_add_advance",
                details=f"Advance ₹{advance} added for {labour.name}",
                ip_address=request.remote_addr
            )
        except Exception as e:
            current_app.logger.warning(e)

        flash("Advance payment added successfully", "success")
        return redirect(url_for('manager_bp.manager_payment_history'))

    # GET
    today = date.today().isoformat()
    return render_template(
        'manager_add_payment.html',
        labours=labours,
        today=today
    )


# ============================
# MANAGER – PAYMENT HISTORY
# ============================
@manager_bp.route('/payments/history')
@login_required
def manager_payment_history():

    search = request.args.get('search', '').strip()
    month = request.args.get('month', '').strip()
    page = request.args.get('page', 1, type=int)

    query = (
        Payment.query
        .join(Labour)
        .filter(
            Payment.company_id == current_user.company_id,
            Payment.site_id == current_user.site_id
        )
    )

    # 🔍 SEARCH: name / phone
    if search:
        query = query.filter(
            or_(
                Labour.name.ilike(f"%{search}%"),
                Labour.phone.ilike(f"%{search}%")
            )
        )

    # 📅 MONTH FILTER (YYYY-MM)
    if month:
        try:
            year, mon = map(int, month.split('-'))
            start = datetime(year, mon, 1).date()
            end = (
                datetime(year + 1, 1, 1).date()
                if mon == 12
                else datetime(year, mon + 1, 1).date()
            )
            query = query.filter(
                Payment.date >= start,
                Payment.date < end
            )
        except ValueError:
            pass  # invalid month → ignore filter

    pagination = (
        query
        .order_by(Payment.date.desc(), Payment.id.desc())
        .paginate(page=page, per_page=20, error_out=False)
    )

    return render_template(
        'manager_payment_history.html',
        payments=pagination.items,
        pagination=pagination,
        search=search,
        month=month
    )