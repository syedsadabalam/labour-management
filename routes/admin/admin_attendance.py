from datetime import datetime, timedelta, date
from . import admin_bp
from datetime import datetime, date
from sqlalchemy import or_
from .utils import _admin_required, _to_int

from flask import render_template, request, redirect, url_for, Response
from flask_login import login_required, current_user
from models import Attendance, Labour, Site
from extensions import db
import csv, io

from decimal import Decimal
from sqlalchemy import func, and_ , case
from calendar import monthrange


@admin_bp.route('/attendance-report', methods=['GET'])
@login_required
def attendance_report():

    page = request.args.get('page', 1, type=int)
    PER_PAGE = 100

    pagination = None
    records = []



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
        'morning_present': 0,
        'day_present': 0,
        'night_present': 0,
        'unique_labours': 0
    }

    # ---------- ONLY QUERY IF SITE SELECTED ----------
    if site_id:
        # Ensure site belongs to current admin's company (Multi-tenancy isolation)
        site_obj = Site.query.filter_by(id=site_id, company_id=current_user.company_id).first()
        if not site_obj:
            site_id = None

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
        kpis['morning_present'] = base_query.filter(
            Attendance.morning_shift_flag > 0
        ).count()

        kpis['day_present'] = base_query.filter(
            Attendance.day_shift_flag > 0
        ).count()

        kpis['night_present'] = base_query.filter(
            Attendance.night_shift_flag > 0
        ).count()

        kpis['unique_labours'] = (
            base_query.filter(
                or_(
                    Attendance.morning_shift_flag > 0,
                    Attendance.day_shift_flag > 0,
                    Attendance.night_shift_flag > 0
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
            query = query.filter(Attendance.day_shift_flag > 0)
        elif day_shift == 'absent':
            query = query.filter(Attendance.day_shift_flag == 0)

        # Night shift filter
        if night_shift == 'present':
            query = query.filter(Attendance.night_shift_flag > 0)
        elif night_shift == 'absent':
            query = query.filter(Attendance.night_shift_flag == 0)

        # Worked type filter
        if worked_type == 'day':
            query = query.filter(Attendance.day_shift_flag > 0)
        elif worked_type == 'night':
            query = query.filter(Attendance.night_shift_flag > 0)
        elif worked_type == 'multiple':
            query = query.filter(
                (
                    Attendance.morning_shift_flag +
                    Attendance.day_shift_flag +
                    Attendance.night_shift_flag
                ) >= 2
            )
        elif worked_type == 'any_worked':
            query = query.filter(
                or_(
                    Attendance.morning_shift_flag > 0,
                    Attendance.day_shift_flag > 0,
                    Attendance.night_shift_flag > 0
                )
            )


        pagination = (
            query
            .order_by(Attendance.date.desc(), Attendance.labour_id.asc())
            .paginate(page=page, per_page=PER_PAGE, error_out=False)
        )

        records = pagination.items

    sites = Site.query.filter_by(
        company_id=current_user.company_id
    ).order_by(Site.site_name.asc()).all()


    return render_template(
        'admin_attendance_report.html',
        records=records,
        pagination=pagination,
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

    q = (
        Attendance.query
        .join(Labour, Attendance.labour_id == Labour.id)
        .filter(Labour.company_id == current_user.company_id)
    )
    if site_id:
        sid = _to_int(site_id)
        if sid:
            site_obj = Site.query.filter_by(id=sid, company_id=current_user.company_id).first()
            if site_obj:
                q = q.filter(Attendance.site_id == sid)
            else:
                return redirect(url_for('admin_bp.attendance_report'))
    if d1:
        q = q.filter(Attendance.date >= d1)
    if d2:
        q = q.filter(Attendance.date <= d2)
    if day_shift_filter:
        if day_shift_filter == 'present':
            q = q.filter(Attendance.day_shift_flag > 0)
        elif day_shift_filter == 'absent':
            q = q.filter(Attendance.day_shift_flag == 0)
        elif day_shift_filter == 'half':
            q = q.filter(Attendance.day_shift_flag == 0.5)
    if ot_filter:
        if ot_filter == "Yes":
            q = q.filter(Attendance.night_shift_flag > 0)
        elif ot_filter == "No":
            q = q.filter(Attendance.night_shift_flag == 0.0)
        elif ot_filter == "Worked":
            q = q.filter(or_(Attendance.day_shift_flag > 0, Attendance.night_shift_flag > 0))

    rows = q.order_by(Attendance.date.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id','date','labour_id','labour_name','site_id','morning_shift_flag','day_shift_flag','night_shift_flag','note'])
    for r in rows:
        writer.writerow([
            r.id,
            r.date.isoformat() if r.date else '',
            r.labour_id,
            getattr(r, 'labour').name if getattr(r, 'labour', None) else '',
            r.site_id,
            float(r.morning_shift_flag),
            float(r.day_shift_flag),
            float(r.night_shift_flag),
            r.note or ''
        ])
    csv_data = output.getvalue()
    output.close()
    filename = f"attendance_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(csv_data, mimetype='text/csv', headers={"Content-Disposition": f"attachment; filename={filename}"})

# monthly attandences

@admin_bp.route("/sites/<int:site_id>/monthly-attendance")
@login_required
def admin_monthly_attendance(site_id):

    if current_user.role != "admin":
        return redirect(url_for("auth.login"))

    site = Site.query.filter_by(
        id=site_id,
        company_id=current_user.company_id
    ).first_or_404()

    today = date.today()

    # ---------- Month handling (YYYY-MM) ----------
    month_str = request.args.get("month")
    if month_str:
        try:
            start_date = datetime.strptime(month_str, "%Y-%m").date().replace(day=1)
        except ValueError:
            start_date = today.replace(day=1)
    else:
        start_date = today.replace(day=1)

    # Block future months
    if start_date > today.replace(day=1):
        start_date = today.replace(day=1)

    # End date = first day of next month
    if start_date.month == 12:
        end_date = date(start_date.year + 1, 1, 1)
    else:
        end_date = date(start_date.year, start_date.month + 1, 1)

    # ---------- Total active labours ----------
    total_labours = Labour.query.filter_by(
        site_id=site.id,
        is_active=True
    ).count()

    stats_rows = (
        db.session.query(
            Attendance.date,
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
            ).label("present"),
            func.coalesce(func.sum(Attendance.morning_shift_flag), 0.0).label("morning"),
            func.coalesce(func.sum(Attendance.day_shift_flag), 0.0).label("day"),
            func.coalesce(func.sum(Attendance.night_shift_flag), 0.0).label("night"),
        )
        .filter(
            Attendance.site_id == site.id,
            Attendance.date >= start_date,
            Attendance.date < end_date
        )
        .group_by(Attendance.date)
        .all()
    )

    stats_map = {
        row.date: {
            "present": int(row.present or 0),
            "morning": float(row.morning or 0.0),
            "day": float(row.day or 0.0),
            "night": float(row.night or 0.0),
            "total_shifts": float((row.morning or 0.0) + (row.day or 0.0) + (row.night or 0.0)),
        }
        for row in stats_rows
    }

    daily_stats = []
    current_day = start_date
    while current_day < end_date:
        day_data = stats_map.get(current_day, {
            "present": 0,
            "morning": 0.0,
            "day": 0.0,
            "night": 0.0,
            "total_shifts": 0.0,
        })
        daily_stats.append({
            "date": current_day,
            **day_data
        })
        current_day += timedelta(days=1)

    return render_template(
        "admin_monthly_attendance.html",
        site=site,
        daily_stats=daily_stats,
        selected_month=start_date.strftime("%Y-%m"),
        today=today.strftime("%Y-%m")
    )