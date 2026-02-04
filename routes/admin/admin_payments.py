from flask_login import login_required, current_user
from . import admin_bp
from services.payment_service import update_admin_payment
from .utils import _admin_required, _to_int
from models import Payment, Labour, Site
from extensions import db
from services.payment_service import get_admin_payments
from sqlalchemy import func
from flask import render_template, redirect, url_for, request
from datetime import datetime, timedelta, date
from flask import render_template, redirect, url_for, request, flash

@admin_bp.route('/payments')
@login_required
def admin_payments():
    if not _admin_required():
        return redirect(url_for('auth.login'))

    page = request.args.get('page', 1, type=int)
    labour_name = request.args.get('labour')
    site_id = request.args.get('site_id', type=int)
    month = request.args.get('month')

    pagination, sites, year, month_num = get_admin_payments(
        company_id=current_user.company_id,
        page=page,
        per_page=50,
        labour_name=labour_name,
        site_id=site_id,
        month=month
    )

    return render_template(
        'admin_payments.html',
        payments=pagination.items,
        pagination=pagination,
        sites=sites,
        current_month=f"{year}-{month_num:02d}"
    )

from services.payment_service import create_admin_payment, PaymentError

@admin_bp.route('/payments/add', methods=['GET', 'POST'])
@login_required
def admin_add_payment():
    if not _admin_required():
        return redirect(url_for('auth.login'))

    sites = Site.query.filter_by(
        company_id=current_user.company_id,
        is_active=True
    ).all()

    labours = Labour.query.filter_by(
        company_id=current_user.company_id,
        is_active=True
    ).all()

    # --- UI helper only ---
    labour_advances = {}
    for l in labours:
        total_adv = db.session.query(
            func.coalesce(func.sum(Payment.advance), 0.0)
        ).filter(Payment.labour_id == l.id).scalar()
        labour_advances[l.id] = float(total_adv or 0.0)

    if request.method == 'POST':
        try:
            create_admin_payment(
                company_id=current_user.company_id,
                user=current_user,
                labour_id=_to_int(request.form.get('labour_id')),
                site_id=_to_int(request.form.get('site_id')),
                date=request.form.get('date'),
                advance=float(request.form.get('advance') or 0),
                note=request.form.get('note'),
                ip_address=request.remote_addr,
            )
        except PaymentError as e:
            flash(str(e), 'danger')
            return redirect(url_for('admin_bp.admin_add_payment'))

        flash('Advance payment recorded', 'success')
        return redirect(url_for('admin_bp.admin_payments'))

    return render_template(
        'admin_add_payment.html',
        sites=sites,
        labours=labours,
        labour_advances=labour_advances,
        date=date
    )


@admin_bp.route('/payments/edit/<int:payment_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_payment(payment_id):
    if not _admin_required():
        return redirect(url_for('auth.login'))

    payment = Payment.query.get_or_404(payment_id)
    sites = Site.query.filter_by(
        company_id=current_user.company_id,
        is_active=True
    ).all()
    labours = Labour.query.filter_by(
        company_id=current_user.company_id,
        is_active=True
    ).all()


    if request.method == 'POST':
        try:
            update_admin_payment(
                payment=payment,
                user=current_user,
                date=request.form.get('date'),
                advance=float(request.form.get('advance') or 0),
                note=request.form.get('note'),
                ip_address=request.remote_addr,
            )
        except PaymentError as e:
            flash(str(e), 'danger')
            return redirect(url_for('admin_bp.admin_edit_payment', payment_id=payment.id))

        flash('Payment updated successfully', 'success')
        return redirect(url_for('admin_bp.admin_payments'))

    return render_template(
        'admin_edit_payment.html',
        payment=payment,
        labours=labours,
        sites=sites
    )


from services.payment_service import delete_admin_payment, PaymentError

@admin_bp.route('/payments/delete/<int:payment_id>', methods=['POST'])
@login_required
def delete_payment(payment_id):
    if not _admin_required():
        return redirect(url_for('auth.login'))

    try:
        delete_admin_payment(
            payment_id=payment_id,
            company_id=current_user.company_id,
            user=current_user,
            ip_address=request.remote_addr,
        )
    except PaymentError as e:
        flash(str(e), 'danger')
        return redirect(url_for('admin_bp.admin_payments'))

    flash('Payment deleted successfully', 'success')
    return redirect(url_for('admin_bp.admin_payments'))

