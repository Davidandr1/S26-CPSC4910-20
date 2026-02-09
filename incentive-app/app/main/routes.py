from flask import Blueprint, render_template, redirect, url_for, session
from sqlalchemy import text
from app.db import engine

main_bp = Blueprint("main", __name__)

NAV_PAGES = [
    ("about", "About"),
    ("page", "Blank Page 1", "page1"),
    ("page", "Blank Page 2", "page2"),
    ("page", "Blank Page 3", "page3"),
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


@main_bp.get("/page/<name>")
def blank_page(name):
    r = require_login_redirect()
    if r:
        return r

    allowed = {"page1", "page2", "page3"}
    if name not in allowed:
        return "Page not found", 404

    return render_template("page.html", page_title=f"Blank Test Page: {name}",
                           nav_pages=NAV_PAGES, logged_in=is_logged_in())