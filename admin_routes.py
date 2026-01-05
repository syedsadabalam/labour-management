from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, Response
from flask_login import login_required, current_user
from sqlalchemy import func, desc, or_, case
from sqlalchemy.orm import joinedload
from datetime import datetime, date
import csv, io
from datetime import date
from flask import jsonify
from decimal import Decimal
import pytz
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import func, and_
from flask_login import login_required
import pandas as pd
from flask import Response
import xlsxwriter
from sqlalchemy import extract
from models import db, Site, Labour, Payment, Attendance, User, LabourMonthlyExpenses, log_event, AuditLog
from sqlalchemy.exc import IntegrityError
import re



admin_bp = Blueprint('admin_bp', __name__, url_prefix='/admin', template_folder='templates')



IST = pytz.timezone("Asia/Kolkata")
def to_ist(dt):
    if not dt:
        return None
    return dt.astimezone(IST)

def log_action(action, details=None, site_id=None):
    log = AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        site_id=site_id,
        action=action,
        details=details,
        ip_address=request.remote_addr,
        created_at=datetime.utcnow()  # always store UTC
    )
    db.session.add(log)
    db.session.commit()



# helpers
def _admin_required():
    if not current_user.is_authenticated or getattr(current_user, 'role', None) != 'admin':
        flash('Unauthorized', 'danger')
        return False
    return True

def _to_int(v):
    try:
        return int(v)
    except Exception:
        return None

# dashboard
# dashboard
@admin_bp.route('/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
        
    today = date.today()
    year = today.year
    month = today.month

    # BASIC COUNTS
    total_labours = Labour.query.filter_by(is_active=True).count()
    total_managers = User.query.filter_by(role='manager').count()
    total_sites = Site.query.count()

    # TODAY PRESENT
    today_present = (
        db.session.query(func.count(func.distinct(Attendance.labour_id)))
        .filter(
            Attendance.date == today,
            or_(
                Attendance.day_shift_flag == True,
                Attendance.night_shift_flag == True
            )
        )
        .scalar()
    ) or 0

    # ---------- TOTAL PAYABLE (CURRENT MONTH) ----------
    per_labour_shifts = (
        db.session.query(
            Attendance.labour_id.label('labour_id'),
            func.sum(
                case((Attendance.day_shift_flag == True, 1), else_=0) +
                case((Attendance.night_shift_flag == True, 1), else_=0)
            ).label('shift_count')
        )
        .filter(
            extract('year', Attendance.date) == year,
            extract('month', Attendance.date) == month
        )
        .group_by(Attendance.labour_id)
        .subquery()
    )

    total_payable_amount = (
        db.session.query(
            func.coalesce(
                func.sum(per_labour_shifts.c.shift_count * Labour.daily_wage),
                0
            )
        )
        .select_from(per_labour_shifts)
        .join(Labour, Labour.id == per_labour_shifts.c.labour_id)
        .filter(Labour.is_active == True)
        .scalar()
    ) or 0

    # TOTAL ADVANCES (ALL TIME)
    total_advance = (
        db.session.query(func.coalesce(func.sum(Payment.advance), 0))
        .scalar()
    ) or 0


    # -------- TOP LABOURS BY PRESENCE --------
    top_labours = (
        db.session.query(
            Labour.id,
            Labour.name,
            func.sum(
                case((Attendance.day_shift_flag == True, 1), else_=0) +
                case((Attendance.night_shift_flag == True, 1), else_=0)
            ).label('days_present')
        )
        .join(Attendance, Attendance.labour_id == Labour.id)
        .group_by(Labour.id)
        .order_by(desc('days_present'))
        .limit(10)
        .all()
    )

    top_labours = [
        {'id': l.id, 'name': l.name, 'days_present': int(l.days_present)}
        for l in top_labours
    ]

    sites = Site.query.order_by(Site.site_name).all()


    
    # -------- MANAGER ACTIVITY (CORRECT) --------
    
    today = date.today()

    site_activity = []

    for s in sites:
        last_attendance = (
            db.session.query(func.max(Attendance.date))
            .filter(Attendance.site_id == s.id)
            .scalar()
        )

        if last_attendance == today:
            status = 'Active'
        elif last_attendance:
            status = 'Delayed'
        else:
            status = 'Inactive'

        site_activity.append({
            'site_name': s.site_name,
            'last_attendance': last_attendance,
            'status': status
        })


    # -------- ACTIVE SITES --------
    sites = Site.query.all()

    return render_template(
        'admin_dashboard.html',
        total_labours=total_labours,
        total_managers=total_managers,
        total_sites=total_sites,
        today_present=today_present,
        total_payable_amount=total_payable_amount,
        total_advance=total_advance,
        top_labours=top_labours,
        site_activity=site_activity,
        sites=sites
    )

# Sites
@admin_bp.route('/sites')
@login_required
def admin_sites():
    if not _admin_required():
        return redirect(url_for('auth.login'))

    sites = Site.query.all()
    return render_template('admin_sites.html', sites=sites)


@admin_bp.route('/sites/add', methods=['GET','POST'])
@login_required
def admin_add_site():
    if not _admin_required():
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        site_name = request.form.get('site_name')
        address = request.form.get('address')
        location = request.form.get('location')
        s = Site(site_name=site_name, address=address, location=location, is_active=True)
        db.session.add(s); db.session.commit()
        flash('Site added', 'success')
        return redirect(url_for('admin_bp.admin_sites'))
    return render_template('admin_add_site.html')

@admin_bp.route('/sites/edit/<int:site_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_site(site_id):
    if not _admin_required():
        return redirect(url_for('auth.login'))

    site = Site.query.get_or_404(site_id)
    managers = User.query.filter_by(role='manager').all()

    if request.method == 'POST':
        site.site_name = request.form.get('site_name')
        site.location = request.form.get('location')
        site.manager_id = request.form.get('manager_id') or None

        db.session.commit()
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
    site = Site.query.get_or_404(site_id)
    db.session.delete(site); db.session.commit()
    flash('Site deleted', 'info')
    return redirect(url_for('admin_bp.admin_sites'))

@admin_bp.route('/sites/toggle/<int:site_id>', methods=['POST'])
@login_required
def toggle_site_status(site_id):
    if not _admin_required():
        return redirect(url_for('auth.login'))

    site = Site.query.get_or_404(site_id)
    site.is_active = not site.is_active

    db.session.commit()
    flash(
        f"Site {'activated' if site.is_active else 'deactivated'} successfully",
        'success'
    )
    return redirect(url_for('admin_bp.admin_sites'))



# ================== MANAGER ==================
@admin_bp.route('/managers')
@login_required
def admin_managers():
    if not _admin_required():
        return redirect(url_for('auth.login'))
    managers = User.query.filter_by(role='manager').order_by(User.id.desc()).all()
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
        m = User(username=username, password=pwd, role='manager', site_id=site_id)
        db.session.add(m); db.session.commit()
        flash('Manager added', 'success')
        return redirect(url_for('admin_bp.admin_managers'))
    sites = Site.query.all()
    return render_template('add_manager.html', sites=sites)

# ================== EDIT MANAGER ==================
@admin_bp.route('/managers/edit/<int:manager_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_manager(manager_id):
    if not _admin_required():
        return redirect(url_for('auth.login'))

    manager = User.query.filter_by(id=manager_id, role='manager').first_or_404()
    sites = Site.query.all()

    if request.method == 'POST':
        manager.username = request.form.get('username')
        site_id = request.form.get('site_id')
        manager.site_id = int(site_id) if site_id else None

        db.session.commit()
        flash('Manager updated successfully', 'success')
        return redirect(url_for('admin_bp.admin_managers'))

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

    manager = User.query.filter_by(id=manager_id, role='manager').first_or_404()
    db.session.delete(manager)
    db.session.commit()

    flash('Manager deleted successfully', 'success')
    return redirect(url_for('admin_bp.admin_managers'))



# Labours
@admin_bp.route('/labours')
@login_required
def admin_labours():
    search = request.args.get('search', '').strip()
    site_id = request.args.get('site_id', '').strip()
    page = request.args.get('page', 1, type=int)

    PER_PAGE = 30

    query = Labour.query

    # 🔍 Search by name OR phone
    if search:
        query = query.filter(
            or_(
                Labour.name.ilike(f"%{search}%"),
                Labour.phone.ilike(f"%{search}%")
            )
        )

    #  Filter by site
    if site_id:
        query = query.filter(Labour.site_id == site_id)

    # ✅ Pagination (THIS is the real fix)
    pagination = query.order_by(Labour.id.desc()).paginate(
        page=page,
        per_page=PER_PAGE,
        error_out=False
    )

    sites = Site.query.order_by(Site.site_name).all()

    return render_template(
        "admin_labours.html",
        labours=pagination.items,   # 🔥 IMPORTANT
        pagination=pagination,      # 🔥 REQUIRED or next/prev
        sites=sites,
        search=search,
        site_id=site_id
)


@admin_bp.route('/labours/add', methods=['GET', 'POST'])
@login_required
def admin_add_labour():
    if not _admin_required():
        return redirect(url_for('auth.login'))

    sites = Site.query.all()

    if request.method == 'POST':
        phone = request.form.get('phone')
        site_id = _to_int(request.form.get('site_id'))

        # ---- DUPLICATE CHECK (USER FRIENDLY) ----
        existing = Labour.query.filter_by(
            phone=phone,
            site_id=site_id,
            is_active=True
        ).first()

        if existing:
            flash(
                'Labour with this phone number already exists for this site.',
                'danger'
            )
            return redirect(url_for('admin_bp.admin_add_labour'))

        labour = Labour(
            name=request.form.get('name'),
            phone=phone,
            bank_account=request.form.get('bank_account'),
            ifsc_code=request.form.get('ifsc_code'),
            site_id=site_id,
            daily_wage=request.form.get('daily_wage') or None,
            is_active=(request.form.get('is_active') == 'on')
        )

        try:
            db.session.add(labour)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(
                'Duplicate labour detected (same phone & site).',
                'danger'
            )
            return redirect(url_for('admin_bp.admin_add_labour'))

        # ---- AUDIT LOG ----
        log_action(
            action='labour_added',
            details=f"Labour '{labour.name}' added",
            site_id=labour.site_id
        )

        flash('Labour added successfully', 'success')
        return redirect(url_for('admin_bp.admin_labours'))

    return render_template('admin_add_labour.html', sites=sites)


@admin_bp.route('/labours/<int:labour_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_edit_labour(labour_id):
    if not _admin_required():
        return redirect(url_for('auth.login'))

    labour = Labour.query.get_or_404(labour_id)
    sites = Site.query.all()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        bank_account = request.form.get('bank_account', '').strip()
        ifsc_code = request.form.get('ifsc_code', '').strip()
        site_id = _to_int(request.form.get('site_id'))
        daily_wage = request.form.get('daily_wage') or None
        is_active = bool(request.form.get('is_active'))

        # Phone validation
        if phone and not re.fullmatch(r"\d{10}", phone):
            flash("Phone number must be exactly 10 digits.", "danger")
            return redirect(url_for("admin_bp.admin_edit_labour", labour_id=labour.id))

        # Bank account validation
        if bank_account and not re.fullmatch(r"\d+", bank_account):
            flash("Bank account number must contain digits only.", "danger")
            return redirect(url_for("admin_bp.admin_edit_labour", labour_id=labour.id))

        labour.name = name
        labour.phone = phone
        labour.bank_account = bank_account
        labour.ifsc_code = ifsc_code
        labour.site_id = site_id
        labour.daily_wage = daily_wage
        labour.is_active = is_active


        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(
                'Another labour with this phone number already exists for this site.',
                'danger'
            )
            return redirect(
                url_for('admin_bp.admin_edit_labour', labour_id=labour.id)
            )

        # AUDIT
        log_action(
            action='labour_updated',
            details=f"Labour '{labour.name}' updated",
            site_id=labour.site_id
        )

        flash('Labour updated successfully.', 'success')
        return redirect(url_for('admin_bp.admin_labours'))

    return render_template(
        'admin_edit_labour.html',
        labour=labour,
        sites=sites
    )


@admin_bp.route('/labours/<int:labour_id>/delete', methods=['POST'])
@login_required
def delete_labour(labour_id):
    if not _admin_required():
        return redirect(url_for('auth.login'))

    labour = Labour.query.get_or_404(labour_id)

    #  Check dependencies
    has_attendance = Attendance.query.filter_by(labour_id=labour.id).first()
    has_payments = Payment.query.filter_by(labour_id=labour.id).first()
    has_expenses = LabourMonthlyExpenses.query.filter_by(labour_id=labour.id).first()

    if has_attendance or has_payments or has_expenses:
        flash(
            f"Cannot delete labour '{labour.name}'. Attendance / payment history exists. "
            f"Deactivate instead.",
            "danger"
        )
        return redirect(url_for('admin_bp.admin_labours'))

    # Safe delete
    db.session.delete(labour)
    db.session.commit()

    #  Audit log
    log = AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        site_id=labour.site_id,
        action='labour_deleted',
        details=f"Labour '{labour.name}' deleted",
        ip_address=request.remote_addr,
        created_at=datetime.utcnow()
    )
    db.session.add(log)
    db.session.commit()

    flash('Labour deleted successfully', 'success')
    return redirect(url_for('admin_bp.admin_labours'))



# =========================
# PAYMENTS (ADVANCES ONLY)
# =========================

@admin_bp.route('/payments')
@login_required
def admin_payments():
    if not _admin_required():
        return redirect(url_for('auth.login'))

    payments = Payment.query.order_by(Payment.id.desc()).all()
    return render_template('admin_payments.html', payments=payments)


@admin_bp.route('/payments/add', methods=['GET', 'POST'])
@login_required
def admin_add_payment():
    if not _admin_required():
        return redirect(url_for('auth.login'))

    sites = Site.query.all()
    labours = Labour.query.all()

    # --- compute total advance per labour (for UI display only) ---
    labour_advances = {}
    for l in labours:
        total_adv = db.session.query(
            func.coalesce(func.sum(Payment.advance), 0.0)
        ).filter(Payment.labour_id == l.id).scalar()
        labour_advances[l.id] = float(total_adv or 0.0)

    if request.method == 'POST':
        payment = Payment(
            labour_id=_to_int(request.form.get('labour_id')),
            site_id=_to_int(request.form.get('site_id')),
            date=request.form.get('date'),
            advance=request.form.get('advance'),
            note=request.form.get('note'),
            created_by=current_user.id if current_user.is_authenticated else None
        )

        db.session.add(payment)
        db.session.commit()
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
    sites = Site.query.all()
    labours = Labour.query.all()

    if request.method == 'POST':
        # ❌ DO NOT change labour_id or site_id
        payment.date = request.form.get('date')
        payment.advance = request.form.get('advance') or 0
        payment.note = request.form.get('note')

        db.session.commit()
        flash('Payment updated successfully', 'success')
        return redirect(url_for('admin_bp.admin_payments'))

    return render_template(
        'admin_edit_payment.html',
        payment=payment,
        labours=labours,
        sites=sites
    )


@admin_bp.route('/payments/delete/<int:payment_id>', methods=['POST'])
@login_required
def delete_payment(payment_id):
    if not _admin_required():
        return redirect(url_for('auth.login'))

    payment = Payment.query.get_or_404(payment_id)
    db.session.delete(payment)
    db.session.commit()
    flash('Payment deleted successfully', 'success')
    return redirect(url_for('admin_bp.admin_payments'))



# Attendance report (view)
from datetime import datetime, date
from sqlalchemy import or_
from flask_login import login_required

@admin_bp.route('/attendance-report', methods=['GET'])
@login_required
def attendance_report():

    # ---------- INPUTS ----------
    site_id = request.args.get('site_id', type=int)
    start_date_raw = request.args.get('start_date')
    end_date_raw = request.args.get('end_date')

    day_shift = request.args.get('day_shift', 'all')          # all | present | absent
    night_shift = request.args.get('night_shift', 'all')      # all | present | absent
    worked_type = request.args.get('worked_type', 'any')      # any | day | night | both | any_worked

    # ---------- DATE PARSING ----------
    today = date.today()
    try:
        start_date = datetime.strptime(start_date_raw, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_raw, '%Y-%m-%d').date()
    except Exception:
        start_date = end_date = today

    # ---------- DEFAULT OUTPUT ----------
    records = []
    kpis = {
        'day_present': 0,
        'night_present': 0,
        'unique_labours': 0
    }

    # ---------- ONLY QUERY IF SITE SELECTED ----------
    if site_id:

        # BASE QUERY (DO NOT MUTATE)
        base_query = (
            Attendance.query
            .join(Labour)
            .filter(
                Attendance.site_id == site_id,
                Attendance.date >= start_date,
                Attendance.date <= end_date
            )
        )

        # ---------- KPIs (ALWAYS FROM BASE QUERY) ----------
        kpis['day_present'] = base_query.filter(
            Attendance.day_shift_flag == 1
        ).count()

        kpis['night_present'] = base_query.filter(
            Attendance.night_shift_flag == 1
        ).count()

        kpis['unique_labours'] = (
            base_query.filter(
                or_(
                    Attendance.day_shift_flag == 1,
                    Attendance.night_shift_flag == 1
                )
            )
            .with_entities(Attendance.labour_id)
            .distinct()
            .count()
        )

        # ---------- TABLE QUERY (SAFE TO MUTATE) ----------
        query = base_query

        # Day shift filter
        if day_shift == 'present':
            query = query.filter(Attendance.day_shift_flag == 1)
        elif day_shift == 'absent':
            query = query.filter(Attendance.day_shift_flag == 0)

        # Night shift filter
        if night_shift == 'present':
            query = query.filter(Attendance.night_shift_flag == 1)
        elif night_shift == 'absent':
            query = query.filter(Attendance.night_shift_flag == 0)

        # Worked type filter
        if worked_type == 'day':
            query = query.filter(Attendance.day_shift_flag == 1)
        elif worked_type == 'night':
            query = query.filter(Attendance.night_shift_flag == 1)
        elif worked_type == 'both':
            query = query.filter(
                Attendance.day_shift_flag == 1,
                Attendance.night_shift_flag == 1
            )
        elif worked_type == 'any_worked':
            query = query.filter(
                or_(
                    Attendance.day_shift_flag == 1,
                    Attendance.night_shift_flag == 1
                )
            )

        records = (
            query
            .order_by(Attendance.date.desc(), Attendance.labour_id.asc())
            .all()
        )

    sites = Site.query.order_by(Site.site_name.asc()).all()

    return render_template(
        'admin_attendance_report.html',
        records=records,
        sites=sites,
        kpis=kpis,
        filters={
            'site_id': site_id,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'day_shift': day_shift,
            'night_shift': night_shift,
            'worked_type': worked_type
        }
    )


# attendance export (CSV)
@admin_bp.route('/attendance-report/export')
@login_required
def export_attendance_report():
    if not _admin_required():
        return redirect(url_for('auth.login'))

    # reuse same filter logic
    site_id = request.args.get('site_id') or None
    start_date = request.args.get('start_date') or None
    end_date = request.args.get('end_date') or None
    day_shift_filter = request.args.get('day_shift') or None
    ot_filter = request.args.get('ot') or None

    d1 = None; d2 = None
    try:
        if start_date:
            d1 = datetime.strptime(start_date, "%Y-%m-%d").date()
    except: d1 = None
    try:
        if end_date:
            d2 = datetime.strptime(end_date, "%Y-%m-%d").date()
    except: d2 = None

    q = Attendance.query.join(Labour, Attendance.labour_id == Labour.id)
    if site_id:
        sid = _to_int(site_id)
        if sid:
            q = q.filter(Attendance.site_id == sid)
    if d1:
        q = q.filter(Attendance.date >= d1)
    if d2:
        q = q.filter(Attendance.date <= d2)
    if day_shift_filter:
        q = q.filter(Attendance.day_shift == day_shift_filter)
    if ot_filter:
        if ot_filter == "Yes":
            q = q.filter(Attendance.night_shift_flag == True)
        elif ot_filter == "No":
            q = q.filter(Attendance.night_shift_flag == False)
        elif ot_filter == "Worked":
            q = q.filter(or_(Attendance.day_shift_flag == True, Attendance.night_shift_flag == True))

    rows = q.order_by(Attendance.date.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id','date','labour_id','labour_name','site_id','day_shift','day_flag','night_shift','night_flag','note'])
    for r in rows:
        writer.writerow([
            r.id,
            r.date.isoformat() if r.date else '',
            r.labour_id,
            getattr(r, 'labour').name if getattr(r, 'labour', None) else '',
            r.site_id,
            r.day_shift,
            int(bool(r.day_shift_flag)),
            r.night_shift,
            int(bool(r.night_shift_flag)),
            r.note or ''
        ])
    csv_data = output.getvalue()
    output.close()
    filename = f"attendance_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(csv_data, mimetype='text/csv', headers={"Content-Disposition": f"attachment; filename={filename}"})

# reports page
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import func, and_
from flask_login import login_required

@admin_bp.route('/monthly-report', methods=['GET'])
@login_required
def monthly_report():

    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))

    site_id = request.args.get('site_id', type=int)
    month = request.args.get('month')          # YYYY-MM
    export = request.args.get('export', '0')

    sites = Site.query.order_by(Site.site_name.asc()).all()
    rows = []
    grand_total = Decimal('0.00')

    if site_id and month:
        start_date = datetime.strptime(month + '-01', '%Y-%m-%d').date()
        end_date = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1)


        attendance_subq = (
            db.session.query(
                Attendance.labour_id.label('labour_id'),

                func.sum(
                    case((Attendance.day_shift_flag == 1, 1), else_=0)
                ).label('day_shift'),

                func.sum(
                    case((Attendance.night_shift_flag == 1, 1), else_=0)
                ).label('night_shift'),
            )
            .filter(
                Attendance.site_id == site_id,
                Attendance.date >= start_date,
                Attendance.date < end_date
            )
            .group_by(Attendance.labour_id)
            .subquery()
        )







        data = (
            db.session.query(
                Labour.id,
                Labour.name.label('labour_name'),
                Site.site_name,
                Labour.bank_account,
                Labour.ifsc_code,
                Labour.daily_wage,

                
                func.coalesce(attendance_subq.c.day_shift, 0).label('day_shift'),
                func.coalesce(attendance_subq.c.night_shift, 0).label('night_shift'),

                func.coalesce(func.sum(Payment.advance), Decimal('0.00')).label('advance_paid'),
                func.coalesce(
                    LabourMonthlyExpenses.mess_amount +
                    LabourMonthlyExpenses.canteen_amount,
                    Decimal('0.00')
                ).label('expenses')
            )
            .join(attendance_subq, attendance_subq.c.labour_id == Labour.id)
            .join(Site, Site.id == Labour.site_id)


            .outerjoin(
                Payment,
                and_(
                    Payment.labour_id == Labour.id,
                    Payment.site_id == site_id,
                    Payment.date >= start_date,
                    Payment.date < end_date
                )
            )
            .outerjoin(
                LabourMonthlyExpenses,
                and_(
                    LabourMonthlyExpenses.labour_id == Labour.id,
                    LabourMonthlyExpenses.site_id == site_id,
                    LabourMonthlyExpenses.month == month
                )
            )
            .filter(Labour.is_active == True)
            .group_by(
                Labour.id,
                Labour.name,
                Site.site_name,
                Labour.bank_account,
                Labour.ifsc_code,
                Labour.daily_wage,
                LabourMonthlyExpenses.mess_amount,
                LabourMonthlyExpenses.canteen_amount
            )

            .order_by(Labour.name.asc())
            .all()
        )


        for r in data:
            day = int(r.day_shift or 0)
            night = int(r.night_shift or 0)

            total_shifts = day + night
            wage = Decimal(r.daily_wage or 0)

            total_pay = wage * total_shifts

            advance = Decimal(r.advance_paid or 0)
            expenses = Decimal(r.expenses or 0)

            net = total_pay - advance - expenses
            grand_total += net

            rows.append({
                'labour_name': r.labour_name,
                'site_name': r.site_name,
                'total_shifts': total_shifts, 
                'day_shift': day,
                'night_shift': night,
                'total_pay': total_pay,
                'advance_paid': advance,
                'expenses': expenses,
                'net_payable': net
            })



    # -------- EXCEL EXPORT --------
    # -------- EXCEL EXPORT --------
    if export == '1' and rows:
        df = pd.DataFrame(rows)

        df.insert(0, 'Sl. No.', range(1, len(df) + 1))

        df = df[[
            'Sl. No.',
            'labour_name',
            'total_shifts',
            'day_shift',
            'night_shift',
            'total_pay',
            'advance_paid',
            'expenses',
            'net_payable'
        ]]

        df.columns = [
            'Sl. No.',
            'Name',
            'Total Shifts',
            'Day Shift',
            'Night Shift',
            'Total Pay',
            'Advance Paid',
            'Expenses',
            'Net Payable'
        ]

        # TOTAL ROW (PROPER TOTALS)
        df.loc[len(df)] = [
            '',
            'TOTAL',
            df['Total Shifts'].sum(),
            df['Day Shift'].sum(),
            df['Night Shift'].sum(),
            df['Total Pay'].sum(),
            df['Advance Paid'].sum(),
            df['Expenses'].sum(),
            df['Net Payable'].sum()
        ]

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Monthly Payroll')

        output.seek(0)
        return Response(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={
                'Content-Disposition':
                'attachment;filename=Monthly_Payroll_Report.xlsx'
            }
        )

    return render_template(
        'monthly_report.html',
        sites=sites,
        rows=rows,
        selected_site=site_id,
        selected_month=month,
        grand_total=grand_total
    )


# ------------------------------
#--------Monthly EXPENSES-------
# -------------------------------

@admin_bp.route('/monthly-expenses')
@login_required
def admin_monthly_expenses():
    if current_user.role != 'admin':
        flash('Only Admin can add or view expenses', 'danger')
        return redirect(url_for('manager_bp.manager_dashboard'))

    site_id = request.args.get('site_id', type=int)
    month = request.args.get('month')  # YYYY-MM

    sites = Site.query.filter_by(is_active=True).all()
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

    expense = LabourMonthlyExpenses.query.filter_by(
        labour_id=labour_id,
        site_id=site_id,
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
            month=month,
            mess_amount=mess,
            canteen_amount=canteen,
            entered_by=current_user.id
        )
        db.session.add(expense)

    db.session.commit()
    return jsonify({'status': 'ok'})



@admin_bp.route('/audit-logs')
@login_required
def admin_audit_logs():
    if current_user.role != 'admin':
        flash('Access denied', 'danger')
        return redirect(url_for('admin_bp.admin_dashboard'))

    # Filters
    role = request.args.get('role')
    site_id = request.args.get('site_id')

    query = AuditLog.query

    if role:
        query = query.filter(AuditLog.role == role)

    if site_id:
        query = query.filter(AuditLog.site_id == site_id)

    logs = query.order_by(AuditLog.created_at.desc()).limit(500).all()

    sites = Site.query.all()

    return render_template(
    'admin_audit_logs.html',
    logs=logs,
    sites=sites,
    selected_role=role,
    selected_site=site_id,
    pytz=pytz   
    )



@admin_bp.route('/salary-sheet', methods=['GET'])
@login_required
def labour_salary_sheet():

    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))

    site_id = request.args.get('site_id', type=int)
    month = request.args.get('month')  # YYYY-MM
    export = request.args.get('export')

    sites = Site.query.order_by(Site.site_name.asc()).all()
    rows = []
    grand_total = Decimal('0.00')

    if site_id and month:
        start_date = datetime.strptime(month + '-01', '%Y-%m-%d').date()
        end_date = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1)

        attendance_subq = (
            db.session.query(
                Attendance.labour_id.label('labour_id'),

                func.sum(
                    case((Attendance.day_shift_flag == 1, 1), else_=0)
                ).label('day_shift'),

                func.sum(
                    case((Attendance.night_shift_flag == 1, 1), else_=0)
                ).label('night_shift')
            )
            .filter(
                Attendance.site_id == site_id,
                Attendance.date >= start_date,
                Attendance.date < end_date
            )
            .group_by(Attendance.labour_id)
            .subquery()
        )




        raw_rows = (
            db.session.query(
                Labour.name,
                Labour.bank_account,
                Labour.ifsc_code,
                Labour.daily_wage,

                func.coalesce(attendance_subq.c.day_shift, 0).label('day_shift'),
                func.coalesce(attendance_subq.c.night_shift, 0).label('night_shift')
            )
            .join(attendance_subq, attendance_subq.c.labour_id == Labour.id)
            .filter(Labour.is_active == True)
            .order_by(Labour.name.asc())
            .all()
        )



        for r in raw_rows:
            total_shifts = int(r.day_shift) + int(r.night_shift)
            total_pay = Decimal(r.daily_wage) * total_shifts

            rows.append({
                'name': r.name,
                'bank_account': r.bank_account,
                'ifsc_code': r.ifsc_code,
                'total_pay': total_pay
            })

            grand_total += total_pay



        # ---------- EXCEL EXPORT ----------
        if export == '1':
            df = pd.DataFrame(rows)
            df.insert(0, 'Sl. No.', range(1, len(df) + 1))
            df.rename(columns={
                'name': 'Name',
                'bank_account': 'Bank Account',
                'ifsc_code': 'IFSC Code',
                'total_pay': 'Total Pay'
            }, inplace=True)

            # ✅ TOTAL ROW (correct)
            df.loc[len(df)] = {
                'Sl. No.': '',
                'Name': 'TOTAL',
                'Bank Account': '',
                'IFSC Code': '',
                'Total Pay': grand_total
            }

            output = pd.ExcelWriter('salary_sheet.xlsx', engine='xlsxwriter')
            df.to_excel(output, index=False, sheet_name='Salary Sheet')
            output.close()

            return Response(
                open('salary_sheet.xlsx', 'rb'),
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                headers={'Content-Disposition': 'attachment;filename=Labour_Salary_Sheet.xlsx'}
            )


    return render_template(
        'salary_sheet.html',
        sites=sites,
        rows=rows,
        selected_site=site_id,
        selected_month=month,
        grand_total=grand_total
    )

#----------archive_audit_logs(days=180)---------------------------
from datetime import datetime
from dateutil.relativedelta import relativedelta
from models import AuditLog, AuditLogArchive


def archive_audit_logs_keep_last_3_months():
    now = datetime.utcnow()

    # First day of current month
    first_day_current_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Keep current + last 2 months → archive older than this
    cutoff = first_day_current_month - relativedelta(months=2)

    old_logs = AuditLog.query.filter(
        AuditLog.created_at < cutoff
    ).all()

    if not old_logs:
        return 0

    for log in old_logs:
        archived = AuditLogArchive(
            user_id=log.user_id,
            username=log.username,
            role=log.role,
            site_id=log.site_id,
            action=log.action,
            details=log.details,
            ip_address=log.ip_address,
            created_at=log.created_at
        )
        db.session.add(archived)
        db.session.delete(log)

    db.session.commit()
    return len(old_logs)

#----------MANUAL METHOD archive_audit_logs(days=180)---------------------------
@admin_bp.route('/audit/archive-now', methods=['POST'])
@login_required
def archive_audit_now():
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))

    count = archive_audit_logs(days=180)

    flash(f'{count} audit logs archived successfully.', 'success')
    return redirect(url_for('admin_bp.admin_audit_logs'))
