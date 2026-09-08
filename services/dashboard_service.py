from datetime import date, time
from decimal import Decimal

from sqlalchemy import func, case, extract, or_
from sqlalchemy.orm import joinedload

from extensions import db
from models import Site, Labour, Attendance, Payment, User

ATTENDANCE_CUTOFF = time(22, 0)  # 10:00 PM


def get_admin_dashboard_data(company_id):
    today = date.today()
    year = today.year
    month = today.month

    # =====================================================
    # BASIC COUNTS
    # =====================================================

    total_sites = Site.query.filter_by(company_id=company_id).count()

    active_sites_count = Site.query.filter_by(
        company_id=company_id,
        is_active=True
    ).count()

    total_active_labours = Labour.query.join(Site).filter(
        Labour.company_id == company_id,
        Labour.is_active == True,
        Site.is_active == True
    ).count()

    # =====================================================
    # ATTENDANCE TODAY (PER SITE)
    # =====================================================

    attendance_today_rows = (
        db.session.query(
            Attendance.site_id,
            func.count(func.distinct(Attendance.labour_id)).label("present"),
            func.max(Attendance.created_at).label("last_marked")
        )
        .join(Labour, Labour.id == Attendance.labour_id)
        .join(Site, Site.id == Attendance.site_id)
        .filter(
            Labour.company_id == company_id,
            Labour.is_active == True,
            Site.is_active == True,
            Attendance.date == today,
            or_(
                Attendance.morning_shift_flag == True,
                Attendance.day_shift_flag == True,
                Attendance.night_shift_flag == True
            )
        )
        .group_by(Attendance.site_id)
        .all()
    )

    attendance_map = {}
    for r in attendance_today_rows:
        delayed = False
        if r.last_marked:
            delayed = r.last_marked.time() > ATTENDANCE_CUTOFF

        attendance_map[r.site_id] = {
            "present": r.present,
            "delayed": delayed
        }

    # =====================================================
    # PAYROLL (MTD)
    # =====================================================

    payroll_subq = (
        db.session.query(
            Attendance.site_id,
            Attendance.labour_id,
            func.sum(
                case((Attendance.morning_shift_flag == True, 1), else_=0) +
                case((Attendance.day_shift_flag == True, 1), else_=0) +
                case((Attendance.night_shift_flag == True, 1), else_=0)
            ).label("shifts")
        )
        .join(Labour, Labour.id == Attendance.labour_id)
        .join(Site, Site.id == Attendance.site_id)
        .filter(
            Labour.company_id == company_id,
            Labour.is_active == True,
            Site.is_active == True,
            extract("year", Attendance.date) == year,
            extract("month", Attendance.date) == month
        )
        .group_by(Attendance.site_id, Attendance.labour_id)
        .subquery()
    )

    payroll_rows = (
        db.session.query(
            payroll_subq.c.site_id,
            func.sum(payroll_subq.c.shifts * Labour.daily_wage).label("payroll")
        )
        .join(Labour, Labour.id == payroll_subq.c.labour_id)
        .group_by(payroll_subq.c.site_id)
        .all()
    )

    payroll_map = {
        r.site_id: Decimal(r.payroll or 0)
        for r in payroll_rows
    }

    total_payroll_mtd = sum(payroll_map.values(), Decimal(0))

    # =====================================================
    # ADVANCES (MTD)
    # =====================================================

    advance_rows = (
        db.session.query(
            Payment.site_id,
            func.coalesce(func.sum(Payment.advance), 0)
        )
        .join(Labour, Labour.id == Payment.labour_id)
        .join(Site, Site.id == Payment.site_id)
        .filter(
            Labour.company_id == company_id,
            Labour.is_active == True,
            Site.is_active == True,
            extract("year", Payment.date) == year,
            extract("month", Payment.date) == month
        )
        .group_by(Payment.site_id)
        .all()
    )

    advance_map = {
        r[0]: Decimal(r[1] or 0)
        for r in advance_rows
    }

    total_advances = sum(advance_map.values(), Decimal(0))

    # =====================================================
    # SITE CARDS
    # =====================================================

    sites = (
        Site.query
        .options(joinedload(Site.users), joinedload(Site.labours))
        .filter(Site.company_id == company_id)
        .all()
    )

    site_cards = []
    total_expected_today = 0
    total_present_today = 0
    critical_alerts = 0

    for site in sites:
        total_labours = len(
            [l for l in site.labours if l.is_active]
        )

        att = attendance_map.get(site.id, {})
        present = att.get("present", 0)
        delayed = att.get("delayed", False)

        total_expected_today += total_labours
        total_present_today += present

        attendance_pct = (
            round((present / total_labours) * 100, 1)
            if total_labours else 0
        )

        payroll = Decimal(payroll_map.get(site.id, 0))
        advance = Decimal(advance_map.get(site.id, 0))
        advance_ratio = (
            round((advance / payroll) * 100, 1)
            if payroll else 0
        )

        status = "OK"
        if not site.is_active:
            status = "INACTIVE"
        elif present == 0:
            status = "CRITICAL"
            critical_alerts += 1
        elif delayed:
            status = "DELAYED"
        elif attendance_pct < 70:
            status = "WARNING"

        manager = next(
            (u.username for u in site.users if u.role == "manager"),
            None
        )

        site_cards.append({
            "site_id": site.id,
            "site_name": site.site_name,
            "manager_name": manager or "—",
            "is_active": site.is_active,
            "total_labours": total_labours,
            "present_today": present,
            "attendance_percent": attendance_pct,
            "payroll_mtd": float(payroll),
            "advances_mtd": float(advance),
            "advance_ratio": advance_ratio,
            "status": status
        })

    # =====================================================
    # SYSTEM STATUS BAR
    # =====================================================

    system_attendance_percent = (
        (total_present_today / total_expected_today) * 100
        if total_expected_today else 0
    )

    active_sites = sum(
        1 for s in site_cards if s["status"] != "INACTIVE"
    )

    # =====================================================
    # FINAL RESPONSE
    # =====================================================
    managers = []

    for site in site_cards:
        if site["manager_name"] == "—":
            continue

        status = "Healthy"
        if site["status"] == "CRITICAL":
            status = "Critical"
        elif site["status"] == "DELAYED":
            status = "Delayed"

        managers.append({
            
            "site": site["site_name"],
            "status": status
        })

    attendance_exceptions = []

    for site in site_cards:
        if site["attendance_percent"] < 70 and site["total_labours"] > 0:
            attendance_exceptions.append({
                "site_name": site["site_name"],
                "attendance_percent": site["attendance_percent"]
            })


    # =====================================================
    # 7-DAY TREND DATA
    # =====================================================
    from datetime import timedelta
    
    last_7_days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    
    trend_rows = (
        db.session.query(
            Attendance.date,
            func.count(func.distinct(Attendance.labour_id)).label("present")
        )
        .join(Labour, Labour.id == Attendance.labour_id)
        .join(Site, Site.id == Attendance.site_id)
        .filter(
            Labour.company_id == company_id,
            Labour.is_active == True,
            Site.is_active == True,
            Attendance.date >= last_7_days[0],
            or_(
                Attendance.morning_shift_flag == True,
                Attendance.day_shift_flag == True,
                Attendance.night_shift_flag == True
            )
        )
        .group_by(Attendance.date)
        .all()
    )

    trend_map = {r.date: r.present for r in trend_rows}

    trend_labels = [d.strftime("%b %d") for d in last_7_days]
    trend_values = [trend_map.get(d, 0) for d in last_7_days]


    return {
        "system_status": {
            "attendance_percent": round(system_attendance_percent, 1),
            "total_sites": total_sites,
            "active_sites": active_sites,
            "total_payroll_mtd": float(total_payroll_mtd),
            "total_advances": float(total_advances),
            "advance_ratio": round(
                (total_advances / total_payroll_mtd) * 100, 2
            ) if total_payroll_mtd else 0,
            "alerts": critical_alerts,
            "payroll_state": "Draft"
        },

        "financial_risk": {
            "payroll_mtd": float(total_payroll_mtd),
            "advances": float(total_advances),
            "ratio": round(
                (total_advances / total_payroll_mtd) * 100, 2
            ) if total_payroll_mtd else 0
        },

        "trend_data": {
            "labels": trend_labels,
            "values": trend_values
        },

        "attendance_exceptions": attendance_exceptions,
        "sites": site_cards
    }
