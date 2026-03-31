from sqlalchemy import text

from app.db import engine


class DriverService:
    @staticmethod
    def get_home_data(driver_id):
        with engine.connect() as conn:
            transactions = conn.execute(
                text(
                    """
                    SELECT Points_Changed, Reason, Transaction_Time
                    FROM POINT_TRANSACTIONS
                    WHERE Driver_ID = :uid
                    """
                ),
                {"uid": driver_id},
            ).fetchall()
            points_row = conn.execute(
                text("SELECT User_Points FROM DRIVERS WHERE User_ID = :uid"),
                {"uid": driver_id},
            ).fetchone()
        points = points_row.User_Points if points_row else 0
        return transactions, points

    @staticmethod
    def get_points(driver_id):
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT User_Points FROM DRIVERS WHERE User_ID = :uid"),
                {"uid": driver_id},
            ).fetchone()
        return row.User_Points if row else 0
