from flask import (
    render_template, request, redirect, url_for,
    flash, jsonify, current_app
)
from flask_login import login_required, current_user
from extensions import db
from models import Labour, Site
from services.audit_service import log_audit
from services.labour_summary_service import build_monthly_summary
from sqlalchemy import func, or_

from . import manager_bp

# ✅ SAME UTIL USED BY ADMIN (CRITICAL)
from routes.admin.utils import save_and_compress_image
from sqlalchemy.exc import IntegrityError
import shutil
import os
import re


# ============================
# MANAGER – LABOURS LIST
# ============================
@manager_bp.route('/labours')
@login_required
def manager_labours():

    # 🔒 HARD GUARD — manager must have a site
    if not current_user.site_id:
        flash("You are not assigned to any site. Contact admin.", "danger")
        return redirect(url_for("manager_bp.manager_dashboard"))

    search = request.args.get('search', '').strip()

    query = Labour.query.filter(
        Labour.company_id == current_user.company_id,
        Labour.site_id == current_user.site_id,
        Labour.is_active == True
    )

    if search:
        query = query.filter(
            Labour.name.ilike(f"%{search}%") |
            Labour.phone.ilike(f"%{search}%") |
            Labour.gate_pass_id.ilike(f"%{search}%")
        )

    labours = query.order_by(Labour.name.asc()).all()

    return render_template(
        'manager_labours.html',
        labours=labours,
        search=search
    )


# ============================
# MANAGER – ADD LABOUR
# ============================
@manager_bp.route('/labours/add', methods=['GET', 'POST'])
@login_required
def manager_add_labour():

    site = Site.query.filter_by(
        id=current_user.site_id,
        company_id=current_user.company_id,
        is_active=True
    ).first_or_404()

    if request.method == 'POST':

        phone = request.form.get('phone', '').strip()

        # ---- DUPLICATE CHECK ----
        existing = Labour.query.filter_by(
            phone=phone,
            site_id=site.id,
            company_id=current_user.company_id,
            is_active=True
        ).first()

        if existing:
            flash("Labour with this phone already exists.", "danger")
            return redirect(url_for('manager_bp.manager_add_labour'))

        # ---- CREATE LABOUR (STEP 1) ----
        labour = Labour(
            gate_pass_id=request.form.get('gate_pass_id') or None,
            name=request.form.get('name'),
            phone=phone,
            bank_account=request.form.get('bank_account'),
            ifsc_code=request.form.get('ifsc_code'),
            site_id=site.id,
            company_id=current_user.company_id,
            daily_wage=None,
            is_active=True                # 🔒 FORCED
        )

        try:
            db.session.add(labour)
            db.session.commit()  # ⚠️ REQUIRED to get labour.id
        except IntegrityError:
            db.session.rollback()
            flash("Duplicate labour detected.", "danger")
            return redirect(url_for('manager_bp.manager_add_labour'))

        # ---- FILE UPLOADS (STEP 2) ----
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

        except Exception as e:
            db.session.delete(labour)
            db.session.commit()
            upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'labours', str(labour.id))
            if os.path.exists(upload_dir):
                shutil.rmtree(upload_dir, ignore_errors=True)
            current_app.logger.error(e)
            flash("File upload failed", "danger")
            return redirect(url_for('manager_bp.manager_labours'))

        # ---- AUDIT LOG ----
        try:
            log_audit(
                company_id=current_user.company_id,
                user_id=current_user.id,
                username=current_user.username,
                role=current_user.role,
                site_id=site.id,
                action="manager_labour_added",
                details=f"Labour '{labour.name}' added by manager",
                ip_address=request.remote_addr
            )
        except Exception:
            pass

        flash("Labour added successfully", "success")
        return redirect(url_for('manager_bp.manager_labours'))

    return render_template('manager_add_labour.html', site=site)


# ============================
# MANAGER – EDIT LABOUR
# (NO WAGE, NO ACTIVE TOGGLE)
# ============================
@manager_bp.route('/labours/<int:labour_id>/edit', methods=['GET', 'POST'])
@login_required
def manager_edit_labour(labour_id):

    # 🔐 SECURITY: scope by company + site
    labour = Labour.query.filter_by(
        id=labour_id,
        company_id=current_user.company_id,
        site_id=current_user.site_id
    ).first_or_404()

    if request.method == 'POST':

        phone = (request.form.get('phone') or '').strip()
        bank_account = (request.form.get('bank_account') or '').strip()

        # ---- VALIDATIONS ----
        if phone and not re.fullmatch(r"\d{10}", phone):
            flash("Phone number must be exactly 10 digits.", "danger")
            return redirect(url_for("manager_bp.manager_edit_labour", labour_id=labour.id))

        if bank_account and not re.fullmatch(r"\d+", bank_account):
            flash("Bank account number must contain digits only.", "danger")
            return redirect(url_for("manager_bp.manager_edit_labour", labour_id=labour.id))

        # --------------------
        # BASIC INFO (ALLOWED)
        # --------------------
        labour.name = (request.form.get('name') or '').strip()
        labour.phone = phone
        labour.gate_pass_id = (request.form.get('gate_pass_id') or '').strip() or None
        labour.bank_account = bank_account
        labour.ifsc_code = (request.form.get('ifsc_code') or '').strip()

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Another labour with this phone number already exists for this site.", "danger")
            return redirect(url_for('manager_bp.manager_edit_labour', labour_id=labour.id))

        # --------------------
        # DOCUMENT UPLOADS
        # (SAME AS ADMIN)
        # --------------------
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

        except Exception as e:
            db.session.rollback()
            flash("Failed to upload documents", "danger")
            return redirect(
                url_for('manager_bp.manager_edit_labour', labour_id=labour.id)
            )

        # --------------------
        # AUDIT LOG
        # --------------------
        try:
            log_audit(
                company_id=current_user.company_id,
                user_id=current_user.id,
                username=current_user.username,
                role=current_user.role,
                site_id=current_user.site_id,
                action="manager_labour_updated_with_docs",
                details=f"Labour '{labour.name}' updated with documents by manager",
                ip_address=request.remote_addr
            )
        except Exception:
            pass

        flash("Labour updated successfully", "success")
        return redirect(url_for('manager_bp.manager_labours'))

    return render_template(
        'manager_edit_labour.html',
        labour=labour
    )



# ============================
# MANAGER – LABOUR SUMMARY API
# ============================
@manager_bp.route("/api/labour/<int:labour_id>/monthly-summary")
@login_required
def manager_labour_summary(labour_id):

    labour = Labour.query.filter_by(
        id=labour_id,
        site_id=current_user.site_id,
        company_id=current_user.company_id
    ).first_or_404()

    month = request.args.get("month")
    if not month:
        return {"error": "Month required"}, 400

    summary = build_monthly_summary(
        labour=labour,
        month=month,
        site_id=current_user.site_id
    )

    def file_url(path):
        return url_for('static', filename=path) if path else None

    return jsonify({
        "labour": {
            "name": labour.name,
            "phone": labour.phone,
            "gate_pass_id": labour.gate_pass_id,
            "site": labour.site.site_name,
            "photo_url": file_url(labour.photo_path),
            "aadhaar_front_url": file_url(labour.aadhaar_front_path),
            "aadhaar_back_url": file_url(labour.aadhaar_back_path),
            "gate_pass_front_url": file_url(labour.gate_pass_front_path),
            "gate_pass_back_url": file_url(labour.gate_pass_back_path),
        },
        **summary
    })
