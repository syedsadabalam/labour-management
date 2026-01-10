# services/labour_summary_service.py

from datetime import date
from sqlalchemy import func
from models import (
    db,
    Attendance,
    Payment,
    LabourMonthlyExpenses
)

def build_monthly_summary(labour, month, site_id=None):
    """
    Builds labour monthly summary.
    If site_id is provided → site-restricted (manager)
    """

    year, mon = map(int, month.split('-'))
    start_date = date(year, mon, 1)
    end_date = date(year + (mon == 12), (mon % 12) + 1, 1)

    # ---------- Attendance ----------
    attendance_query = Attendance.query.filter(
        Attendance.labour_id == labour.id,
        Attendance.date >= start_date,
        Attendance.date < end_date
    )

    if site_id:
        attendance_query = attendance_query.filter(
            Attendance.site_id == site_id
        )

    attendance_rows = attendance_query.order_by(Attendance.date).all()

    day_shifts = night_shifts = absent_days = 0
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

    # ---------- Earnings ----------
    daily_wage = float(labour.daily_wage or 0)
    earned_pay = daily_wage * total_shifts

    # ---------- Advances ----------
    advance_query = db.session.query(
        func.coalesce(func.sum(Payment.advance), 0)
    ).filter(
        Payment.labour_id == labour.id,
        Payment.date < end_date
    )

    if site_id:
        advance_query = advance_query.filter(
            Payment.site_id == site_id
        )

    advance_paid = advance_query.scalar() or 0

    # ---------- Monthly Expenses ----------
    expense = LabourMonthlyExpenses.query.filter_by(
        labour_id=labour.id,
        site_id=site_id if site_id else labour.site_id,
        month=month
    ).first()

    mess = float(expense.mess_amount) if expense else 0
    canteen = float(expense.canteen_amount) if expense else 0
    total_expense = mess + canteen

    # ---------- Net Payable ----------
    net_payable = earned_pay - advance_paid - total_expense

    return {
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
            "mess_canteen": total_expense,
            "net_payable": net_payable
        },
        "calendar": calendar
    }
