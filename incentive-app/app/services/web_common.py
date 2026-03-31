from flask import Blueprint, redirect, session, url_for
from sqlalchemy import text

from app.db import engine

main_bp = Blueprint("main", __name__)

NAV_PAGES = [
    ("about", "About"),
    ("store", "Store"),
    ("applications_list", "Applications"),
    ("admin_create_page", "Create New Admin"),
    ("sponsor_create_page", "Create New Sponsor User"),
    ("sponsor_products", "My Products"),
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


def require_sponsor_or_admin():
    sponsor_check = require_role("Sponsor")
    if sponsor_check:
        admin_check = require_role("Admin")
        if admin_check:
            return admin_check
    return None


def fetch_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None

    try:
        with engine.connect() as conn:
            u = conn.execute(
                text(
                    """
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
            """
                ),
                {"id": user_id},
            ).fetchone()

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
                row = conn.execute(
                    text(
                        """
                    SELECT s.Sponsor_Name, d.User_Points
                    FROM DRIVERS d
                    JOIN SPONSORS s ON s.Sponsor_ID = d.Sponsor_ID
                    WHERE d.User_ID = :id
                """
                    ),
                    {"id": user_id},
                ).fetchone()
                sponsor_name = row.Sponsor_Name if row else None
                user["points"] = row.User_Points if row and hasattr(row, "User_Points") else 0

            elif u.User_Type == "Sponsor":
                row = conn.execute(
                    text(
                        """
                    SELECT s.Sponsor_Name
                    FROM SPONSOR_USER su
                    JOIN SPONSORS s ON s.Sponsor_ID = su.Sponsor_ID
                    WHERE su.User_ID = :id
                """
                    ),
                    {"id": user_id},
                ).fetchone()
                sponsor_name = row.Sponsor_Name if row else None

            user["sponsor"] = sponsor_name or "N/A"
            return user
    except SQLAlchemyError:
        return None


def get_user_count():
    try:
        with engine.connect() as conn:
            return conn.execute(text("SELECT COUNT(*) AS count FROM USERS")).fetchone()
    except SQLAlchemyError:
        return None
