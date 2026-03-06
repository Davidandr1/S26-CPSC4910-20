from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from sqlalchemy import text
from app.db import engine

main_bp = Blueprint("main", __name__)

NAV_PAGES = [
    ("about", "About"),
    ("store", "Store"),
    ("applications_list", "Applications"),
    ("admin_create_page", "Create New Admin"),
    ("sponsor_create_page", "Create New Sponsor User"),
    ("sponsor_products", "My Products")
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

def fetch_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None

    with engine.connect() as conn:
        u = conn.execute(text("""
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
        """), {"id": user_id}).fetchone()

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
            row = conn.execute(text("""
                SELECT s.Sponsor_Name, d.User_Points
                FROM DRIVERS d
                JOIN SPONSORS s ON s.Sponsor_ID = d.Sponsor_ID
                WHERE d.User_ID = :id
            """), {"id": user_id}).fetchone()
            sponsor_name = row.Sponsor_Name if row else None
            user["points"] = row.User_Points if row and hasattr(row, 'User_Points') else 0

        elif u.User_Type == "Sponsor":
            row = conn.execute(text("""
                SELECT s.Sponsor_Name
                FROM SPONSOR_USER su
                JOIN SPONSORS s ON s.Sponsor_ID = su.Sponsor_ID
                WHERE su.User_ID = :id
            """), {"id": user_id}).fetchone()
            sponsor_name = row.Sponsor_Name if row else None

        user["sponsor"] = sponsor_name or "N/A"
        return user


@main_bp.get("/home")
def home_redirect():
    r = require_login_redirect()
    if r:
        return r

    t = session.get("user_type")
    if t == "Admin":
        return redirect(url_for("main.admin_home"))
    if t == "Sponsor":
        return redirect(url_for("main.sponsor_home"))
    return redirect(url_for("main.driver_home"))


@main_bp.get("/about")
def about_page():
    r = require_login_redirect()
    if r:
        return r

    user = fetch_current_user()
    try:
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) AS count FROM USERS")).fetchone()
            user_count = count.count
            db_status = "Connected"
    except Exception as e:
        user_count = "N/A"
        db_status = f"Error: {str(e)}"
    return render_template(
        "about.html",
        user=user,
        nav_pages=NAV_PAGES,
        logged_in=is_logged_in(),
        db_status=db_status,
        count=count
    )


@main_bp.get("/driver/home")
def driver_home():
    r = require_role("Driver")
    if r:
        return r

    driver_id = session.get("user_id")
    with engine.connect() as conn:
        transactions = conn.execute(text("""
            SELECT Points_Changed, Reason, Transaction_Time FROM POINT_TRANSACTIONS WHERE Driver_ID = :uid
        """), {"uid": driver_id}).fetchall()
        points = conn.execute(text("""SELECT User_Points FROM DRIVERS WHERE User_ID = :uid"""), {"uid": driver_id}).fetchone().User_Points

    return render_template("driverHome.html", page_title="Driver Home", nav_pages=NAV_PAGES, logged_in=is_logged_in(), transactions=transactions, points=points)


@main_bp.get("/driver/points")
def driver_points_api():
    r = require_role("Driver")
    if r:
        return r

    driver_id = session.get("user_id")
    with engine.connect() as conn:
        row = conn.execute(text("SELECT User_Points FROM DRIVERS WHERE User_ID = :uid"), {"uid": driver_id}).fetchone()

    points = row.User_Points if row else 0
    return jsonify({"points": points})


@main_bp.get("/sponsor/home")
def sponsor_home():
    r = require_role("Sponsor")
    if r:
        return r
    
    sponsor_id = session.get("sponsor_id")
    if not sponsor_id:
        return "Sponsor ID not found in session", 400
    
    with engine.connect() as conn:
        sponsor = conn.execute(text("""
            SELECT Sponsor_Name FROM SPONSORS WHERE Sponsor_ID = :sid
        """), {"sid": sponsor_id}).fetchone()
    drivers = []
    with engine.connect() as conn:
        drivers = conn.execute(text("""
            SELECT d.User_ID, u.User_FName, u.User_LName, u.User_Email, u.User_Phone_Num
            FROM DRIVERS d
            JOIN USERS u ON d.User_ID = u.User_ID
            WHERE d.Sponsor_ID = :sid AND d.Is_Active = TRUE
        """), {"sid": sponsor_id}).fetchall()

    return render_template("sponsorHome.html", nav_pages=NAV_PAGES, logged_in=is_logged_in(), drivers=drivers, sponsor=sponsor)

@main_bp.get("/sponsor/products")
def sponsor_products():
    r = require_role("Sponsor")
    if r:
        return r
    
    sponsor_id = session.get("sponsor_id")
    if not sponsor_id:
        return "Sponsor ID not found in session", 400
    
    with engine.connect() as conn:
        products = conn.execute(text("""
            SELECT Item_ID, Item_Name, Prod_Description, Prod_Quantity, Prod_UnitPrice, Is_Available
            FROM INVENTORY
            WHERE Sponsor_ID = :sid
        """), {"sid": sponsor_id}).fetchall()

    return render_template("sponsorProducts.html", nav_pages=NAV_PAGES, logged_in=is_logged_in(), products=products)

@main_bp.get("/sponsor/products/<int:item_id>")
def sponsor_product_detail(item_id):
    r = require_role("Sponsor")
    if r:
        return r
    
    sponsor_id = session.get("sponsor_id")
    if not sponsor_id:
        return "Sponsor ID not found in session", 400
    
    with engine.connect() as conn:
        product = conn.execute(text("""
            SELECT Item_ID, Prod_SKU, Item_Name, Prod_Description, Prod_Quantity, Prod_UnitPrice, Is_Available
            FROM INVENTORY
            WHERE Item_ID = :iid AND Sponsor_ID = :sid
        """), {"iid": item_id, "sid": sponsor_id}).fetchone()
    
    if not product:
        return "Product not found", 404


    return render_template("sponsorProductDetail.html", nav_pages=NAV_PAGES, logged_in=is_logged_in(), product=product)


@main_bp.post("/sponsor/products/<int:item_id>/available")
def sponsor_product_availability(item_id):
    r = require_role("Sponsor")
    if r:
        return r
    
    sponsor_id = session.get("sponsor_id")
    if not sponsor_id:
        return "Sponsor ID not found in session", 400
    
    with engine.begin() as conn:
        product = conn.execute(text("""
            SELECT Sponsor_ID, Is_Available FROM INVENTORY WHERE Item_ID = :iid
        """), {"iid": item_id}).fetchone()
        if not product:
            return "Product not found", 404
        if product.Sponsor_ID != sponsor_id:
            return "Forbidden", 403

        newStatus = 0 if product.Is_Available else 1
        conn.execute(text("""
            UPDATE INVENTORY SET Is_Available = :status WHERE Item_ID = :iid
        """), {"status": newStatus, "iid": item_id})
    return redirect(url_for("main.sponsor_products"))

@main_bp.get("/admin/home")
def admin_home():
    r = require_role("Admin")
    if r:
        return r
    return render_template("adminHome.html", page_title="Admin Home", nav_pages=NAV_PAGES, logged_in=is_logged_in())


@main_bp.get('/admin/sponsors')
def admin_sponsors():
    r = require_role('Admin')
    if r:
        return r

    # Fetch sponsors with driver counts
    with engine.connect() as conn:
        sponsors = conn.execute(text('''
            SELECT s.Sponsor_ID, s.Sponsor_Name, s.Sponsor_Email, s.Sponsor_Phone,
                   s.Sponsor_Address, s.Sponsor_PointConversion, s.Sponsor_Creation,
                   COALESCE(COUNT(d.User_ID),0) AS driver_count
            FROM SPONSORS s
            LEFT JOIN DRIVERS d ON d.Sponsor_ID = s.Sponsor_ID
            GROUP BY s.Sponsor_ID, s.Sponsor_Name, s.Sponsor_Email, s.Sponsor_Phone, s.Sponsor_Address, s.Sponsor_PointConversion, s.Sponsor_Creation
            ORDER BY s.Sponsor_Name
        ''')).fetchall()

    return render_template('sponsorList.html', nav_pages=NAV_PAGES, logged_in=is_logged_in(), sponsors=sponsors)


@main_bp.get('/admin/users')
def admin_users():
    r = require_role('Admin')
    if r:
        return r

    # Sorting options
    sort = request.args.get('sort', 'username')
    allowed = {
        'username': 'Username',
        'type': 'User_Type',
        'email': 'User_Email',
        'created': 'User_Creation',
        'points': 'd.User_Points'
    }
    order_by = allowed.get(sort, 'Username')

    with engine.connect() as conn:
        users = conn.execute(text(f'''
            SELECT u.User_ID, u.Username, u.User_FName, u.User_LNAME, u.User_Email, u.User_Phone_Num, u.User_Type, u.User_Creation,
                   d.User_Points
            FROM USERS u
            LEFT JOIN DRIVERS d ON d.User_ID = u.User_ID
            ORDER BY {order_by}
        ''')).fetchall()

    return render_template('userList.html', nav_pages=NAV_PAGES, logged_in=is_logged_in(), users=users, current_sort=sort)

@main_bp.get("/store")
def storefront():
    r = require_role("Driver")   # Only drivers can shop
    if r:
        return r

    user = fetch_current_user()

    with engine.connect() as conn:
        products = conn.execute(text("""
            SELECT i.Item_ID, i.Item_Name, i.Prod_Description, i.Prod_Quantity, i.Is_Available,
                ROUND(i.Prod_UnitPrice / s.Sponsor_PointConversion) AS point_cost
            FROM INVENTORY i
            JOIN SPONSORS s ON i.Sponsor_ID = s.Sponsor_ID
            JOIN DRIVERS d ON d.Sponsor_ID = i.Sponsor_ID
            WHERE d.User_ID = :uid AND i.Is_Available = TRUE
            """), {"uid": session["user_id"]}).fetchall()


    search = request.args.get("search")
    category_filter = request.args.get("category")
    min_price = request.args.get("min_price")
    max_price = request.args.get("max_price")
    sort_by = request.args.get("sort_by", "asc")

    if min_price is not None and max_price is not None:
        if min_price > max_price:
            max_price = min_price

    filters = []
    params = {"sid": session.get("sponsor_id")}

    if search:
        filters.append("Item_Name LIKE :search")
        params["search"] = f"%{search}%"

    if category_filter:
        filters.append("Category_Name = :category")
        params["category"] = category_filter
    if min_price:
        filters.append("Prod_UnitPrice >= :min_price")
        params["min_price"] = min_price
    if max_price:
        filters.append("Prod_UnitPrice <= :max_price")
        params["max_price"] = max_price
    order_clause = "ORDER BY Prod_UnitPrice ASC" if sort_by == "asc" else "ORDER BY Prod_UnitPrice DESC"
    filter_statement = " AND ".join(filters) if filters else "1=1"

    with engine.connect() as conn:
        products = conn.execute(text(f"""
            SELECT Item_ID, Item_Name, Prod_Description, Prod_UnitPrice
            FROM INVENTORY
            WHERE Sponsor_ID = :sid AND Is_Available = TRUE AND {filter_statement} {order_clause}
        """), params).fetchall()

        categories = conn.execute(text("""
            SELECT DISTINCT Prod_Category FROM INVENTORY WHERE Sponsor_ID = :sid
        """), {"sid": session.get("sponsor_id")}).fetchall()

        max_point_cost = conn.execute(text("""
            SELECT MAX(Prod_UnitPrice) AS max_price FROM INVENTORY WHERE Sponsor_ID = :sid AND Is_Available = TRUE
        """), {"sid": session.get("sponsor_id")}).fetchone().max_price or 1000

        row = conn.execute(text("""
            SELECT COALESCE(SUM(Quantity), 0) AS cnt
            FROM CART_ITEMS
            WHERE Driver_ID = :uid
        """), {"uid": session["user_id"]}).fetchone()
        cart_count = row.cnt

    return render_template(
        "storefront.html",
        nav_pages=NAV_PAGES,
        logged_in=is_logged_in(),
        user=user,
        products=products,
        categories=categories,
        max_point_cost=max_point_cost,
        cart_count=cart_count
    )



@main_bp.get("/cart")
def cart_page():
    r = require_role("Driver")
    if r: return r
    user = fetch_current_user()
    with engine.connect() as conn:
        cart_items = conn.execute(text("""
            SELECT ci.Item_ID as id, i.Item_Name as name, i.Prod_Description as description,
                   ROUND(i.Prod_UnitPrice / s.Sponsor_PointConversion) AS point_cost,
                   ci.Quantity as quantity, i.Prod_Quantity as stock, '' as image_url
            FROM CART_ITEMS ci
            JOIN INVENTORY i ON ci.Item_ID = i.Item_ID
            JOIN SPONSORS s ON i.Sponsor_ID = s.Sponsor_ID
            WHERE ci.Driver_ID = :uid
        """), {"uid": session["user_id"]}).fetchall()
        total_cost = sum(i.point_cost * i.quantity for i in cart_items)
    return render_template("cart.html", nav_pages=NAV_PAGES, logged_in=is_logged_in(),
                           user=user, cart_items=cart_items, total_cost=total_cost)


# Add to cart
@main_bp.post("/cart/add/<int:item_id>")
def cart_add(item_id):
    r = require_role("Driver")
    if r: return r
    with engine.begin() as conn:
        existing = conn.execute(text(
            "SELECT Quantity FROM CART_ITEMS WHERE Driver_ID=:uid AND Item_ID=:iid"
        ), {"uid": session["user_id"], "iid": item_id}).fetchone()
        if existing:
            conn.execute(text("UPDATE CART_ITEMS SET Quantity=Quantity+1 WHERE Driver_ID=:uid AND Item_ID=:iid"),
                         {"uid": session["user_id"], "iid": item_id})
        else:
            conn.execute(text("INSERT INTO CART_ITEMS (Driver_ID, Item_ID, Quantity) VALUES (:uid, :iid, 1)"),
                         {"uid": session["user_id"], "iid": item_id})
    return redirect(url_for("main.storefront"))


# Update quantity
@main_bp.post("/cart/update/<int:item_id>")
def cart_update(item_id):
    r = require_role("Driver")
    if r: return r
    quantity = int(request.form.get("quantity", 1))
    with engine.begin() as conn:
        if quantity <= 0:
            conn.execute(text("DELETE FROM CART_ITEMS WHERE Driver_ID=:uid AND Item_ID=:iid"),
                         {"uid": session["user_id"], "iid": item_id})
        else:
            conn.execute(text("UPDATE CART_ITEMS SET Quantity=:qty WHERE Driver_ID=:uid AND Item_ID=:iid"),
                         {"qty": quantity, "uid": session["user_id"], "iid": item_id})
    return redirect(url_for("main.cart_page"))


# Remove item
@main_bp.post("/cart/remove/<int:item_id>")
def cart_remove(item_id):
    r = require_role("Driver")
    if r: return r
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM CART_ITEMS WHERE Driver_ID=:uid AND Item_ID=:iid"),
                     {"uid": session["user_id"], "iid": item_id})
    return redirect(url_for("main.cart_page"))


# Checkout
@main_bp.post("/cart/checkout")
def cart_checkout():
    r = require_role("Driver")
    if r: return r
    uid = session["user_id"]
    with engine.begin() as conn:
        # Get cart items with point costs
        cart_items = conn.execute(text("""
            SELECT ci.Item_ID, i.Item_Name, i.Prod_SKU,
                   ROUND(i.Prod_UnitPrice / s.Sponsor_PointConversion) AS point_cost,
                   ci.Quantity, d.Sponsor_ID
            FROM CART_ITEMS ci
            JOIN INVENTORY i ON ci.Item_ID = i.Item_ID
            JOIN SPONSORS s ON i.Sponsor_ID = s.Sponsor_ID
            JOIN DRIVERS d ON d.User_ID = ci.Driver_ID
            WHERE ci.Driver_ID = :uid
        """), {"uid": uid}).fetchall()

        if not cart_items:
            return redirect(url_for("main.cart_page"))

        total_cost = sum(i.point_cost * i.Quantity for i in cart_items)
        sponsor_id = cart_items[0].Sponsor_ID

        # Check driver has enough points
        driver = conn.execute(text(
            "SELECT User_Points FROM DRIVERS WHERE User_ID = :uid"
        ), {"uid": uid}).fetchone()

        if driver.User_Points < total_cost:
            return render_template("cart.html", nav_pages=NAV_PAGES, logged_in=is_logged_in(), 
                                   error="You do not have enough points to complete this purchase.", cart_items=cart_items, total_cost=total_cost)

        # Create the order
        result = conn.execute(text("""
            INSERT INTO ORDERS (Driver_ID, Sponsor_ID, Order_Status, Total_Points)
            VALUES (:uid, :sid, 'Pending', :total)
        """), {"uid": uid, "sid": sponsor_id, "total": total_cost})
        order_id = result.lastrowid

        # Insert line items
        for item in cart_items:
            stock_check = conn.execute(text(
                "SELECT Prod_Quantity FROM INVENTORY WHERE Item_ID = :iid"
            ), {"iid": item.Item_ID}).fetchone()

            if not stock_check or stock_check.Prod_Quantity < item.Quantity:
                flash(f"Sorry, {item.Item_Name} is out of stock.")
                return redirect(url_for("main.cart_page"))
            
            conn.execute(text("""
                INSERT INTO LINE_ITEMS (Item_ID, Order_ID, Prod_SKU, Item_Name, Price_Points, Line_Quantity)
                VALUES (:iid, :oid, :sku, :name, :pts, :qty)
            """), {"iid": item.Item_ID, "oid": order_id, "sku": item.Prod_SKU,
                  "name": item.Item_Name, "pts": item.point_cost, "qty": item.Quantity})

        # Deduct points from driver
        conn.execute(text("""
            UPDATE DRIVERS SET User_Points = User_Points - :total WHERE User_ID = :uid
        """), {"total": total_cost, "uid": uid})

        # Log the point transaction
        conn.execute(text("""
            INSERT INTO POINT_TRANSACTIONS (Driver_ID, Sponsor_ID, Points_Changed, Reason)
            VALUES (:uid, :sid, :pts, 'Order placed')
        """), {"uid": uid, "sid": sponsor_id, "pts": -total_cost})

        # Clear the cart
        conn.execute(text(
            "DELETE FROM CART_ITEMS WHERE Driver_ID = :uid"
        ), {"uid": uid})

    return redirect(url_for("main.driver_home"))

@main_bp.get("/page/<name>")
def blank_page(name):
    r = require_login_redirect()
    if r:
        return r

    allowed = {"page2", "page3"}
    if name not in allowed:
        return "Page not found", 404

    return render_template("page.html", page_title=f"Blank Test Page: {name}",
                           nav_pages=NAV_PAGES, logged_in=is_logged_in())

@main_bp.get("/applications")
def applications_list():
    r = require_role("Sponsor")
    if r:
        r2 = require_role("Admin")
        if r2:
            return r2
        
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    sponsor_filter = request.args.get("sponsor_id")

    filters = []
    params = {}

    with engine.connect() as conn:

        if start_date:
            filters.append("App_Time >= :start_date")
            params["start_date"] = start_date

        if end_date:
            filters.append("App_Time <= :end_date")
            params["end_date"] = end_date

        if session["user_type"] == "Admin" and sponsor_filter:
            filters.append("App_Sponsor_ID = :sponsor_id")
            params["sponsor_id"] = sponsor_filter

        filter_statement = " AND ".join(filters) if filters else "1=1"
                
        if session["user_type"] == "Sponsor":
            apps = conn.execute(text(f""" SELECT Application_ID, App_Status, App_FName, App_LNAME FROM APPLICATIONS
                                     WHERE App_Sponsor_ID = :sid AND {filter_statement} ORDER BY App_Time"""),
                                params | {"sid": session["sponsor_id"]}).fetchall()
        else:
            apps = conn.execute(text(f""" SELECT Application_ID, App_Status, App_FName, App_LNAME FROM APPLICATIONS WHERE {filter_statement} ORDER BY App_Time"""), params).fetchall()
    return render_template("applications_list.html", apps=apps, nav_pages = NAV_PAGES, logged_in=is_logged_in())

@main_bp.get("/applications/<int:app_id>")
def application_details(app_id):
    r = require_role("Sponsor")
    if r:
        r2 = require_role("Admin")
        if r2:
            return r2
    with engine.connect() as conn:
        app = conn.execute(text(""" SELECT Application_ID, App_Sponsor_ID, App_Username,App_Status, App_FName, App_LNAME, App_Email, App_Phone_Num,
                                License_Num, App_Time, Denial_Reason FROM APPLICATIONS
                                 WHERE Application_ID = :aid"""),
                               {"aid": app_id}).fetchone()
    if not app:
        return "Application not found", 404

    if session["user_type"] == "Sponsor" and app.App_Sponsor_ID != session["sponsor_id"]:
        return "Forbidden", 403

    return render_template(
        "application_detail.html",
        app=app, nav_pages=NAV_PAGES, logged_in=is_logged_in())

@main_bp.post("/applications/<int:app_id>/evaluate")
def evaluate_applications(app_id):
    r = require_role("Sponsor")
    if r:
        r2 = require_role("Admin")
        if r2:
            return r2
    decision = request.form.get("decision")
    reason = request.form.get("reason")

    with engine.begin() as conn:
        app = conn.execute(text(""" SELECT App_Sponsor_ID FROM APPLICATIONS WHERE Application_ID = :aid"""), 
                           {"aid": app_id}).fetchone()
        if not app:
            return "Application not found", 404
        if session["user_type"] == "Sponsor" and app["App_Sponsor_ID"] != session["sponsor_id"]:
            return "Forbidden", 403
        
        if decision == "Denied" and not reason:
            return render_template(
                "application_detail.html",
                app=app, nav_pages=NAV_PAGES, logged_in=is_logged_in(),
                error="Reason for denial is required when denying an application."
            )

        conn.execute(text("""UPDATE APPLICATIONS SET App_Status = :status, Denial_Reason = :reason WHERE Application_ID = :aid"""), {"status": decision, "reason": reason if decision == "Denied" else None, "aid": app_id})
        if decision == "Approved":
            conn.execute(text("""DELETE FROM APPLICATIONS WHERE Application_ID = :aid"""), {"aid": app_id})
    return redirect(url_for("main.applications_list"))

@main_bp.get("/admin/create")
def admin_create_page():
    return redirect(url_for("auth.admin_create_page"))

@main_bp.get("/sponsor/create")
def sponsor_create_page():
    return redirect(url_for("auth.sponsor_create_page"))

@main_bp.post("/sponsor/removeDriver")
def remove_driver():
    r = require_role("Sponsor")
    if r:
        return r
    driver_id = request.form.get("driver_id")
    if not driver_id:
        return "Driver ID is required", 400
    
    with engine.begin() as conn:
        driver = conn.execute(text("""
            SELECT User_ID FROM DRIVERS WHERE USER_ID = :did AND Sponsor_ID = :sid
        """), {"did": driver_id, "sid": session["sponsor_id"]}).fetchone()
        if not driver:
            return "Driver not found or not associated with your sponsor account", 404
        
        conn.execute(text("""
            UPDATE DRIVERS SET Is_Active = FALSE WHERE User_ID = :did
        """), {"did": driver_id})
    return redirect(url_for("main.sponsor_home"))