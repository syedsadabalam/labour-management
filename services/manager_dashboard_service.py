from models import Attendance, Site, Labour
from extensions import db
from datetime import date
from sqlalchemy import or_

def get_manager_dashboard_data(site_id):
    if not site_id:
        return {
            "total_labours": 0,
            "present_today": 0,
            "absent_today": 0
        }

    today = date.today()

    total_labours = (
        Labour.query
        .filter_by(site_id=site_id, is_active=True)
        .count()
    )

    present_today = (
        Attendance.query
        .filter(
            Attendance.site_id == site_id,
            Attendance.date == today,
            or_(
                Attendance.morning_shift_flag > 0,
                Attendance.day_shift_flag > 0,
                Attendance.night_shift_flag > 0
            )
        )
        .count()
    )


    return {
        "total_labours": total_labours,
        "present_today": present_today,
        "absent_today": total_labours - present_today
    }
