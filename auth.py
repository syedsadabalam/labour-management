# auth.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import bcrypt

from extensions import db
from models import User
from services.audit_service import log_audit


auth_bp = Blueprint('auth', __name__, template_folder='templates')


def _is_bcrypt_hash(value: str) -> bool:
    return isinstance(value, str) and value.startswith(('$2a$', '$2b$', '$2y$'))


@auth_bp.route('/auth/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        # already logged in → route by role
        if current_user.role == 'super_admin':
            return redirect(url_for('admin_bp.super_admin_companies'))
        elif current_user.role == 'admin':
            return redirect(url_for('admin_bp.admin_dashboard'))
        elif current_user.role == 'manager':
            return redirect(url_for('manager_bp.manager_dashboard'))
        else:
            logout_user()
            flash('Invalid role configuration', 'danger')
            return redirect(url_for('auth.login'))

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''

        if not username or not password:
            flash('Enter username and password', 'warning')
            return render_template('login.html')

        # 🔐 IMPORTANT: login lookup must NOT filter by company_id
        user = User.query.filter_by(username=username).first()

        if not user:
            flash('Invalid username or password', 'danger')
            return render_template('login.html')

        stored = user.password or ''
        authenticated = False

        # 1️⃣ Werkzeug hash (pbkdf2, scrypt, etc.)
        try:
            if stored and check_password_hash(stored, password):
                authenticated = True
        except ValueError:
            pass

        # 2️⃣ bcrypt (legacy support)
        if not authenticated and _is_bcrypt_hash(stored):
            try:
                if bcrypt.checkpw(password.encode('utf-8'), stored.encode('utf-8')):
                    authenticated = True
                    # upgrade to Werkzeug hash
                    try:
                        user.password = generate_password_hash(password)
                        db.session.add(user)
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
            except Exception:
                pass

        # 3️⃣ plaintext fallback (legacy, auto-upgrade)
        if not authenticated and stored == password:
            authenticated = True
            try:
                user.password = generate_password_hash(password)
                db.session.add(user)
                db.session.commit()
            except Exception:
                db.session.rollback()

        if not authenticated:
            flash('Invalid username or password', 'danger')
            return render_template('login.html')

        # ✅ LOGIN SUCCESS
        login_user(user)

    
        # ---- AUDIT (NON-BLOCKING) ----
        try:
            log_audit(
                company_id=user.company_id,
                user_id=user.id,
                username=user.username,
                role=user.role,
                site_id=user.site_id,
                action='login',
                details='User logged in',
                ip_address=request.remote_addr
            )
        except Exception:
            pass

        # ---- ROLE-BASED REDIRECT (CRITICAL) ----
        if user.role == 'super_admin':
            return redirect(url_for('admin_bp.super_admin_companies'))

        elif user.role == 'admin':
            return redirect(url_for('admin_bp.admin_dashboard'))

        elif user.role == 'manager':
            return redirect(url_for('manager_bp.manager_dashboard'))

        else:
            logout_user()
            flash('Invalid role configuration', 'danger')
            return redirect(url_for('auth.login'))

    return render_template('login.html')


@auth_bp.route('/auth/logout')
@login_required
def logout():
    try:
        log_audit(
            company_id=current_user.company_id,
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            site_id=current_user.site_id,
            action='logout',
            details='User logged out',
            ip_address=request.remote_addr
        )
    except Exception:
        pass

    logout_user()
    flash('Logged out successfully', 'info')
    return redirect(url_for('auth.login'))
