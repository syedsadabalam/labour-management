from flask_login import login_required
from . import admin_bp
import pandas as pd
import io
from flask import Response
from sqlalchemy import case

from .utils import _admin_required, _to_int

from datetime import datetime, timedelta
from decimal import Decimal
from flask import render_template, redirect, url_for, request
from flask_login import login_required, current_user
from sqlalchemy import func, and_
from models import Attendance, Labour, Payment, Site, LabourMonthlyExpenses
from extensions import db

@admin_bp.route('/monthly-report', methods=['GET'])
@login_required
def monthly_report():

    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))

    site_id = request.args.get('site_id', type=int)
    month = request.args.get('month')          # YYYY-MM
    export = request.args.get('export', '0')

    sites = Site.query.filter_by(
        company_id=current_user.company_id
    ).order_by(Site.site_name.asc()).all()

    rows = []
    grand_total = Decimal('0.00')
    

    if site_id:
        valid_site = Site.query.filter_by(id=site_id, company_id=current_user.company_id).first()
        if not valid_site:
            site_id = None

    if site_id and month:
        start_date = datetime.strptime(month + '-01', '%Y-%m-%d').date()
        end_date = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1)


        attendance_subq = (
            db.session.query(
                Attendance.labour_id.label('labour_id'),

                func.sum(Attendance.morning_shift_flag).label('morning_shift'),
                func.sum(Attendance.day_shift_flag).label('day_shift'),
                func.sum(Attendance.night_shift_flag).label('night_shift'),
            )
            .filter(
                Attendance.site_id == site_id,
                Attendance.date >= start_date,
                Attendance.date < end_date
            )
            .group_by(Attendance.labour_id)
            .subquery()
        )







        data = (
            db.session.query(
                Labour.id,
                Labour.name.label('labour_name'),
                Site.site_name,
                Labour.bank_account,
                Labour.ifsc_code,
                Labour.daily_wage,

                func.coalesce(attendance_subq.c.morning_shift, 0).label('morning_shift'),
                func.coalesce(attendance_subq.c.day_shift, 0).label('day_shift'),
                func.coalesce(attendance_subq.c.night_shift, 0).label('night_shift'),

                func.coalesce(func.sum(Payment.advance), Decimal('0.00')).label('advance_paid'),
                func.coalesce(
                    LabourMonthlyExpenses.mess_amount +
                    LabourMonthlyExpenses.canteen_amount,
                    Decimal('0.00')
                ).label('expenses')
            )
            .join(attendance_subq, attendance_subq.c.labour_id == Labour.id)
            .join(Site, Site.id == Labour.site_id)


            .outerjoin(
                Payment,
                and_(
                    Payment.labour_id == Labour.id,
                    Payment.site_id == site_id,
                    Payment.date >= start_date,
                    Payment.date < end_date
                )
            )
            .outerjoin(
                LabourMonthlyExpenses,
                and_(
                    LabourMonthlyExpenses.labour_id == Labour.id,
                    LabourMonthlyExpenses.site_id == site_id,
                    LabourMonthlyExpenses.month == month
                )
            )
            .filter(Labour.is_active == True)
            .group_by(
                Labour.id,
                Labour.name,
                Site.site_name,
                Labour.bank_account,
                Labour.ifsc_code,
                Labour.daily_wage,
                LabourMonthlyExpenses.mess_amount,
                LabourMonthlyExpenses.canteen_amount
            )

            .order_by(Labour.name.asc())
            .all()
        )


        for r in data:
            morning = float(r.morning_shift or 0)
            day = float(r.day_shift or 0)
            night = float(r.night_shift or 0)

            total_shifts = morning + day + night
            wage = Decimal(r.daily_wage or 0)

            total_pay = wage * total_shifts

            advance = Decimal(r.advance_paid or 0)
            expenses = Decimal(r.expenses or 0)

            net = total_pay - advance - expenses
            grand_total += net

            rows.append({
                'labour_name': r.labour_name,
                'site_name': r.site_name,
                'total_shifts': total_shifts, 
                'morning_shift': morning,
                'day_shift': day,
                'night_shift': night,
                'total_pay': total_pay,
                'advance_paid': advance,
                'expenses': expenses,
                'net_payable': net
            })



   
    # -------- EXCEL EXPORT --------
    if export == '1' and rows:
        df = pd.DataFrame(rows)

        df.insert(0, 'Sl. No.', range(1, len(df) + 1))

        df = df[[
            'Sl. No.',
            'labour_name',
            'total_shifts',
            'morning_shift',
            'day_shift',
            'night_shift',
            'total_pay',
            'advance_paid',
            'expenses',
            'net_payable'
        ]]

        df.columns = [
            'Sl. No.',
            'Name',
            'Total Shifts',
            'Morning Shift',
            'Day Shift',
            'Night Shift',
            'Total Pay',
            'Advance Paid',
            'Expenses',
            'Net Payable'
        ]

        # TOTAL ROW (PROPER TOTALS)
        df.loc[len(df)] = [
            '',
            'TOTAL',
            df['Total Shifts'].sum(),
            df['Morning Shift'].sum(),
            df['Day Shift'].sum(),
            df['Night Shift'].sum(),
            df['Total Pay'].sum(),
            df['Advance Paid'].sum(),
            df['Expenses'].sum(),
            df['Net Payable'].sum()
        ]

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Monthly Payroll')

        output.seek(0)
        return Response(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={
                'Content-Disposition':
                'attachment;filename=Monthly_Payroll_Report.xlsx'
            }
        )

    return render_template(
        'admin_monthly_report.html',
        sites=sites,
        rows=rows,
        selected_site=site_id,
        selected_month=month,
        grand_total=grand_total
    )



@admin_bp.route('/salary-sheet', methods=['GET'])
@login_required
def labour_salary_sheet():

    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))

    site_id = request.args.get('site_id', type=int)
    month = request.args.get('month')  # YYYY-MM
    export = request.args.get('export')

    sites = Site.query.filter_by(
        company_id=current_user.company_id
    ).order_by(Site.site_name.asc()).all()

    rows = []
    grand_total = Decimal('0.00')

    if site_id:
        valid_site = Site.query.filter_by(id=site_id, company_id=current_user.company_id).first()
        if not valid_site:
            site_id = None

    if site_id and month:
        start_date = datetime.strptime(month + '-01', '%Y-%m-%d').date()
        end_date = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1)

        attendance_subq = (
            db.session.query(
                Attendance.labour_id.label('labour_id'),

                func.sum(Attendance.morning_shift_flag).label('morning_shift'),
                func.sum(Attendance.day_shift_flag).label('day_shift'),
                func.sum(Attendance.night_shift_flag).label('night_shift')
            )
            .filter(
                Attendance.site_id == site_id,
                Attendance.date >= start_date,
                Attendance.date < end_date
            )
            .group_by(Attendance.labour_id)
            .subquery()
        )




        raw_rows = (
            db.session.query(
                Labour.name,
                Labour.bank_account,
                Labour.ifsc_code,
                Labour.daily_wage,

                func.coalesce(attendance_subq.c.morning_shift, 0).label('morning_shift'),
                func.coalesce(attendance_subq.c.day_shift, 0).label('day_shift'),
                func.coalesce(attendance_subq.c.night_shift, 0).label('night_shift')
            )
            .join(attendance_subq, attendance_subq.c.labour_id == Labour.id)
            .filter(Labour.is_active == True)
            .order_by(Labour.name.asc())
            .all()
        )



        for r in raw_rows:
            total_shifts = float(r.morning_shift or 0) + float(r.day_shift or 0) + float(r.night_shift or 0)
            total_pay = Decimal(r.daily_wage) * total_shifts

            rows.append({
                'name': r.name,
                'bank_account': r.bank_account,
                'ifsc_code': r.ifsc_code,
                'total_pay': total_pay
            })

            grand_total += total_pay



        # ---------- EXCEL EXPORT ----------
        if export == '1':
            df = pd.DataFrame(rows)
            df.insert(0, 'Sl. No.', range(1, len(df) + 1))
            df.rename(columns={
                'name': 'Name',
                'bank_account': 'Bank Account',
                'ifsc_code': 'IFSC Code',
                'total_pay': 'Total Pay'
            }, inplace=True)

            # ✅ TOTAL ROW (correct)
            df.loc[len(df)] = {
                'Sl. No.': '',
                'Name': 'TOTAL',
                'Bank Account': '',
                'IFSC Code': '',
                'Total Pay': grand_total
            }

            output = pd.ExcelWriter('salary_sheet.xlsx', engine='xlsxwriter')
            df.to_excel(output, index=False, sheet_name='Salary Sheet')
            output.close()

            return Response(
                open('salary_sheet.xlsx', 'rb'),
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                headers={'Content-Disposition': 'attachment;filename=Labour_Salary_Sheet.xlsx'}
            )


    return render_template(
        'salary_sheet.html',
        sites=sites,
        rows=rows,
        selected_site=site_id,
        selected_month=month,
        grand_total=grand_total
    )

