from extensions import db
from models import Site, User


def get_company_sites(company_id):
    return Site.query.filter_by(
        company_id=company_id
    ).order_by(Site.id).all()


def create_site(company_id, site_name, location=None, address=None, manager_id=None):
    if not site_name:
        raise ValueError("Site name is required")

    site = Site(
        site_name=site_name,
        location=location,
        address=address,
        is_active=True,
        company_id=company_id
    )

    db.session.add(site)
    db.session.flush()  # get site.id safely

    if manager_id:
        manager = User.query.filter_by(
            id=manager_id,
            role='manager',
            company_id=company_id
        ).first()
        if manager:
            manager.site_id = site.id

    db.session.commit()
    return site


def update_site(company_id, site_id, site_name, location, manager_id):
    site = Site.query.filter_by(
        id=site_id,
        company_id=company_id
    ).first_or_404()

    site.site_name = site_name
    site.location = location

    # unassign old manager
    User.query.filter_by(
        site_id=site.id,
        company_id=company_id,
        role='manager'
    ).update({"site_id": None})

    if manager_id:
        manager = User.query.filter_by(
            id=manager_id,
            role='manager',
            company_id=company_id
        ).first()
        if manager:
            manager.site_id = site.id

    db.session.commit()
    return site


def deactivate_site(company_id, site_id):
    site = Site.query.filter_by(
        id=site_id,
        company_id=company_id
    ).first_or_404()

    site.is_active = False
    db.session.commit()
    return site


def toggle_site_status(company_id, site_id):
    site = Site.query.filter_by(
        id=site_id,
        company_id=company_id
    ).first_or_404()

    site.is_active = not site.is_active
    db.session.commit()
    return site
