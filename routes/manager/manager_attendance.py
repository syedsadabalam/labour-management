from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import date, datetime
from extensions import db
from models import Attendance, Labour
from . import manager_bp
import json
from services.audit_service import log_audit
from calendar import monthrange
from sqlalchemy import func, or_, case



@manager_bp.route('/attendance', methods=['GET'])
@login_required
def manager_attendance():
    selected_date_str = request.args.get('date')
    selected_date = (
        datetime.strptime(selected_date_str, "%Y-%m-%d").date()
        if selected_date_str
        else date.today()
    )

    if selected_date > date.today():
        flash("Future attendance is not allowed", "danger")
        return redirect(url_for('manager_bp.manager_attendance'))

    labours = (
        Labour.query
        .filter_by(site_id=current_user.site_id, is_active=True)
        .order_by(Labour.name)
        .all()
    )

    attendance_map = {
        a.labour_id: a
        for a in Attendance.query.filter_by(
            site_id=current_user.site_id,
            date=selected_date
        ).all()
    }

    return render_template(
        "manager_attendance.html",
        labours=labours,
        attendance_map=attendance_map,
        selected_date=selected_date,
        date=date
    )


@manager_bp.route('/attendance/mark', methods=['POST'])
@login_required
def manager_mark_attendance():
    selected_date = datetime.strptime(
        request.form['attendance_date'], "%Y-%m-%d"
    ).date()

    if selected_date > date.today():
        flash("Future attendance is not allowed", "danger")
        return redirect(url_for('manager_bp.manager_attendance'))

    changes = []  # 🔑 collect audit diffs here

    for key, value in request.form.items():
        if not key.startswith("labour_"):
            continue

        _, labour_id, shift = key.split("_")
        labour_id = int(labour_id)

        record = Attendance.query.filter_by(
            labour_id=labour_id,
            site_id=current_user.site_id,
            date=selected_date
        ).first()

        # --- capture BEFORE state ---
        before_morning = record.morning_shift_flag if record else 0
        before_day = record.day_shift_flag if record else 0
        before_night = record.night_shift_flag if record else 0

        if not record:
            record = Attendance(
                labour_id=labour_id,
                site_id=current_user.site_id,
                company_id=current_user.company_id,
                date=selected_date,
                morning_shift_flag=0,
                day_shift_flag=0,
                night_shift_flag=0
            )
            db.session.add(record)

        # --- apply change ---
        if shift == "morning":
            record.morning_shift_flag = 1 if value == "present" else 0
        elif shift == "day":
            record.day_shift_flag = 1 if value == "present" else 0
        elif shift == "night":
            record.night_shift_flag = 1 if value == "present" else 0

        # --- capture AFTER state ---
        after_morning = record.morning_shift_flag
        after_day = record.day_shift_flag
        after_night = record.night_shift_flag

        # --- detect real change only ---
        if (
            before_morning != after_morning or
            before_day != after_day or
            before_night != after_night):
            labour = Labour.query.get(labour_id)
            changes.append({
                "labour_id": labour_id,
                "labour_name": labour.name if labour else "Unknown",
                "before": {
                    "morning": "Present" if before_morning else "Absent",
                    "day": "Present" if before_day else "Absent",
                    "night": "Present" if before_night else "Absent",
                },
                "after": {
                    "morning": "Present" if after_morning else "Absent",
                    "day": "Present" if after_day else "Absent",
                    "night": "Present" if after_night else "Absent",
                }
            })


    db.session.commit()

    # --- AUDIT LOG (ONLY IF SOMETHING CHANGED) ---
    if changes:
        log_audit(
            company_id=current_user.company_id,
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            site_id=current_user.site_id,
            action="mark_attendance",
            details=json.dumps({
                "date": selected_date.isoformat(),
                "changed_count": len(changes),
                "changes": changes
            }, 
            ensure_ascii=False),
            ip_address=request.remote_addr
        )

    flash("Attendance saved successfully", "success")
    return redirect(
        url_for(
            "manager_bp.manager_attendance",
            date=selected_date.isoformat()
        )
    )

@manager_bp.route('/attendance/monthly')
@login_required
def manager_monthly_attendance():

    # 🔐 Role safety
    if current_user.role != 'manager':
        return redirect(url_for('auth.login'))

    today = date.today()

    # 📅 Month picker value (YYYY-MM)
    month_picker = request.args.get('month_picker')

    if month_picker:
        try:
            year, month = map(int, month_picker.split('-'))
        except ValueError:
            year, month = today.year, today.month
    else:
        year, month = today.year, today.month

    # 🚫 Block future months
    if (year, month) > (today.year, today.month):
        year, month = today.year, today.month

    start_date = date(year, month, 1)
    end_date = date(year, month, monthrange(year, month)[1])

    # 👷 Total active labours
    total_labours = Labour.query.filter_by(
        site_id=current_user.site_id,
        is_active=True
    ).count()

    # 📊 Attendance aggregation
    rows = (
        db.session.query(
            Attendance.date.label('date'),

            # ✅ UNIQUE LABOURS PRESENT (ANY SHIFT)
            func.count(
                func.distinct(
                    case(
                        (
                            or_(
                                Attendance.morning_shift_flag == 1,
                                Attendance.day_shift_flag == 1,
                                Attendance.night_shift_flag == 1
                            ),
                            Attendance.labour_id
                        ),
                        else_=None
                    )
                )
            ).label('present_count'),

            # shift-wise counts
            func.sum(case((Attendance.morning_shift_flag == True, 1), else_=0)).label('morning_count'),
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

        morning = int(r.morning_count) if r else 0
        day = int(r.day_count) if r else 0
        night = int(r.night_count) if r else 0
        present = int(r.present_count) if r else 0

        total_shifts = morning + day + night

        daily_stats.append({
            "date": current_date,
            "present": present,
            "total_shifts": total_shifts,
            "morning": morning,
            "day": day,
            "night": night
        })


    return render_template(
        'manager_monthly_attendance.html',
        daily_stats=daily_stats,
        total_labours=total_labours,
        year=year,
        month=month,
        now=today  
    )