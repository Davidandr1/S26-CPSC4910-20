from flask import redirect, render_template, session, url_for

from app.services.web_common import (
    NAV_PAGES,
    fetch_current_user,
    get_user_count,
    is_logged_in,
    main_bp,
    require_login_redirect,
)


@main_bp.get("/home")
def home_redirect():
    r = require_login_redirect()
    if r:
        return r

    t = session.get("user_type")
    if t == "Admin":
        return redirect(url_for("main.admin_home"))
    if t == "Sponsor":
        return redirect(url_for("main.sponsor_home"))
    return redirect(url_for("main.driver_home"))


@main_bp.get("/about")
def about_page():
    r = require_login_redirect()
    if r:
        return r

    user = fetch_current_user()
    try:
        count = get_user_count()
        db_status = "Connected"
    except Exception as e:
        count = None
        db_status = f"Error: {str(e)}"

    return render_template(
        "about.html",
        user=user,
        nav_pages=NAV_PAGES,
        logged_in=is_logged_in(),
        db_status=db_status,
        count=count,
    )


@main_bp.get("/page/<name>")
def blank_page(name):
    r = require_login_redirect()
    if r:
        return r

    allowed = {"page2", "page3"}
    if name not in allowed:
        return "Page not found", 404

    return render_template(
        "page.html",
        page_title=f"Blank Test Page: {name}",
        nav_pages=NAV_PAGES,
        logged_in=is_logged_in(),
    )


@main_bp.get("/admin/create")
def admin_create_page():
    return redirect(url_for("auth.admin_create_page"))


@main_bp.get("/sponsor/create")
def sponsor_create_page():
    return redirect(url_for("auth.sponsor_create_page"))
