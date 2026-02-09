from flask import Flask, render_template, request, redirect, url_for, session
from wtforms import Form, StringField, PasswordField, SelectField, validators
from email_validator import validate_email, EmailNotValidError
import re

app = Flask(__name__)
app.secret_key = "dev-secret-change-me"  # fine for sprint 1 demo

# -------------------------
# Local in-memory "database"
# -------------------------
# username -> user dict
USERS = {
    # demo user so login works immediately
    "demo": {
        "username": "demo",
        "password": "Password1",
        "first_name": "Demo",
        "last_name": "User",
        "email": "demo@example.com",
        "phone": "8645551234",
        "license_number": "D1234567",
        "sponsor": "Test Sponsor",
        "role": "driver",
    }
}


NAV_PAGES = [
    ("about", "About"),
    ("page", "Blank Page 1", "page1"),
    ("page", "Blank Page 2", "page2"),
    ("page", "Blank Page 3", "page3"),
]


# -------------------------
# Validation helpers
# -------------------------
def is_valid_email(value: str) -> bool:
    try:
        validate_email(value)
        return True
    except EmailNotValidError:
        return False


def normalize_phone(value: str) -> str:
    # strip non-digits, keep digits only
    return re.sub(r"\D", "", value or "")


# -------------------------
# WTForms
# -------------------------
class LoginForm(Form):
    username = StringField("Username", [
        validators.DataRequired(message="Username is required.")
    ])
    password = PasswordField("Password", [
        validators.DataRequired(message="Password is required.")
    ])


class RegisterForm(Form):
    username = StringField("Username", [
        validators.DataRequired(message="Username is required."),
        validators.Length(min=3, max=30, message="Username must be 3–30 characters.")
    ])

    password = PasswordField("Password", [
        validators.DataRequired(message="Password is required."),
        validators.Length(min=8, message="Password must be at least 8 characters.")
    ])

    first_name = StringField("First Name", [
        validators.DataRequired(message="First name is required.")
    ])

    last_name = StringField("Last Name", [
        validators.DataRequired(message="Last name is required.")
    ])

    email = StringField("Email", [
        validators.DataRequired(message="Email is required.")
    ])

    phone = StringField("Phone Number", [
        validators.DataRequired(message="Phone number is required.")
    ])

    license_number = StringField("License Number", [
        validators.DataRequired(message="License number is required.")
    ])

    sponsor = StringField("Sponsor", [
        validators.DataRequired(message="Sponsor is required.")
    ])

    def validate(self):
        ok = super().validate()
        if not ok:
            return False

        # Email format check
        if not is_valid_email(self.email.data):
            self.email.errors.append("Enter a valid email address.")
            return False

        # Phone check: digits only after normalization, 10–15 digits
        digits = normalize_phone(self.phone.data)
        if len(digits) < 10 or len(digits) > 15:
            self.phone.errors.append("Enter a valid phone number (10–15 digits).")
            return False

        return True


# -------------------------
# Auth helpers
# -------------------------
def is_logged_in() -> bool:
    return session.get("username") is not None


def require_login_redirect():
    if not is_logged_in():
        return redirect(url_for("login_page"))
    return None


# -------------------------
# Routes
# -------------------------
@app.get("/")
def login_page():
    form = LoginForm(meta={"csrf": False})
    return render_template("login.html", form=form, error=None, nav_pages=NAV_PAGES, logged_in=is_logged_in())


@app.post("/login")
def login_submit():
    form = LoginForm(request.form, meta={"csrf": False})
    if not form.validate():
        return render_template("login.html", form=form, error=None, nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400

    username = form.username.data.strip()
    password = form.password.data

    user = USERS.get(username)
    if not user or user["password"] != password:
        return render_template("login.html", form=form, error="Invalid username or password.", nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400

    session["username"] = user["username"]
    session["role"] = user["role"]
    return redirect(url_for("about_page"))


@app.get("/register")
def register_page():
    form = RegisterForm(meta={"csrf": False})
    return render_template("register.html", form=form, error=None, nav_pages=NAV_PAGES, logged_in=is_logged_in())


@app.post("/register")
def register_submit():
    form = RegisterForm(request.form, meta={"csrf": False})
    if not form.validate():
        return render_template("register.html", form=form, error=None, nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400

    username = form.username.data.strip()

    if username in USERS:
        return render_template("register.html", form=form, error="That username is already taken.", nav_pages=NAV_PAGES, logged_in=is_logged_in()), 400

    phone_digits = normalize_phone(form.phone.data)

    USERS[username] = {
        "username": username,
        "password": form.password.data,
        "first_name": form.first_name.data.strip(),
        "last_name": form.last_name.data.strip(),
        "email": form.email.data.strip(),
        "phone": phone_digits,
        "license_number": form.license_number.data.strip(),
        "sponsor": form.sponsor.data.strip(),
        "role": "driver",
    }

    # Auto-login after register
    session["username"] = username
    session["role"] = "driver"
    return redirect(url_for("about_page"))


@app.get("/about")
def about_page():
    r = require_login_redirect()
    if r:
        return r

    user = USERS.get(session["username"])
    return render_template("about.html",
                           user=user,
                           sprint_name="Sprint 1",
                           sprint_goal="Boilerplate login/register + navigation pages",
                           nav_pages=NAV_PAGES,
                           logged_in=is_logged_in())


@app.get("/page/<name>")
def blank_page(name):
    r = require_login_redirect()
    if r:
        return r

    # simple allow-list so you can’t hit arbitrary pages
    allowed = {"page1", "page2", "page3"}
    if name not in allowed:
        return "Page not found", 404

    return render_template("page.html",
                           page_title=f"Blank Test Page: {name}",
                           nav_pages=NAV_PAGES,
                           logged_in=is_logged_in())


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# Elastic Beanstalk-friendly callable name:
application = app

if __name__ == "__main__":
    app.run(debug=True)