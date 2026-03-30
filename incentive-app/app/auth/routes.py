from flask import Blueprint, render_template, request, redirect, url_for, session
from sqlalchemy import text
from werkzeug.security import generate_password_hash, check_password_hash

from app.db import engine
from app.auth.forms import LoginForm, RegisterForm, ChangePasswordForm, normalize_phone, AdminCreateForm, SponsorCreateForm
from app.auth.forms import ProfileForm
import secrets, string, requests, os

auth_bp = Blueprint("auth", __name__)

NAV_PAGES = [
    ("about", "About"),
]

def is_logged_in() -> bool:
    return session.get("user_id") is not None

def require_login_redirect():
    if not is_logged_in():
        return redirect(url_for("auth.login_page"))
    if not session_valid(session.get("user_id"), session.get("session_version")):
        session.clear()
        return redirect(url_for("auth.login_page"))
    return None

def require_role(role: str):
    r = require_login_redirect()
    if r:
        return r
    if session.get("user_type") != role:
        return "Forbidden", 403
    return None

def session_valid(user_id, session_version):
    with engine.connect() as conn:
        row = conn.execute(text("""SELECT Session_Version 
                                FROM USERS WHERE User_ID = :uid""")
                                ,{"uid": user_id}).fetchone()
        if not row:
            return False
        return row.Session_Version == session_version

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
            SELECT User_ID, Username, Encrypted_Password, User_Type, Session_Version
            FROM USERS
            WHERE Username = :u
        """), {"u": username}).fetchone()

    if not row:
        # If no user, check if there's a pending application with this username
        with engine.connect() as conn:
            app_row = conn.execute(text("""
                SELECT Application_ID, App_Status, App_Time, Denial_Reason
                FROM APPLICATIONS WHERE App_Username = :u"""), 
                {"u": username}).fetchone()

        if app_row:
            submitted = app_row.App_Time
            try:
                # format timestamp for display
                submitted = submitted.strftime("%Y-%m-%d %H:%M:%S") if submitted else None
            except Exception:
                pass

            return render_template("application_status.html",username=username, status=app_row.App_Status,submitted=submitted, denial_reason=app_row.Denial_Reason,
                                    nav_pages=NAV_PAGES,logged_in=is_logged_in()), 200

        return render_template("login.html", form=form, error="Invalid username or password.", nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400

    if not row.Encrypted_Password or not check_password_hash(row.Encrypted_Password, password):
        return render_template("login.html", form=form, error="Invalid username or password.", nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400

    session["user_id"] = row.User_ID
    session["username"] = row.Username
    session["user_type"] = row.User_Type
    session["session_version"] = row.Session_Version
    session.permanent = True  # enables PERMANENT_SESSION_LIFETIME

    with engine.connect() as conn:
        if row.User_Type == "Sponsor":
            srow = conn.execute(text("""
                SELECT su.Sponsor_ID, s.Sponsor_Name
                FROM SPONSOR_USER su
                JOIN SPONSORS s ON su.Sponsor_ID = s.Sponsor_ID
                WHERE su.User_ID = :uid
            """), {"uid": row.User_ID}).fetchone()
            if srow:
                session["sponsor_id"] = srow.Sponsor_ID
                session["sponsor_name"] = srow.Sponsor_Name
        if row.User_Type == "Driver":
            drow = conn.execute(text("""
                SELECT ds.Sponsor_ID, s.Sponsor_Name
                FROM DRIVER_SPONSORS ds
                JOIN SPONSORS s ON ds.Sponsor_ID = s.Sponsor_ID
                WHERE ds.Driver_ID = :uid AND ds.Is_Active = TRUE
                ORDER BY ds.Created_At ASC
            """), {"uid": row.User_ID}).fetchone()
            if drow:
                session["active_sponsor_id"] = drow.Sponsor_ID
                session["active_sponsor_name"] = drow.Sponsor_Name
            else:
                session["active_sponsor_id"] = None
                session["active_sponsor_name"] = None
            session.pop("sponsor_id", None)
            session.pop("sponsor_name", None)
    
    return redirect(url_for("main.home_redirect"))


@auth_bp.post("/application/cancel")
def cancel_application():
    # Allow applicants to cancel their application (only pending allowed)
    username = request.form.get("username", "").strip()
    if not username:
        return redirect(url_for("auth.login_page"))

    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM APPLICATIONS WHERE App_Username = :u AND App_Status = 'Pending'"), {"u": username})
    except Exception:
        return render_template("page.html", page_title="Error Cancelling Application", nav_pages=NAV_PAGES, logged_in=is_logged_in()), 500

    return render_template("page.html", page_title="Application Cancelled", nav_pages=NAV_PAGES, logged_in=is_logged_in())


@auth_bp.get("/change-password")
def change_password_page():
    r = require_login_redirect()
    if r:
        return r
    form = ChangePasswordForm(meta={"csrf": False})
    return render_template("change_password.html", form=form, error=None, nav_pages=NAV_PAGES, logged_in=is_logged_in())


@auth_bp.post("/change-password")
def change_password_submit():
    r = require_login_redirect()
    if r:
        return r
    form = ChangePasswordForm(request.form, meta={"csrf": False})
    if not form.validate():
        return render_template("change_password.html", form=form, error=None, nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400

    current = form.current_password.data
    new_pw = form.new_password.data
    user_id = session.get("user_id")

    try:
        with engine.begin() as conn:
            row = conn.execute(text("SELECT Encrypted_Password, Prev_Password FROM USERS WHERE User_ID = :uid"), {"uid": user_id}).fetchone()
            if not row or not row.Encrypted_Password or not check_password_hash(row.Encrypted_Password, current):
                return render_template("change_password.html", form=form, error="Current password is incorrect.", nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400

            if check_password_hash(row.Encrypted_Password, new_pw) or (row.Prev_Password and check_password_hash(row.Prev_Password, new_pw)):
                return render_template("change_password.html", form=form, error="New password cannot be the same as the current or previous password.", nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400
            new_hash = generate_password_hash(new_pw)

            conn.execute(text("UPDATE USERS SET Encrypted_Password = :pw, Prev_Password = :prev_pw, Session_Version = Session_Version + 1 WHERE User_ID = :uid"), {"pw": new_hash, "prev_pw": row.Encrypted_Password, "uid": user_id})
            new_version = conn.execute(text("SELECT Session_Version FROM USERS WHERE User_ID = :uid"), {"uid": user_id}).fetchone().Session_Version
            session["session_version"] = new_version
    except Exception:
        return render_template("change_password.html", form=form, error="Database error changing password.", nav_pages=NAV_PAGES, logged_in=is_logged_in()), 500

    return render_template("page.html", page_title="Password Changed", nav_pages=NAV_PAGES, logged_in=is_logged_in())
@auth_bp.post("/reset")
def reset_submit():
    username = request.form.get('username', '').strip()
    form = LoginForm(meta={"csrf": False})
    
    if not username:
        return render_template("login.html", form=form, error="Please enter a username.", nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400

    try:
        with engine.connect() as conn:
            # Check if user exists
            user = conn.execute(text("""
                SELECT User_ID, User_Email, Username 
                FROM USERS 
                WHERE Username = :u
            """), {"u": username}).fetchone()
            
            if not user:
                return render_template("login.html", form=form, error="Username not found.", nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400

            # Generate temporary password
            temp_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
            
            # Update password
            pw_hash = generate_password_hash(temp_password)
            conn.execute(text("""
                UPDATE USERS 
                SET Encrypted_Password = :pw, Session_Version = Session_Version + 1 
                WHERE User_ID = :uid
            """), {"pw": pw_hash, "uid": user.User_ID})
            conn.commit()

            # Send email
            MAILGUN_DOMAIN = os.environ.get("MAILGUN_DOMAIN")
            MAILGUN_API = os.environ.get("MAILGUN_API")
            
            if not MAILGUN_DOMAIN or not MAILGUN_API:
                return render_template("login.html", form=form, error="Email service not configured.", nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400
            
            response = requests.post(
                f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages",
                auth=("api", MAILGUN_API),
                data={
                    "from": f"Driver Portal <noreply@{MAILGUN_DOMAIN}>",
                    "to": [user.User_Email],
                    "subject": "New Password",
                    "text": f"Hi {user.Username},\n\nYour new password is: {temp_password}\n\nLogin and change it to something memorable!\n\nThanks!"
                }
            )
            
            if response.status_code == 200:
                return render_template("login.html", form=form, error="New password sent! Check your email.", nav_pages=NAV_PAGES, logged_in=is_logged_in())
            else:
                return render_template("login.html", form=form, error="Failed to send email.", nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400
                
    except Exception:
        return render_template("login.html", form=form, error="Something went wrong. Try again.", nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400
@auth_bp.get("/register")
def register_page():
    form = RegisterForm(meta={"csrf": False})

    with engine.connect() as conn:
        sponsors = conn.execute(text("""
            SELECT Sponsor_ID, Sponsor_Name
            FROM SPONSORS
            ORDER BY Sponsor_Name
        """)).fetchall()

    form.sponsor_id.choices = [(r.Sponsor_ID, r.Sponsor_Name) for r in sponsors]

    return render_template(
        "register.html",
        form=form,
        error=None,
        sponsors=sponsors,
        nav_pages=NAV_PAGES,
        logged_in=is_logged_in()
    )


@auth_bp.get("/profile")
def profile_page():
    r = require_login_redirect()
    if r:
        return r

    user_id = session.get("user_id")
    with engine.connect() as conn:
        row = conn.execute(text("SELECT User_FName, User_LNAME, User_Email, User_Phone_Num FROM USERS WHERE User_ID = :uid"), {"uid": user_id}).fetchone()

    if not row:
        return render_template("page.html", page_title="User Not Found", nav_pages=NAV_PAGES, logged_in=is_logged_in()), 404

    form = ProfileForm(data={
        "first_name": row.User_FName,
        "last_name": row.User_LNAME,
        "email": row.User_Email,
        "phone": row.User_Phone_Num
    }, meta={"csrf": False})

    return render_template("profile.html", form=form, error=None, nav_pages=NAV_PAGES, logged_in=is_logged_in())


@auth_bp.post("/profile")
def profile_submit():
    r = require_login_redirect()
    if r:
        return r

    form = ProfileForm(request.form, meta={"csrf": False})
    if not form.validate():
        return render_template("profile.html", form=form, error=None, nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400

    user_id = session.get("user_id")
    first_name = form.first_name.data.strip()
    last_name = form.last_name.data.strip()
    email = form.email.data.strip()
    phone = normalize_phone(form.phone.data)

    try:
        with engine.begin() as conn:
            # Ensure email/phone uniqueness for other users
            existing = conn.execute(text("SELECT User_ID FROM USERS WHERE (User_Email = :e OR User_Phone_Num = :p) AND User_ID != :uid"), {"e": email, "p": phone, "uid": user_id}).fetchone()
            if existing:
                form.email.errors.append("Email or phone already in use by another account.")
                return render_template("profile.html", form=form, error=None, nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400

            conn.execute(text("UPDATE USERS SET User_FName = :fn, User_LNAME = :ln, User_Email = :em, User_Phone_Num = :ph WHERE User_ID = :uid"), {"fn": first_name, "ln": last_name, "em": email, "ph": phone, "uid": user_id})
    except Exception:
        return render_template("profile.html", form=form, error="Database error saving profile.", nav_pages=NAV_PAGES, logged_in=is_logged_in()), 500

    return render_template("page.html", page_title="Profile Updated", nav_pages=NAV_PAGES, logged_in=is_logged_in())

@auth_bp.post("/register")
def register_submit():
    form = RegisterForm(request.form, meta={"csrf": False})
    if not form.validate():
        # repopulate sponsor list on error
        with engine.connect() as conn:
            sponsors = conn.execute(text("SELECT Sponsor_ID, Sponsor_Name FROM SPONSORS ORDER BY Sponsor_Name")).fetchall()
        form.sponsor.choices = [(r.Sponsor_ID, r.Sponsor_Name) for r in sponsors]

        return render_template("register.html", form=form, error=None, sponsors=sponsors,
                               nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400

    username = form.username.data.strip()
    pw_hash = generate_password_hash(form.password.data)

    fname = form.first_name.data.strip()
    lname = form.last_name.data.strip()
    email = form.email.data.strip()
    phone = normalize_phone(form.phone.data)
    license_num = form.license_number.data.strip()
    sponsor_id = form.sponsor.data

    try:
        with engine.begin() as conn:
            sponsor = conn.execute(
                text("SELECT Sponsor_ID, Sponsor_Name FROM SPONSORS WHERE Sponsor_ID = :id"),
                {"id": sponsor_id}
            ).fetchone()

            if not sponsor:
                with engine.connect() as c2:
                    sponsors = c2.execute(text("SELECT Sponsor_ID, Sponsor_Name FROM SPONSORS ORDER BY Sponsor_Name")).fetchall()
                form.sponsor.choices = [(r.Sponsor_ID, r.Sponsor_Name) for r in sponsors]

                return render_template("register.html", form=form,
                                       error="Sponsor not found. Please choose one from the dropdown.",
                                       sponsors=sponsors,
                                       nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400

            # Check for duplicates across existing USERS and pending/other APPLICATIONS
            existing_user = conn.execute(
                text("SELECT User_ID FROM USERS WHERE Username = :u OR User_Email = :e OR User_Phone_Num = :p"),
                {"u": username, "e": email, "p": phone}
            ).fetchone()

            existing_app = conn.execute(
                text("SELECT Application_ID FROM APPLICATIONS WHERE App_Username = :u OR App_Email = :e OR App_Phone_Num = :p OR License_Num = :lic"),
                {"u": username, "e": email, "p": phone, "lic": license_num}
            ).fetchone()

            if existing_user or existing_app:
                with engine.connect() as c2:
                    sponsors = c2.execute(text("SELECT Sponsor_ID, Sponsor_Name FROM SPONSORS ORDER BY Sponsor_Name")).fetchall()
                form.sponsor.choices = [(r.Sponsor_ID, r.Sponsor_Name) for r in sponsors]

                return render_template("register.html", form=form,
                                       error="Username, email, phone, or license already exists.",
                                       sponsors=sponsors,
                                       nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400

            # Insert into APPLICATIONS (applicants are reviewed before creating USERS/DRIVERS)
            conn.execute(text("""
                INSERT INTO APPLICATIONS
                  (App_Username, Encrypted_Password, App_FName, App_LNAME, App_Email, App_Phone_Num, License_Num, App_Sponsor_ID, App_Status)
                VALUES
                  (:u, :pw, :fn, :ln, :em, :ph, :lic, :sid, 'Pending')
            """), {"u": username, "pw": pw_hash, "fn": fname, "ln": lname, "em": email, "ph": phone, "lic": license_num, "sid": sponsor.Sponsor_ID})

    except Exception:
        with engine.connect() as c2:
            sponsors = c2.execute(text("SELECT Sponsor_ID, Sponsor_Name FROM SPONSORS ORDER BY Sponsor_Name")).fetchall()
        form.sponsor.choices = [(r.Sponsor_ID, r.Sponsor_Name) for r in sponsors]

        return render_template("register.html", form=form,
                               error="Database error creating account.",
                               sponsors=sponsors,
                               nav_pages=NAV_PAGES, logged_in=is_logged_in()), 500

    # Applicants are not automatically logged in; show confirmation page
    return render_template("page.html", page_title="Application Submitted", nav_pages=NAV_PAGES, logged_in=is_logged_in())

@auth_bp.get("/admin/create")
def admin_create_page():
    r = require_role("Admin")
    if r:
        return r
    form = AdminCreateForm(request.form, meta={"csrf": False})
    return render_template("adminCreate.html", form=form, error=None, 
                            nav_pages=NAV_PAGES, logged_in=is_logged_in()) 

@auth_bp.post("/admin/create")
def admin_create_submit():
    r = require_role("Admin")
    if r:
        return r
    form = AdminCreateForm(request.form, meta={"csrf": False})
    if not form.validate():
        return render_template("adminCreate.html", form=form, error=None,
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
                return render_template("adminCreate.html", form=form,
                                       error="Username, email, or phone already exists",
                                       nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400
            conn.execute(text("""INSERT INTO USERS
                (Username, Encrypted_Password, User_FName, User_LNAME, User_Email, User_Phone_Num, User_Type)
                VALUES (:u, :pw, :fn, :ln, :em, :ph, 'Admin')
            """), {"u": username, "pw": pw_hash, "fn": fname, "ln": lname, "em": email, "ph": phone})
        
            new_id = conn.execute(text("SELECT LAST_INSERT_ID() AS id")).fetchone().id
        
            conn.execute(text("INSERT INTO ADMINS (User_ID, Security_Level) VALUES (:uid, 1)"),
                         {"uid": new_id})
        
    except Exception:
        return render_template("adminCreate.html", form=form, error="Database error creating admin",
                               nav_pages=NAV_PAGES, logged_in=is_logged_in()), 500
    return redirect(url_for("main.admin_home"))

@auth_bp.get("/sponsor/create")
def sponsor_create_page():
    r = require_role("Sponsor")
    if r:
        r2 = require_role("Admin")
        if r2:
            return r2
    sponsorList = []
    with engine.begin() as conn:
        sponsorList = conn.execute(text("SELECT Sponsor_ID, Sponsor_Name FROM SPONSORS")).fetchall()

    form = SponsorCreateForm(request.form, meta={"csrf": False})
    return render_template("sponsorCreate.html", form=form, sponsorList=sponsorList,error=None, 
                            nav_pages=NAV_PAGES, logged_in=is_logged_in())

@auth_bp.post("/sponsor/create")
def sponsor_create_submit():
    r = require_role("Sponsor")
    if r:
        r2 = require_role("Admin")
        if r2:
            return r2
        
    form = SponsorCreateForm(request.form, meta={"csrf": False})
    if not form.validate():
        sponsorList = []
        with engine.begin() as conn:
            sponsorList = conn.execute(text("SELECT Sponsor_ID, Sponsor_Name FROM SPONSORS")).fetchall()

        return render_template("sponsorCreate.html", form=form, sponsorList=sponsorList, error=None,
                               nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400
    username = form.username.data.strip()
    pw_hash = generate_password_hash(form.password.data)
    fname = form.first_name.data.strip()
    lname = form.last_name.data.strip()
    email = form.email.data.strip()
    phone = normalize_phone(form.phone.data)
    if session.get("user_type") == "Sponsor":
        sponsor_id = session["sponsor_id"]
    else:
        sponsor_id = request.form.get("sponsor_id")

    try:
        with engine.begin() as conn:
            existing = conn.execute( text("SELECT User_ID FROM USERS WHERE Username = :u OR User_Email = :e OR User_Phone_Num = :p"),
                {"u": username, "e": email, "p": phone}).fetchone()
            if existing:
                sponsorList = []
                with engine.begin() as c2:
                    sponsorList = c2.execute(text("SELECT Sponsor_ID, Sponsor_Name FROM SPONSORS")).fetchall()

                return render_template("sponsorCreate.html", form=form, sponsorList=sponsorList,
                                       error="Username, email, or phone already exists",
                                       nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400
            conn.execute(text("""INSERT INTO USERS
                (Username, Encrypted_Password, User_FName, User_LNAME, User_Email, User_Phone_Num, User_Type)
                VALUES (:u, :pw, :fn, :ln, :em, :ph, 'Sponsor')
            """), {"u": username, "pw": pw_hash, "fn": fname, "ln": lname, "em": email, "ph": phone})
        
            new_id = conn.execute(text("SELECT LAST_INSERT_ID() AS id")).fetchone().id
        
            conn.execute(text("INSERT INTO SPONSOR_USER (User_ID, Sponsor_ID) VALUES (:uid, :sid)"),
                         {"uid": new_id, "sid": sponsor_id})
        
    except Exception:
        sponsorList = []
        with engine.begin() as c2:
                sponsorList = c2.execute(text("SELECT Sponsor_ID, Sponsor_Name FROM SPONSORS")).fetchall()
                
        return render_template("sponsorCreate.html", form=form, sponsorList=sponsorList, error="Database error creating sponsor user",
                               nav_pages=NAV_PAGES, logged_in=is_logged_in()), 500
    if session.get("user_type") == "Sponsor":
        return redirect(url_for("main.sponsor_home"))
    else:
        return redirect(url_for("main.admin_home"))

@auth_bp.get("/logout")
def logout():
    user_id = session.get("user_id")
    if user_id:
        with engine.begin() as conn:
            conn.execute(text("""
                            UPDATE USERS SET Session_Version = Session_Version + 1
                            WHERE User_ID = :uid"""), {"uid": user_id})
    session.clear()
    return redirect(url_for("auth.login_page"))
