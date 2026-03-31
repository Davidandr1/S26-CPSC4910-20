from sqlalchemy import text

from app.db import engine


class ApplicationService:
    @staticmethod
    def list_applications(user_type, sponsor_id, start_date, end_date, sponsor_filter):
        filters = []
        params = {}

        if start_date:
            filters.append("App_Time >= :start_date")
            params["start_date"] = start_date

        if end_date:
            filters.append("App_Time <= :end_date")
            params["end_date"] = end_date

        if user_type == "Admin" and sponsor_filter:
            filters.append("App_Sponsor_ID = :sponsor_id")
            params["sponsor_id"] = sponsor_filter

        filter_statement = " AND ".join(filters) if filters else "1=1"

        with engine.connect() as conn:
            if user_type == "Sponsor":
                return conn.execute(
                    text(
                        f"""
                        SELECT Application_ID, App_Status, App_FName, App_LNAME
                        FROM APPLICATIONS
                        WHERE App_Sponsor_ID = :sid AND {filter_statement}
                        ORDER BY App_Time
                        """
                    ),
                    params | {"sid": sponsor_id},
                ).fetchall()

            return conn.execute(
                text(
                    f"""
                    SELECT Application_ID, App_Status, App_FName, App_LNAME
                    FROM APPLICATIONS
                    WHERE {filter_statement}
                    ORDER BY App_Time
                    """
                ),
                params,
            ).fetchall()

    @staticmethod
    def get_application_detail(app_id):
        with engine.connect() as conn:
            return conn.execute(
                text(
                    """
                    SELECT Application_ID, App_Sponsor_ID, App_Username, App_Status, App_FName,
                           App_LNAME, App_Email, App_Phone_Num, License_Num, App_Time, Denial_Reason
                    FROM APPLICATIONS
                    WHERE Application_ID = :aid
                    """
                ),
                {"aid": app_id},
            ).fetchone()

    @staticmethod
    def evaluate_application(app_id, decision, reason):
        with engine.begin() as conn:
            app = conn.execute(
                text("SELECT App_Sponsor_ID FROM APPLICATIONS WHERE Application_ID = :aid"),
                {"aid": app_id},
            ).fetchone()
            if not app:
                return None

            conn.execute(
                text(
                    """
                    UPDATE APPLICATIONS
                    SET App_Status = :status, Denial_Reason = :reason
                    WHERE Application_ID = :aid
                    """
                ),
                {"status": decision, "reason": reason if decision == "Denied" else None, "aid": app_id},
            )
            if decision == "Approved":
                conn.execute(text("DELETE FROM APPLICATIONS WHERE Application_ID = :aid"), {"aid": app_id})
            return app
