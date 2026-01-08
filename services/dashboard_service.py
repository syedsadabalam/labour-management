from datetime import date, datetime, time
from sqlalchemy import func, case, or_, extract
from decimal import Decimal

from models import db, Site, Labour, Attendance, Payment, User
from sqlalchemy.orm import joinedload


ATTENDANCE_CUTOFF = time(22, 00)  # 9:30 AM IST

def get_admin_dashboard_data():
    today = date.today()
    year = today.year
    month = today.month

    # =========================
    # BASIC COUNTS
    # =========================
    total_sites = Site.query.count()
    total_labours = Labour.query.filter_by(is_active=True).count()

    # =========================
    # ATTENDANCE TODAY (SITE-WISE)
    # =========================
    attendance_today = (
        db.session.query(
            Attendance.site_id,
            func.count(func.distinct(Attendance.labour_id)).label("present"),
            func.max(Attendance.created_at).label("last_marked")
        )
        .filter(
            Attendance.date == today,
            or_(
                Attendance.day_shift_flag == True,
                Attendance.night_shift_flag == True
            )
        )
        .group_by(Attendance.site_id)
        .all()
    )

    attendance_map = {}
    for row in attendance_today:
        delayed = False
        if row.last_marked:
            delayed = row.last_marked.time() > ATTENDANCE_CUTOFF

        attendance_map[row.site_id] = {
            "present": row.present,
            "last_time": row.last_marked,
            "delayed": delayed
        }

    # =========================
    # PAYROLL (MONTH TO DATE)
    # =========================
    payroll_subq = (
        db.session.query(
            Attendance.site_id,
            Attendance.labour_id,
            func.sum(
                case((Attendance.day_shift_flag == True, 1), else_=0) +
                case((Attendance.night_shift_flag == True, 1), else_=0)
            ).label("shifts")
        )
        .filter(
            extract("year", Attendance.date) == year,
            extract("month", Attendance.date) == month
        )
        .group_by(Attendance.site_id, Attendance.labour_id)
        .subquery()
    )

    payroll_map = dict(
        db.session.query(
            payroll_subq.c.site_id,
            func.coalesce(
                func.sum(payroll_subq.c.shifts * Labour.daily_wage),
                0
            )
        )
        .join(Labour, Labour.id == payroll_subq.c.labour_id)
        .group_by(payroll_subq.c.site_id)
        .all()
    )

    # =========================
    # ADVANCES (MONTH TO DATE)
    # =========================
    advance_map = dict(
        db.session.query(
            Payment.site_id,
            func.coalesce(func.sum(Payment.advance), 0)
        )
        .filter(
            extract("year", Payment.date) == year,
            extract("month", Payment.date) == month
        )
        .group_by(Payment.site_id)
        .all()
    )

    # =========================
    # SITES (MAIN LOOP)
    # =========================
    site_cards = []
    total_alerts = 0

    sites = (
        db.session.query(Site)
        .options(joinedload(Site.users), joinedload(Site.labours))
        .all()
    )

    for site in sites:
        total = len([l for l in site.labours if l.is_active])
        att = attendance_map.get(site.id, {})
        present = att.get("present", 0)
        delayed = att.get("delayed", False)

        attendance_pct = round((present / total) * 100, 1) if total else 0

        payroll = Decimal(payroll_map.get(site.id, 0))
        advance = Decimal(advance_map.get(site.id, 0))
        advance_ratio = round((advance / payroll) * 100, 1) if payroll else 0

        # =========================
        # STATUS LOGIC (CORRECT)
        # =========================
        if total == 0:
            status = "INACTIVE"
        elif present == 0:
            status = "CRITICAL"
        elif delayed:
            status = "DELAYED"
        elif attendance_pct < 70:
            status = "WARNING"
        else:
            status = "HEALTHY"


        alerts = []
        if present == 0:
            alerts.append("⚠️No attendance marked today")
        if delayed:
            alerts.append("🟡Attendance delayed")
        if advance_ratio > 40:
            alerts.append("Advance exceeds safe limit")

        total_alerts += len(alerts)

        manager = next(
            (u.username for u in site.users if u.role == "manager"),
            "—"
        )

        site_cards.append({
            "site_id": site.id,
            "site_name": site.site_name,
            "manager_name": manager,
            "total_labours": total,
            "present_today": present,
            "attendance_percent": attendance_pct,
            "payroll_mtd": float(payroll),
            "total_advance": float(advance),
            "advance_ratio": advance_ratio,
            "status": status,
            "alerts": alerts
        })

    # =========================
    # SYSTEM STATUS BAR
    # =========================
    active_sites = sum(
        1 for s in site_cards if s["total_labours"] > 0
    )


    system_status = {
        "attendance_percent": round(
            (sum(s["present_today"] for s in site_cards) / total_labours) * 100, 1
        ) if total_labours else 0,
        "active_sites": active_sites,
        "total_sites": total_sites,

        "alerts": total_alerts,
        "payroll_state": "Draft"
    }

    # =========================
    # FINANCIAL RISK TOTALS
    # =========================
    total_payroll_mtd = sum(
        s["payroll_mtd"] for s in site_cards
    )

    total_advances = sum(
        s["total_advance"] for s in site_cards
    )

    advance_payroll_ratio = (
        round((total_advances / total_payroll_mtd) * 100, 1)
        if total_payroll_mtd > 0 else 0
    )


    attendance_exceptions = [
        {
            "site_name": s["site_name"],
            "attendance_percent": s["attendance_percent"]
        }
        for s in site_cards
        if s["total_labours"] > 0 and s["attendance_percent"] < 70
    ]


    manager_summary = []

    for s in site_cards:
        if s["total_labours"] == 0:
            continue

        if s["status"] == "CRITICAL":
            state = "Critical"
        elif s["status"] == "DELAYED":
            state = "Delayed"
        else:
            state = "Healthy"

        manager_summary.append({
            "manager": s["manager_name"],
            "site": s["site_name"],
            "status": state
        })


    return {
        "system_status": system_status,
        "sites": site_cards,
        "financial_risk": {
            "payroll_mtd": total_payroll_mtd,
            "advances": total_advances,
            "ratio": advance_payroll_ratio
        },
        "attendance_exceptions": attendance_exceptions,
        "managers": manager_summary
    }


