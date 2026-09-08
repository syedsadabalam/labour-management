from datetime import date, time, timedelta
from decimal import Decimal

from sqlalchemy import func, case, extract, or_
from sqlalchemy.orm import joinedload

from extensions import db
from models import Site, Labour, Attendance, Payment, User

ATTENDANCE_CUTOFF = time(22, 0)  # 10:00 PM


def get_admin_dashboard_data(company_id):
    today = date.today()
    yesterday = today - timedelta(days=1)
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
                Attendance.morning_shift_flag > 0,
                Attendance.day_shift_flag > 0,
                Attendance.night_shift_flag > 0
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
    # ATTENDANCE YESTERDAY (BASELINE METRIC - OPTION B)
    # =====================================================

    yesterday_rows = (
        db.session.query(
            Attendance.site_id,
            func.count(func.distinct(Attendance.labour_id)).label("present")
        )
        .join(Labour, Labour.id == Attendance.labour_id)
        .join(Site, Site.id == Attendance.site_id)
        .filter(
            Labour.company_id == company_id,
            Labour.is_active == True,
            Site.is_active == True,
            Attendance.date == yesterday,
            or_(
                Attendance.morning_shift_flag > 0,
                Attendance.day_shift_flag > 0,
                Attendance.night_shift_flag > 0
            )
        )
        .group_by(Attendance.site_id)
        .all()
    )

    yesterday_map = {r.site_id: r.present for r in yesterday_rows}
    total_yesterday_present = sum(yesterday_map.values())
    yesterday_attendance_percent = (
        round((total_yesterday_present / total_active_labours) * 100, 1)
        if total_active_labours else 0.0
    )

    # =====================================================
    # PAYROLL (MTD)
    # =====================================================

    payroll_subq = (
        db.session.query(
            Attendance.site_id,
            Attendance.labour_id,
            func.sum(
                Attendance.morning_shift_flag +
                Attendance.day_shift_flag +
                Attendance.night_shift_flag
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
    net_payable_mtd = max(Decimal("0.00"), total_payroll_mtd - total_advances)
    daily_burn_rate = round(total_payroll_mtd / Decimal(max(1, today.day)), 2)

    # =====================================================
    # SITE CARDS
    # =====================================================

    sites = (
        Site.query
        .options(joinedload(Site.users))
        .filter(Site.company_id == company_id)
        .all()
    )

    active_labour_counts = (
        db.session.query(
            Labour.site_id,
            func.count(Labour.id).label('count')
        )
        .filter(
            Labour.company_id == company_id,
            Labour.is_active == True
        )
        .group_by(Labour.site_id)
        .all()
    )
    
    labour_count_map = {row.site_id: row.count for row in active_labour_counts}

    site_cards = []
    total_expected_today = 0
    total_present_today = 0
    critical_alerts = 0
    pending_attendance_sites = 0

    for site in sites:
        total_labours = labour_count_map.get(site.id, 0)
        yesterday_count = yesterday_map.get(site.id, 0)

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
        alerts = []
        if not site.is_active:
            status = "INACTIVE"
        elif present == 0:
            # Not marked today -> Routinely Pending (not Critical)
            status = "PENDING"
            alerts.append("Today's attendance pending")
            pending_attendance_sites += 1
        elif delayed:
            status = "DELAYED"
            alerts.append("Attendance submission delayed")
        elif attendance_pct < 70:
            status = "WARNING"
            alerts.append(f"Low attendance ({attendance_pct}%)")

        # True Critical criteria: high financial risk or no manager
        manager = next(
            (u.username for u in site.users if u.role == "manager"),
            None
        )
        if not manager and site.is_active:
            status = "CRITICAL"
            alerts.append("No site manager assigned")
            critical_alerts += 1
        elif advance_ratio > 30:
            alerts.append(f"High advance risk ({advance_ratio}%)")
            critical_alerts += 1

        site_cards.append({
            "site_id": site.id,
            "site_name": site.site_name,
            "manager_name": manager or "—",
            "is_active": site.is_active,
            "total_labours": total_labours,
            "present_today": present,
            "yesterday_present": yesterday_count,
            "attendance_percent": attendance_pct,
            "payroll_mtd": float(payroll),
            "advances_mtd": float(advance),
            "advance_ratio": advance_ratio,
            "status": status,
            "alerts": alerts
        })

    # =====================================================
    # SYSTEM STATUS BAR (OPTION B: BASELINE LOGIC)
    # =====================================================

    today_has_attendance = total_present_today > 0
    today_is_pending = not today_has_attendance

    system_attendance_percent = (
        round((total_present_today / total_expected_today) * 100, 1)
        if total_expected_today else 0.0
    )

    active_sites = sum(
        1 for s in site_cards if s["status"] != "INACTIVE"
    )

    # =====================================================
    # MANAGERS TELEMETRY LIST
    # =====================================================
    managers = []

    for site in site_cards:
        att_marked = site["present_today"] > 0
        status_text = "Submitted" if att_marked else "Pending Entry"

        managers.append({
            "manager": site["manager_name"],
            "site": site["site_name"],
            "site_id": site["site_id"],
            "status": status_text,
            "is_marked": att_marked,
            "yesterday_present": site["yesterday_present"],
            "total_labours": site["total_labours"]
        })

    attendance_exceptions = []

    for site in site_cards:
        if site["attendance_percent"] < 70 and site["total_labours"] > 0 and site["present_today"] > 0:
            attendance_exceptions.append({
                "site_name": site["site_name"],
                "attendance_percent": site["attendance_percent"]
            })

    # =====================================================
    # 7-DAY TREND DATA (OPTION B: VERIFIED BASELINE INTEGRATION)
    # =====================================================
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
                Attendance.morning_shift_flag > 0,
                Attendance.day_shift_flag > 0,
                Attendance.night_shift_flag > 0
            )
        )
        .group_by(Attendance.date)
        .all()
    )

    trend_map = {r.date: r.present for r in trend_rows}

    trend_labels = [d.strftime("%b %d") for d in last_7_days]
    trend_values = []
    
    for d in last_7_days:
        if d == today and today_is_pending:
            # Option B: Use yesterday's verified baseline so the curve doesn't plunge artificially to 0
            trend_values.append(total_yesterday_present)
        else:
            trend_values.append(trend_map.get(d, 0))

    return {
        "current_date": today.strftime("%d %b %Y"),
        "today_is_pending": today_is_pending,
        "yesterday_baseline": {
            "present": total_yesterday_present,
            "total_labours": total_active_labours,
            "percent": yesterday_attendance_percent
        },
        "system_status": {
            "attendance_percent": system_attendance_percent,
            "display_attendance_percent": system_attendance_percent if not today_is_pending else yesterday_attendance_percent,
            "is_baseline_display": today_is_pending,
            "total_sites": total_sites,
            "active_sites": active_sites,
            "total_payroll_mtd": float(total_payroll_mtd),
            "total_advances": float(total_advances),
            "net_payable_mtd": float(net_payable_mtd),
            "daily_burn_rate": float(daily_burn_rate),
            "advance_ratio": round(
                (total_advances / total_payroll_mtd) * 100, 2
            ) if total_payroll_mtd else 0,
            "alerts": critical_alerts,
            "pending_attendance_sites": pending_attendance_sites,
            "payroll_state": "Draft"
        },

        "financial_risk": {
            "payroll_mtd": float(total_payroll_mtd),
            "advances": float(total_advances),
            "net_payable": float(net_payable_mtd),
            "ratio": round(
                (total_advances / total_payroll_mtd) * 100, 2
            ) if total_payroll_mtd else 0
        },

        "trend_data": {
            "labels": trend_labels,
            "values": trend_values,
            "is_baseline_today": today_is_pending
        },

        "managers": managers,
        "attendance_exceptions": attendance_exceptions,
        "sites": site_cards
    }
