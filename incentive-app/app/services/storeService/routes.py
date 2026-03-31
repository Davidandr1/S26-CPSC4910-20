from datetime import datetime

from flask import flash, redirect, render_template, request, session, url_for
from sqlalchemy import text

from app.db import engine
from app.services.web_common import NAV_PAGES, fetch_current_user, is_logged_in, main_bp, require_role


@main_bp.get("/store")
def storefront():
    r = require_role("Driver")
    if r:
        return r

    user = fetch_current_user()
    uid = session["user_id"]

    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()
    sort_by = request.args.get("sort_by", "asc")

    try:
        min_points = int(request.args.get("min_price", 0))
    except Exception:
        min_points = 0

    try:
        max_points = int(request.args.get("max_price", 999999))
    except Exception:
        max_points = 999999

    if min_points > max_points:
        max_points = min_points

    filters = ["i.Is_Available = TRUE"]
    params = {"uid": uid}

    if search:
        filters.append("i.Item_Name LIKE :search")
        params["search"] = f"%{search}%"

    if category:
        filters.append("i.Prod_Category = :category")
        params["category"] = category

    filters.append("i.Point_Value >= :min_points")
    filters.append("i.Point_Value <= :max_points")
    params["min_points"] = min_points
    params["max_points"] = max_points

    order_clause = "i.Point_Value ASC" if sort_by == "asc" else "i.Point_Value DESC"
    where_clause = " AND ".join(filters)

    with engine.connect() as conn:
        sponsor_row = conn.execute(
            text("SELECT Sponsor_ID FROM DRIVERS WHERE User_ID = :uid"),
            {"uid": uid},
        ).fetchone()

        if not sponsor_row:
            return "Sponsor not found", 400

        sponsor_id = sponsor_row.Sponsor_ID
        params["sid"] = sponsor_id

        products = conn.execute(
            text(
                f"""
                SELECT
                    i.Item_ID,
                    i.Item_Name,
                    i.Prod_Description,
                    i.Prod_Quantity,
                    i.Is_Available,
                    i.Product_Image_URL,
                    i.Point_Value,
                    i.Prod_Category
                FROM INVENTORY i
                WHERE i.Sponsor_ID = :sid
                  AND {where_clause}
                ORDER BY {order_clause}
                """
            ),
            params,
        ).fetchall()

        categories = conn.execute(
            text(
                """
                SELECT DISTINCT Prod_Category
                FROM INVENTORY
                WHERE Sponsor_ID = :sid
                  AND Prod_Category IS NOT NULL
                  AND Prod_Category != ''
                """
            ),
            {"sid": sponsor_id},
        ).fetchall()

        max_point_cost_row = conn.execute(
            text(
                """
                SELECT MAX(Point_Value) AS max_points
                FROM INVENTORY
                WHERE Sponsor_ID = :sid AND Is_Available = TRUE
                """
            ),
            {"sid": sponsor_id},
        ).fetchone()

        max_point_cost = (
            max_point_cost_row.max_points if max_point_cost_row and max_point_cost_row.max_points else 1000
        )

        points_row = conn.execute(
            text("SELECT User_Points FROM DRIVERS WHERE User_ID = :uid"),
            {"uid": uid},
        ).fetchone()
        user_points = points_row.User_Points if points_row else 0

        cart_row = conn.execute(
            text(
                """
                SELECT COALESCE(SUM(Quantity), 0) AS cnt
                FROM CART_ITEMS
                WHERE Driver_ID = :uid
                """
            ),
            {"uid": uid},
        ).fetchone()
        cart_count = cart_row.cnt if cart_row else 0

    return render_template(
        "storefront.html",
        nav_pages=NAV_PAGES,
        logged_in=is_logged_in(),
        user=user,
        products=products,
        user_points=user_points,
        categories=categories,
        max_point_cost=max_point_cost,
        cart_count=cart_count,
    )


@main_bp.get("/cart")
def cart_page():
    r = require_role("Driver")
    if r:
        return r

    user = fetch_current_user()
    with engine.connect() as conn:
        cart_items = conn.execute(
            text(
                """
                SELECT ci.Item_ID as id, i.Item_Name as name, i.Prod_Description as description,
                       ROUND(i.Prod_UnitPrice / s.Sponsor_PointConversion) AS point_cost,
                       ci.Quantity as quantity, i.Prod_Quantity as stock, '' as image_url
                FROM CART_ITEMS ci
                JOIN INVENTORY i ON ci.Item_ID = i.Item_ID
                JOIN SPONSORS s ON i.Sponsor_ID = s.Sponsor_ID
                WHERE ci.Driver_ID = :uid
                """
            ),
            {"uid": session["user_id"]},
        ).fetchall()
        total_cost = sum(i.point_cost * i.quantity for i in cart_items)

    return render_template(
        "cart.html",
        nav_pages=NAV_PAGES,
        logged_in=is_logged_in(),
        user=user,
        cart_items=cart_items,
        total_cost=total_cost,
    )


@main_bp.post("/cart/add/<int:item_id>")
def cart_add(item_id):
    r = require_role("Driver")
    if r:
        return r

    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT Quantity FROM CART_ITEMS WHERE Driver_ID=:uid AND Item_ID=:iid"),
            {"uid": session["user_id"], "iid": item_id},
        ).fetchone()

        if existing:
            conn.execute(
                text("UPDATE CART_ITEMS SET Quantity=Quantity+1 WHERE Driver_ID=:uid AND Item_ID=:iid"),
                {"uid": session["user_id"], "iid": item_id},
            )
        else:
            conn.execute(
                text("INSERT INTO CART_ITEMS (Driver_ID, Item_ID, Quantity) VALUES (:uid, :iid, 1)"),
                {"uid": session["user_id"], "iid": item_id},
            )

    return redirect(url_for("main.storefront"))


@main_bp.post("/cart/update/<int:item_id>")
def cart_update(item_id):
    r = require_role("Driver")
    if r:
        return r

    quantity = int(request.form.get("quantity", 1))
    with engine.begin() as conn:
        if quantity <= 0:
            conn.execute(
                text("DELETE FROM CART_ITEMS WHERE Driver_ID=:uid AND Item_ID=:iid"),
                {"uid": session["user_id"], "iid": item_id},
            )
        else:
            conn.execute(
                text("UPDATE CART_ITEMS SET Quantity=:qty WHERE Driver_ID=:uid AND Item_ID=:iid"),
                {"qty": quantity, "uid": session["user_id"], "iid": item_id},
            )

    return redirect(url_for("main.cart_page"))


@main_bp.post("/cart/remove/<int:item_id>")
def cart_remove(item_id):
    r = require_role("Driver")
    if r:
        return r

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM CART_ITEMS WHERE Driver_ID=:uid AND Item_ID=:iid"),
            {"uid": session["user_id"], "iid": item_id},
        )

    return redirect(url_for("main.cart_page"))


@main_bp.post("/cart/checkout")
def cart_checkout():
    r = require_role("Driver")
    if r:
        return r

    uid = session["user_id"]
    try:
        with engine.begin() as conn:
            cart_items = conn.execute(
                text(
                    """
                    SELECT ci.Item_ID, i.Item_Name, i.Prod_SKU,
                           ROUND(i.Prod_UnitPrice / s.Sponsor_PointConversion) AS point_cost,
                           ci.Quantity, d.Sponsor_ID
                    FROM CART_ITEMS ci
                    JOIN INVENTORY i ON ci.Item_ID = i.Item_ID
                    JOIN SPONSORS s ON i.Sponsor_ID = s.Sponsor_ID
                    JOIN DRIVERS d ON d.User_ID = ci.Driver_ID
                    WHERE ci.Driver_ID = :uid
                    """
                ),
                {"uid": uid},
            ).fetchall()

            if not cart_items:
                flash("Your cart is empty.", "error")
                return redirect(url_for("main.cart_page"))

            total_cost = sum(i.point_cost * i.Quantity for i in cart_items)
            sponsor_id = cart_items[0].Sponsor_ID

            if any(i.Sponsor_ID != sponsor_id for i in cart_items):
                flash("All items in the cart must be from the same sponsor.", "error")
                return render_template(
                    "cart.html",
                    nav_pages=NAV_PAGES,
                    logged_in=is_logged_in(),
                    error="All items in the cart must be from the same sponsor.",
                    cart_items=cart_items,
                    total_cost=total_cost,
                )

            driver = conn.execute(
                text("SELECT User_Points FROM DRIVERS WHERE User_ID = :uid"),
                {"uid": uid},
            ).fetchone()

            if not driver:
                flash("Driver not found.", "error")
                return render_template(
                    "cart.html",
                    nav_pages=NAV_PAGES,
                    logged_in=is_logged_in(),
                    error="Driver not found.",
                    cart_items=cart_items,
                    total_cost=total_cost,
                )

            if driver.User_Points < total_cost:
                flash("You do not have enough points to complete this purchase.", "error")
                return render_template(
                    "cart.html",
                    nav_pages=NAV_PAGES,
                    logged_in=is_logged_in(),
                    error="You do not have enough points to complete this purchase.",
                    cart_items=cart_items,
                    total_cost=total_cost,
                )

            for item in cart_items:
                if item.Quantity > item.stock:
                    flash(f"Not enough stock for {item.Item_Name}. Available: {item.stock}", "error")
                    return render_template(
                        "cart.html",
                        nav_pages=NAV_PAGES,
                        logged_in=is_logged_in(),
                        error=f"Not enough stock for {item.Item_Name}. Available: {item.stock}",
                        cart_items=cart_items,
                        total_cost=total_cost,
                    )

            result = conn.execute(
                text(
                    """
                    INSERT INTO ORDERS (Driver_ID, Sponsor_ID, Order_Status, Total_Points)
                    VALUES (:uid, :sid, 'Pending', :total)
                    """
                ),
                {"uid": uid, "sid": sponsor_id, "total": total_cost},
            )
            order_id = result.lastrowid

            for item in cart_items:
                stock_check = conn.execute(
                    text("SELECT Prod_Quantity FROM INVENTORY WHERE Item_ID = :iid"),
                    {"iid": item.Item_ID},
                ).fetchone()

                if not stock_check or stock_check.Prod_Quantity < item.Quantity:
                    flash(f"Sorry, {item.Item_Name} is out of stock.")
                    return redirect(url_for("main.cart_page"))

                conn.execute(
                    text(
                        """
                        INSERT INTO LINE_ITEMS (Item_ID, Order_ID, Prod_SKU, Item_Name, Price_Points, Line_Quantity)
                        VALUES (:iid, :oid, :sku, :name, :pts, :qty)
                        """
                    ),
                    {
                        "iid": item.Item_ID,
                        "oid": order_id,
                        "sku": item.Prod_SKU,
                        "name": item.Item_Name,
                        "pts": item.point_cost,
                        "qty": item.Quantity,
                    },
                )

            conn.execute(
                text("UPDATE DRIVERS SET User_Points = User_Points - :total WHERE User_ID = :uid"),
                {"total": total_cost, "uid": uid},
            )

            conn.execute(
                text(
                    """
                    INSERT INTO POINT_TRANSACTIONS (Driver_ID, Actor_User_ID, Points_Changed, Reason, Transaction_Time)
                    VALUES (:uid, :sid, :pts, 'Order placed', :time)
                    """
                ),
                {"uid": uid, "sid": sponsor_id, "pts": -total_cost, "time": datetime.now()},
            )

            conn.execute(text("DELETE FROM CART_ITEMS WHERE Driver_ID = :uid"), {"uid": uid})

        flash("Your order has been placed successfully!", "success")
        return redirect(url_for("main.driver_home"))
    except Exception as e:
        flash(f"An error occurred while processing your order: {str(e)}", "error")
        return redirect(url_for("main.cart_page"))
