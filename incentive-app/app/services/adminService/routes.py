from flask import render_template, request

from app.services.adminService.adminService import AdminService
from app.services.web_common import NAV_PAGES, is_logged_in, main_bp, require_role


@main_bp.get("/admin/home")
def admin_home():
    r = require_role("Admin")
    if r:
        return r
    return render_template(
        "adminHome.html",
        page_title="Admin Home",
        nav_pages=NAV_PAGES,
        logged_in=is_logged_in(),
    )


@main_bp.get("/admin/sponsors")
def admin_sponsors():
    r = require_role("Admin")
    if r:
        return r

    sponsors = AdminService.get_sponsors_with_driver_counts()
    return render_template(
        "sponsorList.html",
        nav_pages=NAV_PAGES,
        logged_in=is_logged_in(),
        sponsors=sponsors,
    )


@main_bp.get("/admin/users")
def admin_users():
    r = require_role("Admin")
    if r:
        return r

    sort = request.args.get("sort", "username")
    users, current_sort = AdminService.get_users(sort)
    return render_template(
        "userList.html",
        nav_pages=NAV_PAGES,
        logged_in=is_logged_in(),
        users=users,
        current_sort=current_sort,
    )
