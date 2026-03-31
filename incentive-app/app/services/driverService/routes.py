from flask import jsonify, render_template, session

from app.services.driverService.driverService import DriverService
from app.services.web_common import NAV_PAGES, is_logged_in, main_bp, require_role


@main_bp.get("/driver/home")
def driver_home():
    r = require_role("Driver")
    if r:
        return r

    driver_id = session.get("user_id")
    transactions, points = DriverService.get_home_data(driver_id)
    return render_template(
        "driverHome.html",
        page_title="Driver Home",
        nav_pages=NAV_PAGES,
        logged_in=is_logged_in(),
        transactions=transactions,
        points=points,
    )


@main_bp.get("/driver/points")
def driver_points_api():
    r = require_role("Driver")
    if r:
        return r

    driver_id = session.get("user_id")
    points = DriverService.get_points(driver_id)
    return jsonify({"points": points})
