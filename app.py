import os
from flask import Flask, render_template
from config import Config
from extensions import db, login_manager
from models import User

from flask import redirect, url_for, request, send_from_directory
from flask_login import current_user
from services.plan_service import is_plan_expired


def create_app():
    # --------------------
    # APP INIT
    # --------------------
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static"
    )
    app.config.from_object(Config)

    # --------------------
    # EXTENSIONS
    # --------------------
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    # --------------------
    # USER LOADER
    # --------------------
    @login_manager.user_loader
    def load_user(user_id):
        try:
            return User.query.get(int(user_id))
        except Exception:
            return None

    # --------------------
    # PLAN CHECK EXPIRY
    # --------------------
    
    @app.before_request
    def enforce_plan_expiry():
        if not current_user.is_authenticated:
            return

        # Super Admin is NEVER blocked
        if current_user.role == 'super_admin':
            return

        # Only admins and managers are checked
        if current_user.role in ['admin', 'manager']:
            company = current_user.company

            if company and is_plan_expired(company):
                allowed_paths = [
                    url_for('admin_bp.plan_expired'),
                    url_for('auth.logout')
                ]

                # allow static files
                if request.path.startswith('/static'):
                    return

                # already on allowed page
                if request.path in allowed_paths:
                    return

                return redirect(url_for('admin_bp.plan_expired'))

    # --------------------
    # BLUEPRINT IMPORTS
    # (IMPORTANT: import AFTER app creation)
    # --------------------
    from routes.admin import admin_bp
    from routes.manager import manager_bp
    from auth import auth_bp

    # --------------------
    # BLUEPRINT REGISTER
    # --------------------
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(manager_bp)

    # --------------------
    # BASIC ROUTES
    # --------------------
    @app.route("/")
    def index():
        return render_template("landing.html")

    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory(
            os.path.join(app.root_path, "static", "landing_images"),
            "logo.png",
            mimetype="image/png"
        )

    return app


# --------------------
# APP ENTRY POINT
# --------------------
if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)


