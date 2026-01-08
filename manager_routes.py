# manager_routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from datetime import datetime, date
from sqlalchemy import or_
from datetime import date, timedelta
from sqlalchemy import and_, or_
from models import db, Site, Labour, Attendance, Payment, log_event

from calendar import monthrange
from sqlalchemy import func, case


manager_bp = Blueprint('manager_bp', __name__, url_prefix='/manager', template_folder='templates')


day_shift_map = {
    'day': 'Day Shift',
    'night': 'Night Shift'
}

night_shift_map = {
    'present': 'Present',
    'absent': 'Absent'
}

from flask import request
from datetime import datetime
from models import AuditLog


def log_action(user, action, details=None, site_id=None):
    log = AuditLog(
        user_id=user.id if user else None,
        username=user.username if user else None,
        role=user.role if user else None,
        site_id=site_id,
        action=action,
        details=details,
        ip_address=request.remote_addr,
        created_at=datetime.utcnow()
    )
    db.session.add(log)




def _manager_required():
    if not current_user.is_authenticated or getattr(current_user, 'role', None) != 'manager':
        flash('Unauthorized', 'danger')
        return False
    return True

from datetime import datetime
from sqlalchemy import func, or_
from flask import render_template, redirect, url_for
from flask_login import login_required, current_user

@manager_bp.route('/dashboard')
@login_required
def manager_dashboard():
    if not _manager_required():
        return redirect(url_for('auth.login'))

    site_id = current_user.site_id
    today = datetime.utcnow().date()

    # 1️⃣ Total Active Labours (site-specific)
    total_labours = Labour.query.filter_by(
        site_id=site_id,
        is_active=True
    ).count()

    # 2️⃣ Today Present (day OR night shift)
    today_present = (
        Attendance.query
        .join(Labour)
        .filter(
            Labour.site_id == site_id,
            Attendance.date == today,
            or_(
                Attendance.day_shift_flag == True,
                Attendance.night_shift_flag == True
            )
        )
        .count()
    )

    # 3️⃣ Today Absent
    today_absent = max(total_labours - today_present, 0)

        # first day of current month
    month_start = today.replace(day=1)

    # 4️⃣ Advances Given This Month
    advances_month = (
        db.session.query(func.coalesce(func.sum(Payment.advance), 0))
        .join(Labour)
        .filter(
            Labour.site_id == site_id,
            Payment.date >= month_start,
            Payment.date <= today
        )
        .scalar()
    )

    # 5️⃣ Attendance marked today?
    attendance_marked = (
        Attendance.query
        .join(Labour)
        .filter(
            Labour.site_id == site_id,
            Attendance.date == today
        )
        .count() > 0
    )

    # 6️⃣ Recent Activity (last 5 actions)
    recent_attendance = (
        Attendance.query
        .join(Labour)
        .filter(Labour.site_id == site_id)
        .order_by(Attendance.date.desc(), Attendance.id.desc())
        .limit(50)
        .all()
    )

    recent_payments = (
        Payment.query
        .join(Labour)
        .filter(Labour.site_id == site_id)
        .order_by(Payment.date.desc(), Payment.id.desc())
        .limit(50)
        .all()
    )

    

    yesterday = date.today() - timedelta(days=1)

    # All active labours for this manager's site
    active_labours = Labour.query.filter_by(
        site_id=current_user.site_id,
        is_active=True
    ).all()

    # Attendance for yesterday (mapped by labour_id)
    attendance_yesterday = {
        a.labour_id: a
        for a in Attendance.query.filter(
            Attendance.site_id == current_user.site_id,
            Attendance.date == yesterday
        ).all()
    }

    yesterday_absent = []

    for labour in active_labours:
        att = attendance_yesterday.get(labour.id)

        # ABSENT if no record OR both shifts false
        if not att or (not att.day_shift_flag and not att.night_shift_flag):
            yesterday_absent.append({
                "id": labour.id,
                "name": labour.name
            })

    

    today = date.today()

    advances_today = (
        db.session.query(func.coalesce(func.sum(Payment.advance), 0))
        .filter(
            Payment.site_id == current_user.site_id,
            Payment.date == today
        )
        .scalar()
    ) or 0



    return render_template(
        'manager_dashboard.html',
        total_labours=total_labours,
        today_present=today_present,
        today_absent=today_absent,
        advances_month=advances_month,
        attendance_marked=attendance_marked,
        recent_attendance=recent_attendance,
        recent_payments=recent_payments,
        yesterday_absent=yesterday_absent,
        yesterday_absent_count=len(yesterday_absent),
        yesterday_date=yesterday,
        advances_today=advances_today

    )


@manager_bp.route('/labours')
@login_required
def labours():
    if not _manager_required():
        return redirect(url_for('auth.login'))

    search = (request.args.get('search') or '').strip()

    query = Labour.query.filter(Labour.site_id == current_user.site_id)

    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                Labour.name.ilike(like),
                Labour.phone.ilike(like),
                Labour.bank_account.ilike(like),
                Labour.ifsc_code.ilike(like)
            )
        )

    labours = query.order_by(Labour.id.desc()).all()

    return render_template(
        'manager_labours.html',
        labours=labours,
        search=search
    )


# ===============================
# MARK ATTENDANCE (GRID)
# ===============================
from datetime import datetime, date
import json

@manager_bp.route('/attendance/mark', methods=['GET', 'POST'])
@login_required
def mark_attendance():
    if current_user.role != 'manager':
        return redirect(url_for('auth.login'))

    selected_date = request.args.get('date') or request.form.get('date')
    if not selected_date:
        selected_date = date.today().isoformat()

    date_obj = datetime.strptime(selected_date, '%Y-%m-%d').date()
    site_id = current_user.site_id

    labours = Labour.query.filter_by(site_id=site_id, is_active=True).all()

    if request.method == 'POST':

        changes = []  #  THIS IS THE KEY
        changed_count = 0

        for labour in labours:
            day_flag = int(request.form.get(f'day_shift_{labour.id}', 0))
            night_flag = int(request.form.get(f'night_shift_{labour.id}', 0))

            attendance = Attendance.query.filter_by(
                labour_id=labour.id,
                date=date_obj
            ).first()

            before = {
                "day": "Present" if attendance and attendance.day_shift_flag else "Absent",
                "night": "Present" if attendance and attendance.night_shift_flag else "Absent"
            }

            after = {
                "day": "Present" if day_flag else "Absent",
                "night": "Present" if night_flag else "Absent"
            }

            if attendance:
                if attendance.day_shift_flag != bool(day_flag) or attendance.night_shift_flag != bool(night_flag):
                    attendance.day_shift_flag = bool(day_flag)
                    attendance.night_shift_flag = bool(night_flag)

                    changes.append({
                        "labour_id": labour.id,
                        "labour_name": labour.name,
                        "before": before,
                        "after": after,
                        "note": "updated"
                    })
                    changed_count += 1
            else:
                attendance = Attendance(
                    labour_id=labour.id,
                    site_id=site_id,
                    date=date_obj,
                    day_shift_flag=bool(day_flag),
                    night_shift_flag=bool(night_flag)
                )
                db.session.add(attendance)

                changes.append({
                    "labour_id": labour.id,
                    "labour_name": labour.name,
                    "before": {"day": "Absent", "night": "Absent"},
                    "after": after,
                    "note": "created"
                })
                changed_count += 1

        db.session.commit()

        #  STRUCTURED AUDIT LOG
        audit_payload = {
            "date": selected_date,
            "changed_count": changed_count,
            "changes": changes
        }

        log = AuditLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            site_id=site_id,
            action='mark_attendance',
            details=json.dumps(audit_payload, ensure_ascii=False),
            ip_address=request.remote_addr,
            created_at=datetime.utcnow()
        )

        db.session.add(log)
        db.session.commit()

        flash('Attendance saved successfully', 'success')
        return redirect(url_for('manager_bp.mark_attendance', date=selected_date))

    # LOAD EXISTING ATTENDANCE
    attendances = Attendance.query.filter_by(
        site_id=site_id,
        date=date_obj
    ).all()

    attendance_map = {a.labour_id: a for a in attendances}

    return render_template(
        'mark_attendance.html',
        labours=labours,
        attendance_map=attendance_map,
        selected_date=selected_date,
        today=date.today().isoformat()
    )




@manager_bp.route('/attendance/monthly')
@login_required
def manager_monthly_attendance():
    if current_user.role != 'manager':
        return redirect(url_for('auth.login'))

    # Month selection (default: current month)
    year = request.args.get('year', date.today().year, type=int)
    month = request.args.get('month', date.today().month, type=int)

    start_date = date(year, month, 1)
    end_date = date(year, month, monthrange(year, month)[1])

    # Total active labours at this site
    total_labours = Labour.query.filter_by(
        site_id=current_user.site_id,
        is_active=True
    ).count()

    # Date-wise aggregation
    rows = (
        db.session.query(
            Attendance.date.label('date'),
            func.sum(case((Attendance.day_shift_flag == True, 1), else_=0)).label('day_count'),
            func.sum(case((Attendance.night_shift_flag == True, 1), else_=0)).label('night_count')
        )
        .filter(
            Attendance.site_id == current_user.site_id,
            Attendance.date >= start_date,
            Attendance.date <= end_date
        )
        .group_by(Attendance.date)
        .order_by(Attendance.date)
        .all()
    )

    attendance_map = {r.date: r for r in rows}

    daily_stats = []

    for d in range(1, end_date.day + 1):
        current_date = date(year, month, d)
        r = attendance_map.get(current_date)

        day = int(r.day_count) if r else 0
        night = int(r.night_count) if r else 0
        present = day + night
        absent = max(total_labours - present, 0)

        daily_stats.append({
            "date": current_date,
            "present": present,
            "absent": absent,
            "day": day,
            "night": night
        })

    return render_template(
        'manager_monthly_attendance.html',
        daily_stats=daily_stats,
        total_labours=total_labours,
        year=year,
        month=month
    )




@manager_bp.route('/payments/add', methods=['GET', 'POST'])
@login_required
def add_payment():
    if not _manager_required():
        return redirect(url_for('auth.login'))

    # Only active labours of this manager's site
    labours = Labour.query.filter_by(
        site_id=current_user.site_id,
        is_active=True
    ).all()

    if request.method == 'POST':
        labour_id = request.form.get('labour_id')
        date_str = request.form.get('date')
        advance_str = request.form.get('advance')
        note = request.form.get('note')

        # ---------- VALIDATIONS ----------
        if not labour_id or not advance_str:
            flash('Labour and advance amount are required', 'danger')
            return redirect(url_for('manager_bp.add_payment'))

        try:
            advance = float(advance_str)
            if advance <= 0:
                raise ValueError
        except ValueError:
            flash('Advance amount must be a positive number', 'danger')
            return redirect(url_for('manager_bp.add_payment'))

        try:
            date_obj = (
                datetime.strptime(date_str, '%Y-%m-%d').date()
                if date_str else datetime.utcnow().date()
            )
        except ValueError:
            flash('Invalid date format', 'danger')
            return redirect(url_for('manager_bp.add_payment'))

        # Block future dates
        if date_obj > datetime.utcnow().date():
            flash('Future dates are not allowed', 'danger')
            return redirect(url_for('manager_bp.add_payment'))

        # Ensure labour belongs to same site (SECURITY)
        labour = Labour.query.filter_by(
            id=labour_id,
            site_id=current_user.site_id
        ).first()

        if not labour:
            flash('Invalid labour selected', 'danger')
            return redirect(url_for('manager_bp.add_payment'))

        # ---------- SAVE ----------
        payment = Payment(
            labour_id=labour.id,
            site_id=current_user.site_id,
            date=date_obj,
            advance=advance,
            note=note,
            created_by_id=current_user.id
        )

        db.session.add(payment)
        db.session.commit()

        flash('Advance payment added successfully', 'success')
        return redirect(url_for('manager_bp.payment_history'))

    # GET
    today = datetime.utcnow().date().isoformat()
    return render_template(
        'manager_add_payment.html',
        labours=labours,
        today=today
    )



@manager_bp.route('/payments/history')
@login_required
def payment_history():
    if not _manager_required():
        return redirect(url_for('auth.login'))

    payments = (
        Payment.query
        .join(Labour)
        .filter(Labour.site_id == current_user.site_id)
        .order_by(Payment.date.desc(), Payment.id.desc())
        .all()
    )

    return render_template(
        'manager_payment_history.html',
        payments=payments
    )


# =========================================================
# MANAGER – LABOUR MONTHLY SUMMARY (READ ONLY)
# =========================================================

from flask import jsonify

@manager_bp.route('/api/labour/<int:labour_id>/monthly-summary')
@login_required
def manager_labour_monthly_summary(labour_id):

    # ---- Role check ----
    if not _manager_required():
        return jsonify({"error": "Unauthorized"}), 403

    month = request.args.get('month')  # YYYY-MM
    if not month:
        return jsonify({"error": "Month is required"}), 400

    # ---- Parse month ----
    try:
        year, mon = map(int, month.split('-'))
        start_date = date(year, mon, 1)
        if mon == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, mon + 1, 1)
    except Exception:
        return jsonify({"error": "Invalid month"}), 400

    # ---- Labour (STRICT site filter) ----
    labour = Labour.query.filter_by(
        id=labour_id,
        site_id=current_user.site_id
    ).first_or_404()

    # ---- Attendance ----
    attendance_rows = Attendance.query.filter(
        Attendance.labour_id == labour_id,
        Attendance.site_id == current_user.site_id,
        Attendance.date >= start_date,
        Attendance.date < end_date
    ).order_by(Attendance.date).all()

    day_shifts = 0
    night_shifts = 0
    absent_days = 0
    calendar = []

    for r in attendance_rows:
        worked = False

        if r.day_shift_flag:
            day_shifts += 1
            worked = True

        if r.night_shift_flag:
            night_shifts += 1
            worked = True

        if not worked:
            absent_days += 1

        calendar.append({
            "date": r.date.isoformat(),
            "status": "PRESENT" if worked else "ABSENT"
        })

    total_shifts = day_shifts + night_shifts

    # ---- Earnings (read-only) ----
    daily_wage = float(labour.daily_wage or 0)
    earned_pay = daily_wage * total_shifts

    # ---- Advances (read-only) ----
    advance_paid = (
        db.session.query(func.coalesce(func.sum(Payment.advance), 0))
        .filter(
            Payment.labour_id == labour_id,
            Payment.site_id == current_user.site_id,
            Payment.date < end_date
        )
        .scalar()
    ) or 0

    # ---- Net payable ----
    net_payable = earned_pay - advance_paid

    return jsonify({
        "labour": {
            "name": labour.name,
            "phone": labour.phone,
            "site": labour.site.site_name if labour.site else "-"
        },
        "attendance_summary": {
            "day_shifts": day_shifts,
            "night_shifts": night_shifts,
            "total_shifts": total_shifts,
            "absent_days": absent_days
        },
        "payment_summary": {
            "daily_wage": daily_wage,
            "earned_pay": earned_pay,
            "advance_paid": advance_paid,
            "mess_canteen": 0,          # managers don’t manage this
            "net_payable": net_payable
        },
        "calendar": calendar
    })
