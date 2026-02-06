from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from extensions import db
from models import Site, Labour, Attendance, Payment, LabourMonthlyExpenses
from services.audit_service import log_audit
from . import admin_bp
from .utils import _admin_required, _to_int
import re
from routes.admin.utils import save_and_compress_image


from services.labour_service import get_admin_labours

@admin_bp.route('/labours')
@login_required
def admin_labours():
    search = request.args.get('search', '').strip()
    site_id = request.args.get('site_id', type=int)
    page = request.args.get('page', 1, type=int)

    pagination, sites = get_admin_labours(
        company_id=current_user.company_id,
        search=search,
        site_id=site_id,
        page=page,
        per_page=30
    )

    return render_template(
        "admin_labours.html",
        labours=pagination.items,
        pagination=pagination,
        sites=sites,
        search=search,
        site_id=site_id
    )



@admin_bp.route('/labours/add', methods=['GET', 'POST'])
@login_required
def admin_add_labour():
    if not _admin_required():
        return redirect(url_for('auth.login'))

    sites = Site.query.filter_by(
        company_id=current_user.company_id,
        is_active=True
    ).all()

    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        site_id = _to_int(request.form.get('site_id'))


        # ---- SITE OWNERSHIP VALIDATION (PASTE HERE) ----
        site = Site.query.filter_by(
            id=site_id,
            company_id=current_user.company_id,
            is_active=True
        ).first()

        if not site:
            flash('Invalid site selected', 'danger')
            return redirect(url_for('admin_bp.admin_add_labour'))


        # ---- DUPLICATE CHECK ----
        existing = Labour.query.filter_by(
            phone=phone,
            site_id=site_id,
            company_id=current_user.company_id,
            is_active=True
        ).first()

        if existing:
            flash(
                'Labour with this phone number already exists for this site.',
                'danger'
            )
            return redirect(url_for('admin_bp.admin_add_labour'))

        labour = Labour(
            gate_pass_id=request.form.get('gate_pass_id') or None,
            name=request.form.get('name'),
            phone=phone,
            bank_account=request.form.get('bank_account'),
            ifsc_code=request.form.get('ifsc_code'),
            site_id=site_id,
            daily_wage=request.form.get('daily_wage') or None,
            is_active=(request.form.get('is_active') == 'on'),
            company_id=current_user.company_id
        )

        try:
            db.session.add(labour)
            db.session.commit()  # MUST commit first to get labour.id
        except IntegrityError:
            db.session.rollback()
            flash(
                'Duplicate labour detected (same phone & site).',
                'danger'
            )
            return redirect(url_for('admin_bp.admin_add_labour'))

        # ---- FILE UPLOADS (WITH ROLLBACK) ----
        try:
            photo = request.files.get('photo')
            aadhaar_front = request.files.get('aadhaar_front')
            aadhaar_back = request.files.get('aadhaar_back')
            gate_pass_front = request.files.get('gate_pass_front')
            gate_pass_back = request.files.get('gate_pass_back')

            if photo:
                labour.photo_path = save_and_compress_image(
                    photo, labour.id, 'photo.jpg'
                )

            if aadhaar_front:
                labour.aadhaar_front_path = save_and_compress_image(
                    aadhaar_front, labour.id, 'aadhaar_front.jpg'
                )

            if aadhaar_back:
                labour.aadhaar_back_path = save_and_compress_image(
                    aadhaar_back, labour.id, 'aadhaar_back.jpg'
                )

            if gate_pass_front:
                labour.gate_pass_front_path = save_and_compress_image(
                    gate_pass_front, labour.id, 'gate_pass_front.jpg'
                )

            if gate_pass_back:
                labour.gate_pass_back_path = save_and_compress_image(
                    gate_pass_back, labour.id, 'gate_pass_back.jpg'
                )

            db.session.commit()

        except ValueError as e:
            # rollback fully (NO orphan labour)
            db.session.delete(labour)
            db.session.commit()
            flash(str(e), 'danger')
            return redirect(url_for('admin_bp.admin_add_labour'))


        # ---- AUDIT LOG ----
        try:
            log_audit(
                company_id=current_user.company_id,
                user_id=current_user.id,
                username=current_user.username,
                role=current_user.role,
                site_id=labour.site_id,
                action="labour_added",
                details=f"Labour '{labour.name}' added",
                ip_address=request.remote_addr,
            )
        except Exception as e:
            current_app.logger.error(f"Audit log failed: {e}")


        flash('Labour added successfully', 'success')
        return redirect(url_for('admin_bp.admin_labours'))

    return render_template('admin_add_labour.html', sites=sites)


@admin_bp.route('/labours/<int:labour_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_edit_labour(labour_id):
    if not _admin_required():
        return redirect(url_for('auth.login'))

    labour = Labour.query.filter_by(
        id=labour_id,
        company_id=current_user.company_id
    ).first_or_404()

    sites = Site.query.filter_by(
        company_id=current_user.company_id,
        is_active=True
    ).all()

    if request.method == 'POST':

        gate_pass_id = request.form.get('gate_pass_id', '').strip()
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        bank_account = request.form.get('bank_account', '').strip()
        ifsc_code = request.form.get('ifsc_code', '').strip()
        site_id = _to_int(request.form.get('site_id'))
        daily_wage = request.form.get('daily_wage') or None
        is_active = bool(request.form.get('is_active'))

        # ---- VALIDATIONS ----
        if phone and not re.fullmatch(r"\d{10}", phone):
            flash("Phone number must be exactly 10 digits.", "danger")
            return redirect(url_for("admin_bp.admin_edit_labour", labour_id=labour.id))

        if bank_account and not re.fullmatch(r"\d+", bank_account):
            flash("Bank account number must contain digits only.", "danger")
            return redirect(url_for("admin_bp.admin_edit_labour", labour_id=labour.id))

        labour.gate_pass_id = gate_pass_id or None
        labour.name = name
        labour.phone = phone
        labour.bank_account = bank_account
        labour.ifsc_code = ifsc_code
        labour.site_id = site_id
        labour.daily_wage = daily_wage
        labour.is_active = is_active

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(
                'Another labour with this phone number already exists for this site.',
                'danger'
            )
            return redirect(
                url_for('admin_bp.admin_edit_labour', labour_id=labour.id)
            )

        # ---- OPTIONAL FILE REPLACEMENT ----
        try:
            photo = request.files.get('photo')
            aadhaar_front = request.files.get('aadhaar_front')
            aadhaar_back = request.files.get('aadhaar_back')
            gate_pass_front = request.files.get('gate_pass_front')
            gate_pass_back = request.files.get('gate_pass_back')

            if photo:
                labour.photo_path = save_and_compress_image(
                    photo, labour.id, 'photo.jpg'
                )

            if aadhaar_front:
                labour.aadhaar_front_path = save_and_compress_image(
                    aadhaar_front, labour.id, 'aadhaar_front.jpg'
                )

            if aadhaar_back:
                labour.aadhaar_back_path = save_and_compress_image(
                    aadhaar_back, labour.id, 'aadhaar_back.jpg'
                )

            if gate_pass_front:
                labour.gate_pass_front_path = save_and_compress_image(
                    gate_pass_front, labour.id, 'gate_pass_front.jpg'
                )

            if gate_pass_back:
                labour.gate_pass_back_path = save_and_compress_image(
                    gate_pass_back, labour.id, 'gate_pass_back.jpg'
                )

            db.session.commit()
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'danger')
            return redirect(
                url_for('admin_bp.admin_edit_labour', labour_id=labour.id)
            )

        # ---- AUDIT LOG (NON-BLOCKING) ----
        try:
            log_audit(
                company_id=current_user.company_id,
                user_id=current_user.id,
                username=current_user.username,
                role=current_user.role,
                site_id=labour.site_id,
                action="labour_updated",
                details=f"Labour '{labour.name}' updated",
                ip_address=request.remote_addr,
            )
        except Exception as e:
            current_app.logger.error(f"Audit log failed: {e}")

        flash('Labour updated successfully.', 'success')
        return redirect(url_for('admin_bp.admin_labours'))

    return render_template(
        'admin_edit_labour.html',
        labour=labour,
        sites=sites
    )


@admin_bp.route('/labours/<int:labour_id>/delete', methods=['POST'])
@login_required
def delete_labour(labour_id):
    if not _admin_required():
        return redirect(url_for('auth.login'))

    labour = Labour.query.filter_by(
        id=labour_id,
        company_id=current_user.company_id
    ).first_or_404()

    # --------- SAFETY CHECKS ---------

    # RULE 0: Attendance exists?
    if Attendance.query.filter(
        Attendance.labour_id == labour.id
    ).first():
        flash(
            f"Cannot delete labour '{labour.name}'. "
            f"Attendance records exist. Deactivate instead.",
            "danger"
        )
        return redirect(url_for('admin_bp.admin_labours'))

    # RULE 1: Payments / advances exist?
    if Payment.query.filter(
        Payment.labour_id == labour.id
    ).first():
        flash(
            f"Cannot delete labour '{labour.name}'. "
            f"Payment or advance history exists. Deactivate instead.",
            "danger"
        )
        return redirect(url_for('admin_bp.admin_labours'))

    # RULE 2: Monthly expenses exist?
    if LabourMonthlyExpenses.query.filter(
        LabourMonthlyExpenses.labour_id == labour.id
    ).first():
        flash(
            f"Cannot delete labour '{labour.name}'. "
            f"Expense history exists. Deactivate instead.",
            "danger"
        )
        return redirect(url_for('admin_bp.admin_labours'))

    # --------- CAPTURE AUDIT CONTEXT (BEFORE DELETE) ---------
    labour_name = labour.name
    labour_site_id = labour.site_id

    # --------- HARD DELETE ---------
    try:
        db.session.delete(labour)
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash(
            "Unable to delete labour due to system constraints. "
            "Deactivate instead.",
            "danger"
        )
        return redirect(url_for('admin_bp.admin_labours'))

    # --------- AUDIT LOG (NON-BLOCKING) ---------
    try:
        log_audit(
            company_id=current_user.company_id,
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            site_id=labour_site_id,
            action="labour_deleted",
            details=f"Labour '{labour_name}' deleted",
            ip_address=request.remote_addr,
        )
    except Exception as e:
        current_app.logger.error(f"Audit log failed: {e}")

    flash('Labour deleted successfully', 'success')
    return redirect(url_for('admin_bp.admin_labours'))


    
#------------LABOUR SUMMAY MODAL-------------
from flask import jsonify
from services.labour_summary_service import build_monthly_summary

@admin_bp.route('/api/labour/<int:labour_id>/monthly-summary')
@login_required
def labour_monthly_summary(labour_id):

    month = request.args.get('month')
    if not month:
        return jsonify({"error": "Month is required"}), 400

    labour = Labour.query.get_or_404(labour_id)

    summary = build_monthly_summary(labour, month)

    def file_url(path):
        return url_for('static', filename=path) if path else None

    return jsonify({
        "labour": {
            "name": labour.name,
            "phone": labour.phone,
            "site": labour.site.site_name if labour.site else "-",
            "gate_pass_id": labour.gate_pass_id,
            "photo_url": file_url(labour.photo_path),
            "aadhaar_front_url": file_url(labour.aadhaar_front_path),
            "aadhaar_back_url": file_url(labour.aadhaar_back_path),
            "gate_pass_front_url": file_url(labour.gate_pass_front_path),
            "gate_pass_back_url": file_url(labour.gate_pass_back_path)
        },
        **summary
    })



from flask import send_from_directory, current_app
import os

@admin_bp.route('/uploads/<path:filename>')
@login_required
def uploaded_file(filename):
    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads')
    return send_from_directory(upload_dir, filename)

