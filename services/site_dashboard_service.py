from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import func, case, or_

from models import db, Site, User, Labour, Attendance, Payment


def D(val):
    try:
        return Decimal(val)
    except Exception:
        return Decimal("0.00")


def get_admin_site_dashboard(site_id: int) -> dict:
    today = date.today()
    yesterday = today - timedelta(days=1)

    # -----------------------------
    # SITE & MANAGER
    # -----------------------------
    site = Site.query.get(site_id)
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
    # PRESENT TODAY
    # -----------------------------
    present_today = (
        db.session.query(func.count(func.distinct(Attendance.labour_id)))
        .filter(
            Attendance.site_id == site_id,
            Attendance.date == today,
            or_(
                Attendance.day_shift_flag.is_(True),
                Attendance.night_shift_flag.is_(True)
            )
        )
        .scalar()
    ) or 0

    # -----------------------------
    # SHIFTS TODAY (DAY + NIGHT)
    # -----------------------------
    total_shifts_today = (
        db.session.query(
            func.coalesce(
                func.sum(case((Attendance.day_shift_flag.is_(True), 1), else_=0)),
                0
            ) +
            func.coalesce(
                func.sum(case((Attendance.night_shift_flag.is_(True), 1), else_=0)),
                0
            )
        )
        .filter(
            Attendance.site_id == site_id,
            Attendance.date == today
        )
        .scalar()
    ) or 0

    attendance_percent = (
        round((present_today / total_labours) * 100, 1)
        if total_labours > 0 else 0.0
    )

    # -----------------------------
    # ABSENT TODAY
    # -----------------------------
    absent_today = (
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
                        Attendance.day_shift_flag.is_(True),
                        Attendance.night_shift_flag.is_(True)
                    )
                )
            )
        )
        .all()
    )

    # -----------------------------
    # FINANCIAL (MONTH TO DATE)
    # -----------------------------
    month_start = today.replace(day=1)

    payroll_mtd = D(
        db.session.query(
            func.sum(
                case((Attendance.day_shift_flag.is_(True), Labour.daily_wage), else_=0) +
                case((Attendance.night_shift_flag.is_(True), Labour.daily_wage), else_=0)
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

    advance_ratio = (
        round((advances_mtd / payroll_mtd) * Decimal("100"), 1)
        if payroll_mtd > 0 else Decimal("0.0")
    )

    # -----------------------------
    # YESTERDAY METRICS
    # -----------------------------
    yesterday_present = (
        db.session.query(func.count(func.distinct(Attendance.labour_id)))
        .filter(
            Attendance.site_id == site_id,
            Attendance.date == yesterday,
            or_(
                Attendance.day_shift_flag.is_(True),
                Attendance.night_shift_flag.is_(True)
            )
        )
        .scalar()
    ) or 0

    yesterday_shifts = (
        db.session.query(
            func.coalesce(
                func.sum(case((Attendance.day_shift_flag.is_(True), 1), else_=0)),
                0
            ) +
            func.coalesce(
                func.sum(case((Attendance.night_shift_flag.is_(True), 1), else_=0)),
                0
            )
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
    shift_diff = total_shifts_today - yesterday_shifts
    attendance_diff = round(attendance_percent - yesterday_attendance_pct, 1)

    # -----------------------------
    # FINAL RESPONSE
    # -----------------------------
    return {
        "site": {
            "id": site.id,
            "site_name": site.site_name
        },
        "manager_name": manager.username if manager else "—",

        "total_labours": total_labours,
        "present_today": present_today,
        "total_shifts_today": int(total_shifts_today),
        "attendance_percent": attendance_percent,

        "payroll_mtd": float(payroll_mtd),
        "advances_mtd": float(advances_mtd),
        "advance_ratio": float(advance_ratio),

        "absent_today": [
            {"id": l.id, "name": l.name} for l in absent_today
        ],

        "yesterday_date": yesterday,


        "yesterday": {
            "present": yesterday_present,
            "shifts": yesterday_shifts,
            "attendance_percent": yesterday_attendance_pct,
            "present_diff": present_diff,
            "shift_diff": shift_diff,
            "attendance_diff": attendance_diff
        }
    }
