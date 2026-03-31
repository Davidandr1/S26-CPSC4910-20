from app.services.web_common import main_bp

# Import route groups for registration side effects.
from app.services import web_common_routes as _web_common_routes  # noqa: F401
from app.services.adminService import routes as _admin_routes  # noqa: F401
from app.services.applicationService import routes as _application_routes  # noqa: F401
from app.services.driverService import routes as _driver_routes  # noqa: F401
from app.services.sponsorService import routes as _sponsor_routes  # noqa: F401
from app.services.storeService import routes as _store_routes  # noqa: F401


__all__ = ["main_bp"]
