import os
from werkzeug.security import generate_password_hash

# Force SQLite for local testing
os.environ['DATABASE_URL'] = 'sqlite:///local_test.db'

from app import create_app
from extensions import db
from models import User, Plan, Company, Site

app = create_app()

with app.app_context():
    # Create all tables
    db.create_all()

    # Create dummy data if it doesn't exist
    if not Plan.query.first():
        plan = Plan(name='Pro Plan', price=999, max_sites=10, max_labours=100)
        db.session.add(plan)
        db.session.commit()
        
        company = Company(company_name='Test Company', plan_id=plan.id)
        db.session.add(company)
        db.session.commit()
        
        site = Site(site_name='Test Site', company_id=company.id)
        db.session.add(site)
        db.session.commit()

        # Create an admin user
        admin = User(
            username='admin',
            password=generate_password_hash('password'),
            role='admin',
            company_id=company.id
        )
        db.session.add(admin)
        
        # Create a manager user
        manager = User(
            username='manager',
            password=generate_password_hash('password'),
            role='manager',
            company_id=company.id,
            site_id=site.id
        )
        db.session.add(manager)
        db.session.commit()

        print("Database initialized successfully!")
        print("Admin Login - Username: admin | Password: password")
        print("Manager Login - Username: manager | Password: password")
    else:
        print("Database already initialized!")
