# services/labour_service.py
from sqlalchemy import or_, func
from models import Labour, Site

def get_admin_labours(
    *,
    company_id,
    search=None,
    site_id=None,
    page=1,
    per_page=30
):
    query = Labour.query.filter(
        Labour.company_id == company_id
    )

    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                Labour.name.ilike(like),
                Labour.phone.ilike(like),
                func.coalesce(Labour.gate_pass_id, '').ilike(like)
            )
        )

    if site_id:
        query = query.filter(Labour.site_id == site_id)

    pagination = query.order_by(Labour.id.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )

    sites = Site.query.filter_by(
        company_id=company_id
    ).order_by(Site.site_name).all()


    return pagination, sites
