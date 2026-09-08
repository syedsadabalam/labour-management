from datetime import date, timedelta
from decimal import Decimal
import calendar
from sqlalchemy import func, case, or_
from extensions import db
from models import Site, User, Labour, Attendance, Payment


def D(val):
    try:
        if val is None:
            return Decimal("0.00")
        return Decimal(str(val))
    except Exception:
        return Decimal("0.00")


def get_admin_site_dashboard(site_id: int, company_id: int) -> dict:
    today = date.today()
    yesterday = today - timedelta(days=1)

    # -----------------------------
    # SITE & MANAGER
    # -----------------------------
    site = Site.query.filter_by(id=site_id, company_id=company_id).first()
    if not site:
        return None

    manager = (
        User.query
        .filter(User.site_id == site_id, User.role == "manager")
        .first()
    )

    # -----------------------------
    # TOTAL LABOURS (BASE METRIC)
    # -----------------------------
    total_labours = (
        Labour.query
        .filter(
            Labour.site_id == site_id,
            Labour.is_active.is_(True)
        )
        .count()
    )

    # -----------------------------
    # ATTENDANCE RECORDED CHECK TODAY
    # -----------------------------
    today_attendance_record_count = (
        db.session.query(func.count(Attendance.id))
        .filter(
            Attendance.site_id == site_id,
            Attendance.date == today
        )
        .scalar()
    ) or 0
    attendance_marked_today = today_attendance_record_count > 0

    # -----------------------------
    # PRESENT TODAY
    # -----------------------------
    present_today = (
        db.session.query(func.count(func.distinct(Attendance.labour_id)))
        .filter(
            Attendance.site_id == site_id,
            Attendance.date == today,
            or_(
                Attendance.morning_shift_flag > 0,
                Attendance.day_shift_flag > 0,
                Attendance.night_shift_flag > 0
            )
        )
        .scalar()
    ) or 0

    # -----------------------------
    # SHIFTS TODAY (BREAKDOWN)
    # -----------------------------
    morning_shifts_today = (
        db.session.query(func.coalesce(func.sum(Attendance.morning_shift_flag), 0.0))
        .filter(Attendance.site_id == site_id, Attendance.date == today)
        .scalar()
    ) or 0.0

    day_shifts_today = (
        db.session.query(func.coalesce(func.sum(Attendance.day_shift_flag), 0.0))
        .filter(Attendance.site_id == site_id, Attendance.date == today)
        .scalar()
    ) or 0.0

    night_shifts_today = (
        db.session.query(func.coalesce(func.sum(Attendance.night_shift_flag), 0.0))
        .filter(Attendance.site_id == site_id, Attendance.date == today)
        .scalar()
    ) or 0.0

    total_shifts_today = float(morning_shifts_today + day_shifts_today + night_shifts_today)

    attendance_percent = (
        round((present_today / total_labours) * 100, 1)
        if total_labours > 0 else 0.0
    )

    # -----------------------------
    # ABSENT TODAY
    # -----------------------------
    absent_labours_query = (
        Labour.query
        .filter(
            Labour.site_id == site_id,
            Labour.is_active.is_(True),
            ~Labour.id.in_(
                db.session.query(Attendance.labour_id)
                .filter(
                    Attendance.site_id == site_id,
                    Attendance.date == today,
                    or_(
                        Attendance.morning_shift_flag > 0,
                        Attendance.day_shift_flag > 0,
                        Attendance.night_shift_flag > 0
                    )
                )
            )
        )
        .order_by(Labour.name.asc())
    )
    absent_today = absent_labours_query.all()

    # -----------------------------
    # FINANCIAL (MONTH TO DATE)
    # -----------------------------
    month_start = today.replace(day=1)
    # Days in current month
    _, num_days_in_month = calendar.monthrange(today.year, today.month)
    days_passed = max(1, today.day)

    payroll_mtd = D(
        db.session.query(
            func.sum(
                (
                    func.coalesce(Attendance.morning_shift_flag, 0.0) +
                    func.coalesce(Attendance.day_shift_flag, 0.0) +
                    func.coalesce(Attendance.night_shift_flag, 0.0)
                ) * Labour.daily_wage
            )
        )
        .select_from(Attendance)
        .join(Labour, Labour.id == Attendance.labour_id)
        .filter(
            Attendance.site_id == site_id,
            Attendance.date >= month_start,
            Attendance.date <= today
        )
        .scalar()
    )

    advances_mtd = D(
        db.session.query(func.sum(Payment.advance))
        .filter(
            Payment.site_id == site_id,
            Payment.date >= month_start,
            Payment.date <= today
        )
        .scalar()
    )

    net_payable_mtd = max(Decimal("0.00"), payroll_mtd - advances_mtd)

    advance_ratio = (
        round((advances_mtd / payroll_mtd) * Decimal("100"), 1)
        if payroll_mtd > 0 else Decimal("0.0")
    )

    daily_burn_rate = round(payroll_mtd / Decimal(days_passed), 2)
    projected_payroll_month = round(daily_burn_rate * Decimal(num_days_in_month), 2)

    # -----------------------------
    # YESTERDAY METRICS
    # -----------------------------
    yesterday_present = (
        db.session.query(func.count(func.distinct(Attendance.labour_id)))
        .filter(
            Attendance.site_id == site_id,
            Attendance.date == yesterday,
            or_(
                Attendance.morning_shift_flag > 0,
                Attendance.day_shift_flag > 0,
                Attendance.night_shift_flag > 0
            )
        )
        .scalar()
    ) or 0

    yesterday_shifts = (
        db.session.query(
            func.coalesce(func.sum(Attendance.morning_shift_flag), 0) +
            func.coalesce(func.sum(Attendance.day_shift_flag), 0) +
            func.coalesce(func.sum(Attendance.night_shift_flag), 0)
        )
        .filter(
            Attendance.site_id == site_id,
            Attendance.date == yesterday
        )
        .scalar()
    ) or 0

    yesterday_attendance_pct = (
        round((yesterday_present / total_labours) * 100, 1)
        if total_labours > 0 else 0.0
    )

    # -----------------------------
    # DELTAS (SAFE)
    # -----------------------------
    present_diff = present_today - yesterday_present
    shift_diff = round(total_shifts_today - float(yesterday_shifts), 1)
    attendance_diff = round(attendance_percent - yesterday_attendance_pct, 1)

    # -----------------------------
    # 14-DAY ATTENDANCE & COST TREND
    # -----------------------------
    trend_labels = []
    trend_turnout = []
    trend_wages = []

    # Get daily aggregate for past 14 days
    fourteen_days_ago = today - timedelta(days=13)
    
    daily_records = (
        db.session.query(
            Attendance.date,
            func.count(func.distinct(case(
                (or_(Attendance.morning_shift_flag > 0, Attendance.day_shift_flag > 0, Attendance.night_shift_flag > 0), Attendance.labour_id),
                else_=None
            ))).label("turnout"),
            func.coalesce(
                func.sum(
                    (
                        func.coalesce(Attendance.morning_shift_flag, 0.0) +
                        func.coalesce(Attendance.day_shift_flag, 0.0) +
                        func.coalesce(Attendance.night_shift_flag, 0.0)
                    ) * Labour.daily_wage
                ),
                0.0
            ).label("wages")
        )
        .select_from(Attendance)
        .join(Labour, Labour.id == Attendance.labour_id)
        .filter(
            Attendance.site_id == site_id,
            Attendance.date >= fourteen_days_ago,
            Attendance.date <= today
        )
        .group_by(Attendance.date)
        .all()
    )

    daily_map = {r.date: (int(r.turnout), float(r.wages)) for r in daily_records}

    for i in range(14):
        d = fourteen_days_ago + timedelta(days=i)
        trend_labels.append(d.strftime("%d %b"))
        val = daily_map.get(d, (0, 0.0))
        trend_turnout.append(val[0])
        trend_wages.append(round(val[1], 2))

    # -----------------------------
    # CHRONIC ABSENTEES (LAST 7 DAYS)
    # -----------------------------
    # Active labours missing 3+ days in the last 7 recorded days
    seven_days_ago = today - timedelta(days=7)
    
    # Days with recorded attendance in the past 7 days
    recorded_dates = [
        r[0] for r in (
            db.session.query(Attendance.date)
            .filter(Attendance.site_id == site_id, Attendance.date >= seven_days_ago, Attendance.date <= today)
            .distinct()
            .all()
        )
    ]

    chronic_absentees = []
    if len(recorded_dates) >= 3:
        all_active_labours = (
            Labour.query
            .filter(Labour.site_id == site_id, Labour.is_active.is_(True))
            .all()
        )
        # Count attendance days per labour
        present_counts = dict(
            db.session.query(
                Attendance.labour_id,
                func.count(func.distinct(Attendance.date))
            )
            .filter(
                Attendance.site_id == site_id,
                Attendance.date.in_(recorded_dates),
                or_(
                    Attendance.morning_shift_flag > 0,
                    Attendance.day_shift_flag > 0,
                    Attendance.night_shift_flag > 0
                )
            )
            .group_by(Attendance.labour_id)
            .all()
        )
        total_session_days = len(recorded_dates)
        for lab in all_active_labours:
            worked_days = present_counts.get(lab.id, 0)
            missed_days = total_session_days - worked_days
            if missed_days >= 3:
                chronic_absentees.append({
                    "id": lab.id,
                    "name": lab.name,
                    "phone": lab.phone or "—",
                    "daily_wage": float(lab.daily_wage or 0),
                    "missed_days": missed_days,
                    "total_days": total_session_days
                })
        chronic_absentees.sort(key=lambda x: x["missed_days"], reverse=True)

    # -----------------------------
    # FINAL RESPONSE
    # -----------------------------
    return {
        "site": {
            "id": site.id,
            "site_name": site.site_name,
            "address": site.address or "—",
            "allow_morning": site.allow_morning_shift,
            "allow_day": site.allow_day_shift,
            "allow_night": site.allow_night_shift
        },
        "manager_name": manager.username if manager else "—",

        "attendance_marked_today": attendance_marked_today,
        "total_labours": total_labours,
        "present_today": present_today,
        "total_shifts_today": total_shifts_today,
        "morning_shifts_today": float(morning_shifts_today),
        "day_shifts_today": float(day_shifts_today),
        "night_shifts_today": float(night_shifts_today),
        "attendance_percent": attendance_percent,

        "payroll_mtd": float(payroll_mtd),
        "advances_mtd": float(advances_mtd),
        "net_payable_mtd": float(net_payable_mtd),
        "advance_ratio": float(advance_ratio),
        "daily_burn_rate": float(daily_burn_rate),
        "projected_payroll_month": float(projected_payroll_month),

        "absent_today": [
            {
                "id": l.id,
                "name": l.name,
                "phone": l.phone or "—",
                "daily_wage": float(l.daily_wage or 0)
            }
            for l in absent_today
        ],
        "chronic_absentees": chronic_absentees[:8],

        "trend_labels": trend_labels,
        "trend_turnout": trend_turnout,
        "trend_wages": trend_wages,

        "yesterday_date": yesterday,
        "yesterday": {
            "present": yesterday_present,
            "shifts": float(yesterday_shifts),
            "attendance_percent": yesterday_attendance_pct,
            "present_diff": present_diff,
            "shift_diff": shift_diff,
            "attendance_diff": attendance_diff
        }
    }
