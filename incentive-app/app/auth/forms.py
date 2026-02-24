import re
from wtforms import Form, StringField, PasswordField, validators
from email_validator import validate_email, EmailNotValidError

def is_valid_email(value: str) -> bool:
    try:
        validate_email(value)
        return True
    except EmailNotValidError:
        return False

def normalize_phone(value: str) -> str:
    return re.sub(r"\D", "", value or "")

class LoginForm(Form):
    username = StringField("Username", [
        validators.DataRequired(message="Username is required.")
    ])
    password = PasswordField("Password", [
        validators.DataRequired(message="Password is required.")
    ])

class RegisterForm(Form):
    # Drivers only self-register
    username = StringField("Username", [
        validators.DataRequired(message="Username is required."),
        validators.Length(min=3, max=100, message="Username must be 3–100 characters.")
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

        if not is_valid_email(self.email.data):
            self.email.errors.append("Enter a valid email address.")
            return False

        digits = normalize_phone(self.phone.data)
        if len(digits) < 10 or len(digits) > 15:
            self.phone.errors.append("Enter a valid phone number (10–15 digits).")
            return False

        return True


class ChangePasswordForm(Form):
    current_password = PasswordField("Current Password", [
        validators.DataRequired(message="Current password is required.")
    ])

    new_password = PasswordField("New Password", [
        validators.DataRequired(message="New password is required."),
        validators.Length(min=8, message="New password must be at least 8 characters.")
    ])

    confirm_password = PasswordField("Confirm New Password", [
        validators.DataRequired(message="Please confirm the new password."),
        validators.EqualTo('new_password', message='Passwords must match.')
    ])


class AdminCreateForm(Form):
    username = StringField("Username", [
        validators.DataRequired(message="Username is required."),
        validators.Length(min=3, max=100, message="Username must be 3–100 characters.")
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

class SponsorCreateForm(Form):
    username = StringField("Username", [
        validators.DataRequired(message="Username is required."),
        validators.Length(min=3, max=100, message="Username must be 3–100 characters.")
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