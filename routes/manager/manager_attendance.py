from flask import render_template, request, redirect, url_for, flash, abort, current_app
from flask_login import login_required, current_user
from datetime import date, datetime
from extensions import db
from models import Attendance, Labour, Site
from . import manager_bp
import json
from services.audit_service import log_audit
from calendar import monthrange
from sqlalchemy import func, or_, case



@manager_bp.route('/attendance', methods=['GET'])
@login_required
def manager_attendance():

    if not current_user.site_id:
        flash("You are not assigned to any site. Contact admin.", "danger")
        return redirect(url_for("manager_bp.manager_dashboard"))

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
        .filter(
            Labour.company_id == current_user.company_id,
            Labour.site_id == current_user.site_id,
            Labour.is_active == True
        )
        .order_by(Labour.name)
        .all()
    )


    attendance_map = {
        a.labour_id: a
        for a in Attendance.query.filter_by(
            company_id=current_user.company_id,
            site_id=current_user.site_id,
            date=selected_date
        ).all()
    }

    site = Site.query.get(current_user.site_id)

    return render_template(
        "manager_attendance.html",
        labours=labours,
        attendance_map=attendance_map,
        selected_date=selected_date,
        date=date,
        site_shift_rules={
        "morning": site.allow_morning_shift,
        "day": site.allow_day_shift,
        "night": site.allow_night_shift,
        }
    )


@manager_bp.route('/attendance/mark', methods=['POST'])
@login_required
def manager_mark_attendance():

    if not current_user.site_id:
        abort(403)

    selected_date = datetime.strptime(
        request.form['attendance_date'], "%Y-%m-%d"
    ).date()

    if selected_date > date.today():
        flash("Future attendance is not allowed", "danger")
        return redirect(url_for('manager_bp.manager_attendance'))

    # ---- FETCH SITE SHIFT RULES ----
    site = Site.query.get(current_user.site_id)

    allow_morning = bool(site.allow_morning_shift)
    allow_day = bool(site.allow_day_shift)
    allow_night = bool(site.allow_night_shift)



    changes = []  # 🔑 collect audit diffs here

    # 🚀 OPTIMIZATION: Pre-fetch site labours & existing attendance in 2 queries instead of 300+
    site_labours = {
        l.id: l
        for l in Labour.query.filter_by(
            company_id=current_user.company_id,
            site_id=current_user.site_id,
            is_active=True
        ).all()
    }

    existing_records = {
        a.labour_id: a
        for a in Attendance.query.filter_by(
            site_id=current_user.site_id,
            company_id=current_user.company_id,
            date=selected_date
        ).all()
    }

    for key, value in request.form.items():
        if not key.startswith("labour_"):
            continue

        parts = key.split("_")
        if len(parts) != 3:
            continue
        _, labour_id_str, shift = parts

        # ---- BLOCK DISALLOWED SHIFTS (SITE LEVEL) ----
        if shift == "morning" and not allow_morning:
            continue
        if shift == "day" and not allow_day:
            continue
        if shift == "night" and not allow_night:
            continue

        try:
            labour_id = int(labour_id_str)
        except ValueError:
            continue

        labour = site_labours.get(labour_id)
        if not labour:
            continue

        record = existing_records.get(labour_id)

        # --- capture BEFORE state ---
        before_morning = record.morning_shift_flag if record else 0.0
        before_day = record.day_shift_flag if record else 0.0
        before_night = record.night_shift_flag if record else 0.0

        if not record:
            record = Attendance(
                labour_id=labour_id,
                site_id=current_user.site_id,
                company_id=current_user.company_id,
                date=selected_date,
                morning_shift_flag=0.0,
                day_shift_flag=0.0,
                night_shift_flag=0.0
            )
            db.session.add(record)
            existing_records[labour_id] = record

        # --- apply change ---
        numeric_val = 1.0 if value == "present" else (0.5 if value == "half" else 0.0)

        if shift == "morning":
            record.morning_shift_flag = numeric_val
        elif shift == "day":
            record.day_shift_flag = numeric_val
        elif shift == "night":
            record.night_shift_flag = numeric_val

        # --- capture AFTER state ---
        after_morning = record.morning_shift_flag
        after_day = record.day_shift_flag
        after_night = record.night_shift_flag

        # --- detect real change only ---
        def _get_status_label(val):
            if val >= 1.0: return "Present"
            if val == 0.5: return "Half Day"
            return "Absent"

        if (
            before_morning != after_morning or
            before_day != after_day or
            before_night != after_night
        ):
            changes.append({
                "labour_id": labour_id,
                "labour_name": labour.name,
                "before": {
                    "morning": _get_status_label(before_morning),
                    "day": _get_status_label(before_day),
                    "night": _get_status_label(before_night),
                },
                "after": {
                    "morning": _get_status_label(after_morning),
                    "day": _get_status_label(after_day),
                    "night": _get_status_label(after_night),
                }
            })

    # ---- FORCE DISABLED SHIFTS TO ZERO (SAFETY NET) ----
    if not allow_morning:
        Attendance.query.filter_by(
            site_id=current_user.site_id,
            date=selected_date
        ).update({Attendance.morning_shift_flag: 0.0})

    if not allow_day:
        Attendance.query.filter_by(
            site_id=current_user.site_id,
            date=selected_date
        ).update({Attendance.day_shift_flag: 0.0})

    if not allow_night:
        Attendance.query.filter_by(
            site_id=current_user.site_id,
            date=selected_date
        ).update({Attendance.night_shift_flag: 0.0})

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to commit attendance: {e}")
        flash("Database error saving attendance. Please try again.", "danger")
        return redirect(
            url_for("manager_bp.manager_attendance", date=selected_date.isoformat())
        )

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
    total_labours = Labour.query.filter(
        Labour.company_id == current_user.company_id,
        Labour.site_id == current_user.site_id,
        Labour.is_active == True
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
                                Attendance.morning_shift_flag > 0,
                                Attendance.day_shift_flag > 0,
                                Attendance.night_shift_flag > 0
                            ),
                            Attendance.labour_id
                        ),
                        else_=None
                    )
                )
            ).label('present_count'),

            # shift-wise counts
            func.sum(Attendance.morning_shift_flag).label('morning_count'),
            func.sum(Attendance.day_shift_flag).label('day_count'),
            func.sum(Attendance.night_shift_flag).label('night_count')
        )

        .filter(
            Attendance.company_id == current_user.company_id,
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

        morning = float(r.morning_count or 0) if r else 0.0
        day = float(r.day_count or 0) if r else 0.0
        night = float(r.night_count or 0) if r else 0.0
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