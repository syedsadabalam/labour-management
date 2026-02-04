from flask import Blueprint

admin_bp = Blueprint(
    'admin_bp',
    __name__,
    url_prefix='/admin',
    template_folder='templates'
)

from .admin_dashboard import *
from .admin_labours import *
from .admin_attendance import *
from .admin_sites import *
from .admin_payments import *
from .admin_expenses import *
from .admin_managers import *
from .admin_audit import *
from .admin_reports import *
from . import super_admin
from . import plan


