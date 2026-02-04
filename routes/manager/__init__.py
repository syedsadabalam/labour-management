from flask import Blueprint

manager_bp = Blueprint(
    'manager_bp',
    __name__,
    url_prefix='/manager'
)

from .manager_dashboard import *
from .manager_payments import *
from .manager_attendance import *
from .manager_labours import *
