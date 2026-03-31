from sqlalchemy import text

from app.db import engine


class AdminService:
    @staticmethod
    def get_sponsors_with_driver_counts():
        with engine.connect() as conn:
            try:
                return conn.execute(
                    text(
                        """
                        SELECT s.Sponsor_ID, s.Sponsor_Name, s.Sponsor_Email, s.Sponsor_Phone,
                               s.Sponsor_Address, s.Sponsor_PointConversion, s.Sponsor_MaxPoints, s.Sponsor_Creation,
                               COALESCE(COUNT(d.User_ID), 0) AS driver_count
                        FROM SPONSORS s
                        LEFT JOIN DRIVERS d ON d.Sponsor_ID = s.Sponsor_ID
                        GROUP BY s.Sponsor_ID, s.Sponsor_Name, s.Sponsor_Email, s.Sponsor_Phone,
                                 s.Sponsor_Address, s.Sponsor_PointConversion, s.Sponsor_MaxPoints, s.Sponsor_Creation
                        ORDER BY s.Sponsor_Name
                        """
                    )
                ).fetchall()
            except Exception:
                return conn.execute(
                    text(
                        """
                        SELECT s.Sponsor_ID, s.Sponsor_Name, s.Sponsor_Email, s.Sponsor_Phone,
                               s.Sponsor_Address, s.Sponsor_PointConversion, s.Sponsor_MaxPoints, s.Sponsor_Creation,
                               COALESCE(COUNT(su.User_ID), 0) AS driver_count
                        FROM SPONSORS s
                        LEFT JOIN SPONSOR_USER su ON su.Sponsor_ID = s.Sponsor_ID
                        GROUP BY s.Sponsor_ID, s.Sponsor_Name, s.Sponsor_Email, s.Sponsor_Phone,
                                 s.Sponsor_Address, s.Sponsor_PointConversion, s.Sponsor_MaxPoints, s.Sponsor_Creation
                        ORDER BY s.Sponsor_Name
                        """
                    )
                ).fetchall()

    @staticmethod
    def get_users(sort):
        allowed = {
            "username": "Username",
            "type": "User_Type",
            "email": "User_Email",
            "created": "User_Creation",
            "points": "d.User_Points",
        }
        order_by = allowed.get(sort, "Username")

        with engine.connect() as conn:
            try:
                users = conn.execute(
                    text(
                        f"""
                        SELECT u.User_ID, u.Username, u.User_FName, u.User_LNAME, u.User_Email,
                               u.User_Phone_Num, u.User_Type, u.User_Creation, d.User_Points
                        FROM USERS u
                        LEFT JOIN DRIVERS d ON d.User_ID = u.User_ID
                        ORDER BY {order_by}
                        """
                    )
                ).fetchall()
            except Exception:
                # Fallback for deployments whose DRIVERS table does not contain User_Points.
                users = conn.execute(
                    text(
                        """
                        SELECT u.User_ID, u.Username, u.User_FName, u.User_LNAME, u.User_Email,
                               u.User_Phone_Num, u.User_Type, u.User_Creation, NULL AS User_Points
                        FROM USERS u
                        ORDER BY Username
                        """
                    )
                ).fetchall()
        return users, sort
