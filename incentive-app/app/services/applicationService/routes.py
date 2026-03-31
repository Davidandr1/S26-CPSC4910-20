from flask import redirect, render_template, request, session, url_for

from app.services.applicationService.applicationService import ApplicationService
from app.services.web_common import NAV_PAGES, is_logged_in, main_bp, require_sponsor_or_admin


@main_bp.get("/applications")
def applications_list():
    r = require_sponsor_or_admin()
    if r:
        return r

    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    sponsor_filter = request.args.get("sponsor_id")

    apps = ApplicationService.list_applications(
        session["user_type"],
        session.get("sponsor_id"),
        start_date,
        end_date,
        sponsor_filter,
    )

    return render_template(
        "applications_list.html",
        apps=apps,
        nav_pages=NAV_PAGES,
        logged_in=is_logged_in(),
    )


@main_bp.get("/applications/<int:app_id>")
def application_details(app_id):
    r = require_sponsor_or_admin()
    if r:
        return r

    app = ApplicationService.get_application_detail(app_id)
    if not app:
        return "Application not found", 404

    if session["user_type"] == "Sponsor" and int(app.App_Sponsor_ID) != int(session["sponsor_id"]):
        return "Forbidden", 403

    return render_template(
        "application_detail.html",
        app=app,
        nav_pages=NAV_PAGES,
        logged_in=is_logged_in(),
    )


@main_bp.post("/applications/<int:app_id>/evaluate")
def evaluate_applications(app_id):
    r = require_sponsor_or_admin()
    if r:
        return r

    decision = request.form.get("decision")
    reason = request.form.get("reason")

    current_app = ApplicationService.get_application_detail(app_id)
    if not current_app:
        return "Application not found", 404

    if session["user_type"] == "Sponsor" and int(current_app.App_Sponsor_ID) != int(session["sponsor_id"]):
        return "Forbidden", 403

    if decision == "Denied" and not reason:
        return render_template(
            "application_detail.html",
            app=current_app,
            nav_pages=NAV_PAGES,
            logged_in=is_logged_in(),
            error="Reason for denial is required when denying an application.",
        )

    ApplicationService.evaluate_application(app_id, decision, reason)
    return redirect(url_for("main.applications_list"))
