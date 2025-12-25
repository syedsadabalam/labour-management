# auth.py (bcrypt-aware)
from flask import Blueprint, render_template, request, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, log_event

import bcrypt

auth_bp = Blueprint('auth', __name__, template_folder='templates')

def _is_bcrypt_hash(s):
    return isinstance(s, str) and s.startswith(('$2a$', '$2b$', '$2y$'))

@auth_bp.route('/auth/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        if not username or not password:
            flash('Enter username and password', 'warning')
            return render_template('login.html')

        user = User.query.filter_by(username=username).first()
        if not user:
            flash('Invalid username or password', 'danger')
            return render_template('login.html')

        stored = user.password or ''

        # 1) Try Werkzeug hash check (handles pbkdf2 etc.)
        try:
            if stored and check_password_hash(stored, password):
                login_user(user)
                try: log_event(user_id=user.id, username=user.username, role=user.role, site_id=user.site_id, action='login', details='login ok (werkzeug)')
                except: pass
                return redirect(url_for('admin_bp.admin_dashboard') if user.role=='admin' else url_for('manager_bp.manager_dashboard'))
        except ValueError:
            # unknown hash format for Werkzeug
            pass

        # 2) If it's a bcrypt hash, try bcrypt
        if _is_bcrypt_hash(stored):
            try:
                ok = bcrypt.checkpw(password.encode('utf-8'), stored.encode('utf-8'))
                if ok:
                    # upgrade to Werkzug hashed password for future
                    try:
                        user.password = generate_password_hash(password)
                        db.session.add(user)
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
                    login_user(user)
                    try: log_event(user_id=user.id, username=user.username, role=user.role, site_id=user.site_id, action='login', details='login ok (bcrypt -> upgraded)')
                    except: pass
                    return redirect(url_for('admin_bp.admin_dashboard') if user.role=='admin' else url_for('manager_bp.manager_dashboard'))
            except Exception:
                pass

        # 3) Fallback: stored plaintext (not recommended)
        if stored == password:
            try:
                user.password = generate_password_hash(password)
                db.session.add(user)
                db.session.commit()
            except Exception:
                db.session.rollback()
            login_user(user)
            try: log_event(user_id=user.id, username=user.username, role=user.role, site_id=user.site_id, action='login', details='login ok (plaintext -> upgraded)')
            except: pass
            return redirect(url_for('admin_bp.admin_dashboard') if user.role=='admin' else url_for('manager_bp.manager_dashboard'))

        flash('Invalid username or password', 'danger')
        return render_template('login.html')

    return render_template('login.html')


@auth_bp.route('/auth/logout')
@login_required
def logout():
    try: log_event(user_id=current_user.id, username=current_user.username, role=current_user.role, site_id=current_user.site_id, action='logout', details='user logged out')
    except: pass
    logout_user()
    flash('Logged out', 'info')
    return redirect(url_for('auth.login'))
