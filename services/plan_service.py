from flask import abort
from flask_login import current_user
from models import Company, Plan
from extensions import db

from datetime import date

def is_plan_expired(company):
    if not company or not company.plan_expires_at:
        return False
    return company.plan_expires_at < date.today()


class PlanService:
    """
    Central place for ALL plan / subscription checks.
    Backend enforcement only. UI is secondary.
    """

    @staticmethod
    def _get_company_and_plan():
        """
        Fetch current company and its plan safely.
        """
        company = (
            db.session.query(Company)
            .filter(Company.id == current_user.company_id)
            .first()
        )

        if not company:
            abort(403, description="Company not found")

        plan = (
            db.session.query(Plan)
            .filter(Plan.id == company.plan_id)
            .first()
        )

        if not plan:
            abort(403, description="Plan not assigned")

        return company, plan

    # =========================
    # EXPORT PERMISSIONS
    # =========================
    @staticmethod
    def require_export_permission(required_level: str):
        """
        required_level:
            - 'monthly'  → only monthly payroll export
            - 'all'      → all exports
        """

        _, plan = PlanService._get_company_and_plan()

        if plan.export_level == 'all':
            return True

        if plan.export_level == 'monthly' and required_level == 'monthly':
            return True

        abort(
            403,
            description="Your plan does not allow this export. Please upgrade."
        )

    # =========================
    # SITE LIMIT
    # =========================
    @staticmethod
    def require_site_limit(current_site_count: int):
        _, plan = PlanService._get_company_and_plan()

        if plan.max_sites == -1:
            return True

        if current_site_count >= plan.max_sites:
            abort(
                403,
                description="Site limit reached. Upgrade your plan."
            )

        return True

    # =========================
    # LABOUR LIMIT
    # =========================
    @staticmethod
    def require_labour_limit(current_labour_count: int):
        _, plan = PlanService._get_company_and_plan()

        if plan.max_labours == -1:
            return True

        if current_labour_count >= plan.max_labours:
            abort(
                403,
                description="Labour limit reached. Upgrade your plan."
            )

        return True

    # =========================
    # AUDIT LOG ACCESS
    # =========================
    @staticmethod
    def require_audit_access():
        _, plan = PlanService._get_company_and_plan()

        if not plan.allow_audit:
            abort(
                403,
                description="Audit logs are not available in your plan."
            )

        return True


