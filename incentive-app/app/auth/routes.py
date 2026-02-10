from flask import Blueprint, render_template, request, redirect, url_for, session
from sqlalchemy import text
from werkzeug.security import generate_password_hash, check_password_hash

from app.db import engine
from app.auth.forms import LoginForm, RegisterForm, normalize_phone

auth_bp = Blueprint("auth", __name__)

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

@auth_bp.get("/")
def login_page():
    form = LoginForm(meta={"csrf": False})
    return render_template("login.html", form=form, error=None, nav_pages=NAV_PAGES, logged_in=is_logged_in())

@auth_bp.post("/login")
def login_submit():
    form = LoginForm(request.form, meta={"csrf": False})
    if not form.validate():
        return render_template("login.html", form=form, error=None, nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400

    username = form.username.data.strip()
    password = form.password.data

    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT User_ID, Username, Encrypted_Password, User_Type
            FROM USERS
            WHERE Username = :u
        """), {"u": username}).fetchone()

    if not row or not row.Encrypted_Password or not check_password_hash(row.Encrypted_Password, password):
        return render_template("login.html", form=form, error="Invalid username or password.", nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400

    session["user_id"] = row.User_ID
    session["username"] = row.Username
    session["user_type"] = row.User_Type
    session.permanent = True  # enables PERMANENT_SESSION_LIFETIME

    return redirect(url_for("main.home_redirect"))

@auth_bp.get("/register")
def register_page():
    form = RegisterForm(meta={"csrf": False})

    with engine.connect() as conn:
        sponsors = conn.execute(text("""
            SELECT Sponsor_Name
            FROM SPONSORS
            ORDER BY Sponsor_Name
        """)).fetchall()

    sponsor_names = [r.Sponsor_Name for r in sponsors]

    return render_template(
        "register.html",
        form=form,
        error=None,
        sponsors=sponsor_names,
        nav_pages=NAV_PAGES,
        logged_in=is_logged_in()
    )

@auth_bp.post("/register")
def register_submit():
    form = RegisterForm(request.form, meta={"csrf": False})
    if not form.validate():
        # repopulate sponsor list on error
        with engine.connect() as conn:
            sponsors = conn.execute(text("SELECT Sponsor_Name FROM SPONSORS ORDER BY Sponsor_Name")).fetchall()
        sponsor_names = [r.Sponsor_Name for r in sponsors]

        return render_template("register.html", form=form, error=None, sponsors=sponsor_names,
                               nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400

    username = form.username.data.strip()
    pw_hash = generate_password_hash(form.password.data)

    fname = form.first_name.data.strip()
    lname = form.last_name.data.strip()
    email = form.email.data.strip()
    phone = normalize_phone(form.phone.data)
    license_num = form.license_number.data.strip()
    sponsor_name = form.sponsor.data.strip()

    try:
        with engine.begin() as conn:
            sponsor = conn.execute(
                text("SELECT Sponsor_ID FROM SPONSORS WHERE Sponsor_Name = :n"),
                {"n": sponsor_name}
            ).fetchone()

            if not sponsor:
                with engine.connect() as c2:
                    sponsors = c2.execute(text("SELECT Sponsor_Name FROM SPONSORS ORDER BY Sponsor_Name")).fetchall()
                sponsor_names = [r.Sponsor_Name for r in sponsors]

                return render_template("register.html", form=form,
                                       error="Sponsor not found. Please choose one from the dropdown.",
                                       sponsors=sponsor_names,
                                       nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400

            existing = conn.execute(
                text("SELECT User_ID FROM USERS WHERE Username = :u OR User_Email = :e OR User_Phone_Num = :p"),
                {"u": username, "e": email, "p": phone}
            ).fetchone()

            if existing:
                with engine.connect() as c2:
                    sponsors = c2.execute(text("SELECT Sponsor_Name FROM SPONSORS ORDER BY Sponsor_Name")).fetchall()
                sponsor_names = [r.Sponsor_Name for r in sponsors]

                return render_template("register.html", form=form,
                                       error="Username, email, or phone already exists.",
                                       sponsors=sponsor_names,
                                       nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400

            conn.execute(text("""
                INSERT INTO USERS
                  (Username, Encrypted_Password, User_FName, User_LNAME, User_Email, User_Phone_Num, User_Type)
                VALUES
                  (:u, :pw, :fn, :ln, :em, :ph, 'Driver')
            """), {"u": username, "pw": pw_hash, "fn": fname, "ln": lname, "em": email, "ph": phone})

            new_id = conn.execute(text("SELECT LAST_INSERT_ID() AS id")).fetchone().id

            conn.execute(text("""
                INSERT INTO DRIVERS (User_ID, License_Num, User_Points, Sponsor_ID, App_Status)
                VALUES (:uid, :lic, 0, :sid, 'Received')
            """), {"uid": new_id, "lic": license_num, "sid": sponsor.Sponsor_ID})

            session["user_id"] = new_id
            session["username"] = username
            session["user_type"] = "Driver"
            session.permanent = True

    except Exception:
        with engine.connect() as c2:
            sponsors = c2.execute(text("SELECT Sponsor_Name FROM SPONSORS ORDER BY Sponsor_Name")).fetchall()
        sponsor_names = [r.Sponsor_Name for r in sponsors]

        return render_template("register.html", form=form,
                               error="Database error creating account.",
                               sponsors=sponsor_names,
                               nav_pages=NAV_PAGES, logged_in=is_logged_in()), 500

    return redirect(url_for("main.driver_home"))

@auth_bp.get("/admin/create")
def admin_create_page():
    r = require_role("Admin"):
    if r:
        return r
    form = RegisterForm(request.form, meta={"csrf": False})
    return render_template("adminCreate.html", form=form, error=None, 
                            nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400  

@auth_bp.post("/admin/create")
def admin_create_submit():
    r = require_role("Admin")
    if r:
        return r
    form = RegisterForm(request.form, meta={"csrf": False})
    if not form.validate():
        return render_template("admin_create.html", form=form, error=None,
                               nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400
    username = form.username.data.strip()
    pw_hash = generate_password_hash(form.password.data)
    fname = form.first_name.data.strip()
    lname = form.last_name.data.strip()
    email = form.email.data.strip()
    phone = normalize_phone(form.phone.data)

    try:
        with engine.begin() as conn:
             existing = conn.execute( text("SELECT User_ID FROM USERS WHERE Username = :u OR User_Email = :e OR User_Phone_Num = :p"),
                {"u": username, "e": email, "p": phone}).fetchone()
            if existing:
                return render_template("admin_create.html", form=form,
                                       error="Username, email, or phone already exists",
                                       nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400
            conn.execute(text("""INSERT INTO USERS
                (Username, Encrypted_Password, User_FName, User_LNAME, User_Email, User_Phone_Num, User_Type)
                VALUES (:u, :pw, :fn, :ln, :em, :ph, 'Admin')
            """), {"u": username, "pw": pw_hash, "fn": fname, "ln": lname, "em": email, "ph": phone})
        
            new_id = conn.execute(text("SELECT LAST_INSERT_ID() AS id")).fetchone().id
        
            conn.execute(text("INSERT INTO ADMINS (User_ID, Security_Level) VALUES (:uid, 1)")
                         {"uid": new_id})
        
    except Exception:
        return render_template("admin_create.html", form=form, error="Database error creating admin",
                               nav_pages=NAV_PAGES, logged_in=is_logged_in()), 500
        return redirect(url_for("main.admin_home))


@auth_bp.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login_page"))
