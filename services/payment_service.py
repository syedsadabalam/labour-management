# services/payment_service.py
from datetime import datetime
from sqlalchemy import extract
from extensions import db
from models import Payment, Labour, Site

from services.audit_service import log_audit

def get_admin_payments(
    *,
    company_id,
    page=1,
    per_page=50,
    labour_name=None,
    site_id=None,
    month=None
):
    query = (
        db.session.query(Payment)
        .join(Labour, Payment.labour_id == Labour.id)
        .filter(Labour.company_id == company_id)
    )

    # Labour name filter
    if labour_name:
        query = query.filter(Labour.name.ilike(f"%{labour_name}%"))

    # Site filter
    if site_id:
        query = query.filter(Payment.site_id == site_id)

    # Month filter
    if month:
        year, month_num = map(int, month.split('-'))
    else:
        today = datetime.today()
        year, month_num = today.year, today.month

    query = query.filter(
        extract('year', Payment.date) == year,
        extract('month', Payment.date) == month_num
    )

    pagination = query.order_by(Payment.date.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )

    sites = (
        Site.query
        .filter_by(company_id=company_id)
        .order_by(Site.site_name)
        .all()
    )

    return pagination, sites, year, month_num



class PaymentError(Exception):
    pass


def create_admin_payment(
    *,
    company_id,
    user,
    labour_id,
    site_id,
    date,
    advance,
    note,
    ip_address=None,
):
    # -------- VALIDATIONS --------

    if advance <= 0:
        raise PaymentError("Advance amount must be greater than zero")

    labour = Labour.query.filter_by(
        id=labour_id,
        company_id=company_id,
        is_active=True
    ).first()

    if not labour:
        raise PaymentError("Invalid labour selected")

    if labour.site_id != site_id:
        raise PaymentError("Labour does not belong to selected site")

    # -------- CREATE PAYMENT --------

    payment = Payment(
        labour_id=labour.id,
        company_id=company_id,
        site_id=site_id,
        date=date,
        advance=advance,
        note=note,
        created_by_id=user.id,
    )

    db.session.add(payment)
    db.session.commit()

    # -------- AUDIT (NON-BLOCKING) --------
    try:
        log_audit(
            company_id=company_id,
            user_id=user.id,
            username=user.username,
            role=user.role,
            site_id=site_id,
            action="admin_add_payment",
            details=f"Advance {advance} added for labour '{labour.name}'",
            ip_address=ip_address,
        )
    except Exception:
        pass

    return payment

def update_admin_payment(
    *,
    payment,
    user,
    date,
    advance,
    note,
    ip_address=None
):
    if advance <= 0:
        raise PaymentError("Advance amount must be greater than zero")

    payment.date = date
    payment.advance = advance
    payment.note = note

    db.session.commit()

    try:
        log_audit(
            company_id=payment.company_id,
            user_id=user.id,
            username=user.username,
            role=user.role,
            site_id=payment.site_id,
            action="admin_edit_payment",
            details=f"Payment {payment.id} updated",
            ip_address=ip_address,
        )
    except Exception:
        pass

    return payment

def delete_admin_payment(
    *,
    payment_id,
    company_id,
    user,
    ip_address=None
):
    payment = Payment.query.filter_by(
        id=payment_id,
        company_id=company_id
    ).first()

    if not payment:
        raise PaymentError("Payment not found or access denied")

    # Capture context BEFORE delete
    payment_id_val = payment.id
    labour_id = payment.labour_id
    site_id = payment.site_id
    amount = payment.advance

    db.session.delete(payment)
    db.session.commit()

    # ---- AUDIT (NON-BLOCKING) ----
    try:
        log_audit(
            company_id=company_id,
            user_id=user.id,
            username=user.username,
            role=user.role,
            site_id=site_id,
            action="admin_delete_payment",
            details=f"Payment {payment_id_val} (₹{amount}) deleted for labour {labour_id}",
            ip_address=ip_address,
        )
    except Exception:
        pass

    return True

def create_manager_payment(
    *,
    company_id,
    user,
    labour_id,
    site_id,
    date,
    advance,
    note,
    ip_address=None
):
    if advance <= 0:
        raise PaymentError("Advance must be greater than zero")

    labour = Labour.query.filter_by(
        id=labour_id,
        site_id=site_id,
        is_active=True
    ).first()

    if not labour:
        raise PaymentError("Invalid labour")

    payment = Payment(
        labour_id=labour.id,
        company_id=company_id,
        site_id=site_id,
        date=date,
        advance=advance,
        note=note,
        created_by_id=user.id
    )

    db.session.add(payment)
    db.session.commit()

    try:
        log_audit(
            company_id=company_id,
            user_id=user.id,
            username=user.username,
            role=user.role,
            site_id=site_id,
            action="manager_add_payment",
            details=f"Advance {advance} added",
            ip_address=ip_address
        )
    except Exception:
        pass

    return payment
