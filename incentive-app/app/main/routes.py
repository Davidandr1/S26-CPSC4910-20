from flask import Blueprint, render_template, request, redirect, url_for, session
from sqlalchemy import text
from app.db import engine

main_bp = Blueprint("main", __name__)

NAV_PAGES = [
    ("about", "About"),
    ("store", "Store"),
    ("applications_list", "Applications"),
]

def is_logged_in() -> bool:
    return session.get("user_id") is not None

def require_login_redirect():
    if not is_logged_in():
        return redirect(url_for("auth.login_page"))
    return None

def require_role(role: str):
    r = require_login_redirect()
    if r:
        return r
    if session.get("user_type") != role:
        return "Forbidden", 403
    return None

def fetch_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None

    with engine.connect() as conn:
        u = conn.execute(text("""
            SELECT
                User_ID,
                Username,
                User_FName,
                User_LNAME,
                User_Email,
                User_Phone_Num,
                User_Type
            FROM USERS
            WHERE User_ID = :id
        """), {"id": user_id}).fetchone()

        if not u:
            return None

        user = {
            "user_id": u.User_ID,
            "username": u.Username,
            "first_name": u.User_FName,
            "last_name": u.User_LNAME,
            "email": u.User_Email,
            "phone": u.User_Phone_Num,
            "role": (u.User_Type or "").lower(),
        }

        sponsor_name = None
        if u.User_Type == "Driver":
            row = conn.execute(text("""
                SELECT s.Sponsor_Name
                FROM DRIVERS d
                JOIN SPONSORS s ON s.Sponsor_ID = d.Sponsor_ID
                WHERE d.User_ID = :id
            """), {"id": user_id}).fetchone()
            sponsor_name = row.Sponsor_Name if row else None

        elif u.User_Type == "Sponsor":
            row = conn.execute(text("""
                SELECT s.Sponsor_Name
                FROM SPONSOR_USER su
                JOIN SPONSORS s ON s.Sponsor_ID = su.Sponsor_ID
                WHERE su.User_ID = :id
            """), {"id": user_id}).fetchone()
            sponsor_name = row.Sponsor_Name if row else None

        user["sponsor"] = sponsor_name or "N/A"
        return user


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
    return render_template(
        "about.html",
        user=user,
        sprint_name="Sprint 2",
        sprint_goal="DB-backed login/register + role-based pages",
        nav_pages=NAV_PAGES,
        logged_in=is_logged_in()
    )


@main_bp.get("/driver/home")
def driver_home():
    r = require_role("Driver")
    if r:
        return r
    return render_template("page.html", page_title="Driver Home", nav_pages=NAV_PAGES, logged_in=is_logged_in())


@main_bp.get("/sponsor/home")
def sponsor_home():
    r = require_role("Sponsor")
    if r:
        return r
    return render_template("page.html", page_title="Sponsor Home", nav_pages=NAV_PAGES, logged_in=is_logged_in())


@main_bp.get("/admin/home")
def admin_home():
    r = require_role("Admin")
    if r:
        return r
    return render_template("page.html", page_title="Admin Home", nav_pages=NAV_PAGES, logged_in=is_logged_in())

@main_bp.get("/store")
def storefront():
    r = require_role("Driver")   # Only drivers can shop
    if r:
        return r

    user = fetch_current_user()

    #Temporary fake data until DB is connected
    products = []
    categories = []
    cart_count = 0

    return render_template(
        "storefront.html",
        nav_pages=NAV_PAGES,
        logged_in=is_logged_in(),
        user=user,
        products=products,
        categories=categories,
        cart_count=cart_count
    )


@main_bp.get("/page/<name>")
def blank_page(name):
    r = require_login_redirect()
    if r:
        return r

    allowed = {"page2", "page3"}
    if name not in allowed:
        return "Page not found", 404

    return render_template("page.html", page_title=f"Blank Test Page: {name}",
                           nav_pages=NAV_PAGES, logged_in=is_logged_in())

@main_bp.get("/applications")
def applications_list():
    r = require_role("Sponsor")
    if r:
        r2 = require_role("Admin")
        if r2:
            return r2
    with engine.connect() as conn:
        if session["user_type"] == "Sponsor":
            apps = conn.execute(text(""" SELECT Application_ID, App_Status, App_FName, App_LNAME FROM APPLICATIONS
                                     WHERE App_Sponsor_ID = :sid"""),
                                {"sid": session["sponsor_id"]}).fetchall()
        else:
            apps = conn.execute(text(""" SELECT Application_ID, App_Status, App_FName, App_LNAME FROM APPLICATIONS""")).fetchall()
    return render_template("applications_list.html", apps=apps, nav_pages = NAV_PAGES, logged_in=is_logged_in())

@main_bp.get("/applications/<int:app_id>")
def application_details(app_id):
    r = require_role("Sponsor")
    if r:
        r2 = require_role("Admin")
        if r2:
            return r2
    with engine.connect() as conn:
        app = conn.execute(text(""" SELECT Application_ID, App_Sponsor_ID, App_Status, App_FName, App_LNAME, App_Email, App_Phone_Num,
                                License_Num, App_Time FROM APPLICATIONS
                                 WHERE Application_ID = :aid"""),
                               {"aid": app_id}).fetchone()
    if not app:
        return "Application not found", 404

    if session["user_type"] == "Sponsor" and app.App_Sponsor_ID != session["sponsor_id"]:
        return "Forbidden", 403

    return render_template(
        "application_detail.html",
        app=app, nav_pages=NAV_PAGES, logged_in=is_logged_in())

@main_bp.post("/applications/<int:app_id>/evaluate")
def evaluate_applications(app_id):
    r = require_role("Sponsor")
    if r:
        r2 = require_role("Admin")
        if r2:
            return r2
    decision = request.form.get("decision")

    with engine.connect() as conn:
        app = conn.execute(text(""" SELECT App_Sponsor_ID FROM APPLICATIONS WHERE Application_ID = :aid"""), 
                           {"aid": app_id}).fetchone()
        if not app:
            return "Application not found", 404
        if session["user_type"] == "Sponsor" and app.App_Sponsor_ID != session["sponsor_id"]:
            return "Forbidden", 403

        conn.execute(text("""UPDATE APPLICATIONS SET App_Status = :status WHERE Application_ID = :aid"""), {"status": decision, "aid": app_id})
    return redirect(url_for("main.applications_list"))
