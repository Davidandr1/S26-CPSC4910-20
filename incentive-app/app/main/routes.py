from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from sqlalchemy import text
from app.db import engine
from app.services.importProducts import ProductAPIService
from app.services.inventoryService import InventoryService
from app.services.ScheduledPointEvents import ScheduledPointEventService
from datetime import datetime, timedelta
import os
import io
import csv
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
                SELECT s.Sponsor_Name, ds.Driver_Points
                FROM DRIVER_SPONSORS ds
                JOIN SPONSORS s ON s.Sponsor_ID = ds.Sponsor_ID
                WHERE ds.Driver_ID = :id AND ds.Is_Active = TRUE AND ds.Sponsor_ID = :sid
            """), {"id": user_id, "sid": session.get("active_sponsor_id")}).fetchone()
            sponsor_name = row.Sponsor_Name if row else None
            user["points"] = row.Driver_Points if row and hasattr(row, 'Driver_Points') else 0

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
    active_sponsor_id = session.get("active_sponsor_id")
    active_sponsor_name = session.get("active_sponsor_name")
    with engine.connect() as conn:
        sponsors = conn.execute(text("""
                                     SELECT ds.Sponsor_ID, s.Sponsor_Name, ds.Driver_Points
                                     FROM DRIVER_SPONSORS ds
                                     JOIN SPONSORS s ON s.Sponsor_ID = ds.Sponsor_ID
                                     WHERE ds.Driver_ID = :uid AND ds.Is_Active = TRUE
                                     ORDER BY s.Sponsor_Name
        """), {"uid": driver_id}).fetchall()

        if not active_sponsor_id and sponsors:
            active_sponsor_id = sponsors[0].Sponsor_ID
            active_sponsor_name = sponsors[0].Sponsor_Name
            session["active_sponsor_id"] = active_sponsor_id
            session["active_sponsor_name"] = active_sponsor_name
        
        if active_sponsor_id:
            active_sponsor = conn.execute(text("SELECT ds.Sponsor_ID, s.Sponsor_Name, ds.Driver_Points FROM DRIVER_SPONSORS ds JOIN SPONSORS s ON s.Sponsor_ID = ds.Sponsor_ID WHERE ds.Driver_ID = :uid AND ds.Sponsor_ID = :sid AND ds.Is_Active = TRUE"), {"uid": driver_id, "sid": active_sponsor_id}).fetchone()
            if active_sponsor:
                points = active_sponsor.Driver_Points if hasattr(active_sponsor, 'Driver_Points') else 0
        transactions = conn.execute(text("""
            SELECT Points_Changed, Reason, Transaction_Time FROM POINT_TRANSACTIONS WHERE Driver_ID = :uid AND Sponsor_ID = :sid ORDER BY Transaction_Time DESC
        """), {"uid": driver_id, "sid": active_sponsor_id}).fetchall()
    return render_template("driverHome.html", page_title="Driver Home", nav_pages=NAV_PAGES, logged_in=is_logged_in(), transactions=transactions, points=points, sponsors=sponsors, active_sponsor_id=active_sponsor_id, active_sponsor=active_sponsor)


@main_bp.get("/driver/points")
def driver_points_api():
    r = require_role("Driver")
    if r:
        return r

    driver_id = session.get("user_id")
    active_sponsor_id = session.get("active_sponsor_id")
    with engine.connect() as conn:
        row = conn.execute(text("SELECT Driver_Points FROM DRIVER_SPONSORS WHERE Driver_ID = :uid AND Sponsor_ID = :sid"), {"uid": driver_id, "sid": active_sponsor_id}).fetchone()

    points = row.Driver_Points if row else 0
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
    events = []
    with engine.connect() as conn:
        drivers = conn.execute(text("""
            SELECT ds.Driver_ID, ds.Driver_Points, u.User_FName, u.User_LName, u.User_Email, u.User_Phone_Num
            FROM DRIVER_SPONSORS ds
            JOIN USERS u ON ds.Driver_ID = u.User_ID
            WHERE ds.Sponsor_ID = :sid AND ds.Is_Active = TRUE
        """), {"sid": sponsor_id}).fetchall()

        # Load sponsor-created point events (presets)
        events = conn.execute(text("""
            SELECT Event_ID, Event_Name, Event_Points, Created_At
            FROM POINT_EVENTS
            WHERE Sponsor_ID = :sid
            ORDER BY Created_At DESC
        """), {"sid": sponsor_id}).fetchall()

    return render_template("sponsorHome.html", nav_pages=NAV_PAGES, logged_in=is_logged_in(), drivers=drivers, sponsor=sponsor, events=events)


@main_bp.get('/sponsor/points')
def sponsor_points_page():
    r = require_role('Sponsor')
    if r:
        return r
    sponsor_id = session.get('sponsor_id')
    if not sponsor_id:
        return "Sponsor ID not found in session", 400
    with engine.connect() as conn:
        drivers = conn.execute(text("""
            SELECT ds.Driver_ID, ds.Driver_Points, u.User_FName, u.User_LName, u.User_Email
            FROM DRIVER_SPONSORS ds
            JOIN USERS u ON ds.Driver_ID = u.User_ID
            WHERE ds.Sponsor_ID = :sid AND ds.Is_Active = TRUE
        """), {"sid": sponsor_id}).fetchall()

        events = conn.execute(text("SELECT Event_ID, Event_Name, Event_Points FROM POINT_EVENTS WHERE Sponsor_ID = :sid ORDER BY Created_At DESC"), {"sid": sponsor_id}).fetchall()

    return render_template('sponsorPoints.html', nav_pages=NAV_PAGES, logged_in=is_logged_in(), drivers=drivers, events=events)


@main_bp.get('/sponsor/events')
def sponsor_events_page():
    r = require_role('Sponsor')
    if r:
        return r
    try:
        ScheduledPointEventService.process_scheduled_events()
    except Exception as e:
        print("Scheduled event processing failed:", e)

    sponsor_id = session.get('sponsor_id')
    if not sponsor_id:
        return "Sponsor ID not found in session", 400
    
    with engine.connect() as conn:
        drivers = conn.execute(text("""SELECT ds.Driver_ID, User_FName, User_LName FROM DRIVER_SPONSORS ds JOIN USERS u ON ds.Driver_ID = u.User_ID WHERE ds.Sponsor_ID = :sid AND ds.Is_Active = TRUE"""), {"sid": sponsor_id}).fetchall()
        events = conn.execute(text("SELECT Event_ID, Event_Name, Event_Points, Created_At FROM POINT_EVENTS WHERE Sponsor_ID = :sid ORDER BY Created_At DESC"), {"sid": sponsor_id}).fetchall()
    return render_template('sponsorEvents.html', nav_pages=NAV_PAGES, logged_in=is_logged_in(), drivers=drivers, events=events)


@main_bp.post('/sponsor/events/create')
def sponsor_create_event():
    r = require_role('Sponsor')
    if r:
        return r
    sponsor_id = session.get('sponsor_id')
    if not sponsor_id:
        return "Sponsor ID not found in session", 400

    name = request.form.get('event_name')
    points = request.form.get('event_points')
    # Validation
    try:
        points = int(points)
    except Exception:
        flash('Event points must be an integer.', 'error')
        return redirect(url_for('main.sponsor_home'))

    if not name or points == 0:
        flash('Event name is required and points cannot be zero.', 'error')
        return redirect(url_for('main.sponsor_home'))

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO POINT_EVENTS (Sponsor_ID, Event_Name, Event_Points, Created_At)
            VALUES (:sid, :name, :pts, CURRENT_TIMESTAMP)
        """), {"sid": sponsor_id, "name": name, "pts": points})

    flash('Event created successfully.', 'success')
    return redirect(url_for('main.sponsor_home'))


@main_bp.post('/sponsor/events/delete')
def sponsor_delete_event():
    r = require_role('Sponsor')
    if r:
        return r
    sponsor_id = session.get('sponsor_id')
    event_id = request.form.get('event_id')
    if not event_id:
        return redirect(url_for('main.sponsor_home'))

    with engine.begin() as conn:
        # Ensure event belongs to sponsor
        row = conn.execute(text("SELECT Sponsor_ID FROM POINT_EVENTS WHERE Event_ID = :eid"), {"eid": event_id}).fetchone()
        if not row or row.Sponsor_ID != sponsor_id:
            flash('Event not found or forbidden.', 'error')
            return redirect(url_for('main.sponsor_home'))
        conn.execute(text("DELETE FROM POINT_EVENTS WHERE Event_ID = :eid"), {"eid": event_id})

    flash('Event deleted.', 'success')
    return redirect(url_for('main.sponsor_home'))


@main_bp.post('/sponsor/events/schedule')
def sponsor_schedule_event():
    r = require_role('Sponsor')
    if r:
        r2 = require_role('Admin')
        if r2:
            return r2
    sponsor_id = session.get('sponsor_id')
    current_user = session.get('user_id')
    event_name = None

    if not sponsor_id or not current_user:
        return "Sponsor ID or User ID not found in session", 400
    if not current_user:
        return "User ID not found in session", 400
    
    event_id = request.form.get('event_id')

    if not event_id:
        flash('Event ID is required to schedule.', 'error')
        return redirect(url_for('main.sponsor_events_page'))
    
    driver_ids = request.form.getlist('driver_id')
    if not driver_ids:
        flash('No drivers selected.', 'error')
        return redirect(url_for('main.sponsor_events_page'))
    
   
    try:
        scheduled_for = datetime.strptime(request.form.get('scheduled_time').strip(), '%Y-%m-%dT%H:%M')
    except ValueError:
        flash('Scheduled Time is Invalid', "error")
        return redirect(url_for("main.sponsor_events_page"))

    if scheduled_for < datetime.now():
        flash('Scheduled time must be in the future.', 'error')
        return redirect(url_for('main.sponsor_events_page'))
    
    with engine.connect() as conn:
        event = conn.execute(text("SELECT Event_Name, Event_ID, Event_Points FROM POINT_EVENTS WHERE Event_ID = :eid AND Sponsor_ID = :sid"), {"eid": event_id, "sid": sponsor_id}).fetchone()
        if not event:
            flash('Selected event not found for your sponsor account.', 'error')
            return redirect(url_for('main.sponsor_events_page'))
        event_name = event.Event_Name
    
    created = ScheduledPointEventService.create_scheduled_events_bulk(sponsor_id, driver_ids, current_user, event.Event_Points, event_name, scheduled_for, event_id, event_name)

    if created == 0:
        flash('No events were scheduled; verify driver selection.', 'error')
    else:
        flash(f'{created} event(s) scheduled successfully.', 'success')
    return redirect(url_for('main.sponsor_events_page'))

@main_bp.get('/sponsor/points/scheduled')
def sponsor_scheduled_points_page():
    r = require_role('Sponsor')
    if r:
        r2 = require_role('Admin')
        if r2:
            return r2
    sponsor_id = session.get('sponsor_id')
    if not sponsor_id:
        return "Sponsor ID not found in session", 400
    events = ScheduledPointEventService.get_scheduled_events_for_sponsor(sponsor_id)
    return render_template('sponsorScheduledPoints.html', nav_pages=NAV_PAGES, logged_in=is_logged_in(), scheduled_events=events)

@main_bp.post('/tasks/process_scheduled_events')
def process_scheduled_events():
    processed = ScheduledPointEventService.process_scheduled_events()
    return {"processed": processed}

@main_bp.post('/sponsor/scheduled_events/cancel')
def sponsor_cancel_scheduled_event():
    r = require_role('Sponsor')
    if r:
        r2 = require_role('Admin')
        if r2:
            return r2
    sponsor_id = session.get('sponsor_id')
    if not sponsor_id:
        return "Sponsor ID not found in session", 400

    scheduled_event_id = request.form.get('scheduled_event_id')
    if not scheduled_event_id:
        return "Scheduled Event ID not provided", 400

    cancelled = ScheduledPointEventService.cancel_scheduled_event(scheduled_event_id, sponsor_id)
    if cancelled:
        flash('Scheduled event cancelled successfully.', 'success')
    else:
        flash('Failed to cancel scheduled event. It may have already been processed or cancelled.', 'error')

    return redirect(url_for('main.sponsor_scheduled_points_page'))


@main_bp.post('/sponsor/points/adjust')
def sponsor_adjust_points():
    r = require_role('Sponsor')
    if r:
        return r
    sponsor_id = session.get('sponsor_id')
    if not sponsor_id:
        return "Sponsor ID not found in session", 400
    
    current_user = session.get('user_id')
    if not current_user:
        return "User ID not found in session", 400

    # driver_ids may be passed as multiple form values 'driver_id'
    driver_ids = request.form.getlist('driver_id')
    # fallback to comma separated
    if not driver_ids:
        raw = request.form.get('driver_ids')
        if raw:
            driver_ids = [d.strip() for d in raw.split(',') if d.strip()]

    # If an event was selected, use its points and default reason
    event_id = request.form.get('event_id')
    event = None
    if event_id:
        with engine.connect() as conn:
            event = conn.execute(text("SELECT Event_ID, Event_Name, Event_Points, Sponsor_ID FROM POINT_EVENTS WHERE Event_ID = :eid"), {"eid": event_id}).fetchone()
        if not event:
            flash('Selected event not found.', 'error')
            return redirect(url_for('main.sponsor_home'))
        if event.Sponsor_ID != sponsor_id:
            flash('Selected event does not belong to your sponsor account.', 'error')
            return redirect(url_for('main.sponsor_home'))

    # Validate points (use event points if provided)
    pts = None
    if event:
        pts = int(event.Event_Points)

    if pts is None:
        pts_raw = request.form.get('points', None)
        if pts_raw is None:
            flash('Points value is required.', 'error')
            return redirect(url_for('main.sponsor_home'))
        try:
            pts = int(pts_raw)
        except Exception:
            flash('Points must be an integer.', 'error')
            return redirect(url_for('main.sponsor_home'))

    event_reason = (event.Event_Name if event else '').strip()
    type_reason = request.form.get('reason', '').strip()
    reason = ""

    if not event_reason and not type_reason:
        flash('A reason for the point adjustment is required.', 'error')
        return redirect(url_for('main.sponsor_home'))
    elif type_reason and event_reason:
        reason = event_reason
    elif event_reason and not type_reason:
        reason = event_reason
    else:
        reason = type_reason
        

    if not driver_ids:
        flash('No drivers selected.', 'error')
        return redirect(url_for('main.sponsor_home'))
    if pts == 0:
        flash('Points cannot be zero.', 'error')
        return redirect(url_for('main.sponsor_home'))

    updated = 0
    skipped_insufficient = 0
    skipped_at_cap = 0
    with engine.begin() as conn:
        sponsor_info = conn.execute(text(""" SELECT COALESCE(Sponsor_MaxPoints, 3000000) AS Sponsor_MaxPoints FROM SPONSORS WHERE Sponsor_ID = :sid"""),
                                        {"sid": sponsor_id}).fetchone()
        sponsor_cap = sponsor_info.Sponsor_MaxPoints if sponsor_info else 3000000
        for did in driver_ids:
            # verify driver belongs to sponsor
            drv = conn.execute(text("SELECT Driver_ID, Driver_Points FROM DRIVER_SPONSORS WHERE Driver_ID = :did AND Sponsor_ID = :sid"), {"did": did, "sid": sponsor_id}).fetchone()
            if not drv:
                continue
            
            # Check current points to avoid negative balance
            driverPoints = drv.Driver_Points if drv and hasattr(drv, 'Driver_Points') else 0
            new_points = driverPoints + pts
            if new_points > sponsor_cap:
                new_points = sponsor_cap
            
            if new_points < 0:
                skipped_insufficient +=1
                continue

            point_change = new_points - driverPoints
            if point_change == 0:
                skipped_at_cap += 1
            
            # Update points (no transaction logging here)
            conn.execute(text("UPDATE DRIVER_SPONSORS SET Driver_Points = Driver_Points + :pts WHERE DRIVER_ID = :did AND SPONSOR_ID = :sid"), {"pts": point_change, "did": did, "sid": sponsor_id})
            updated += 1

            conn.execute(text("""INSERT INTO POINT_TRANSACTIONS (Driver_ID, Sponsor_ID, Actor_User_ID, Points_Changed, Reason, Transaction_Time) VALUES (:did, :sid, :actor_id, :pts, :reason, CURRENT_TIMESTAMP)"""),
                            {"did": did, "sid": sponsor_id, "actor_id": current_user, "pts": point_change, "reason": reason})

    if updated == 0:
        msg = 'No drivers were updated; verify selection and sponsor association.'
        if skipped_insufficient:
            msg += f' {skipped_insufficient} driver(s) skipped due to insufficient points. '
        if skipped_at_cap:
            msg += f' {skipped_at_cap} driver(s) skipped due to max points.'
        flash(msg, 'error')
    else:
        action = 'added to' if pts > 0 else 'removed from'
        msg = f'{abs(point_change)} points {action} {updated} driver(s).'
        if skipped_insufficient:
            msg += f' {skipped_insufficient} driver(s) skipped due to insufficient points.'
        if skipped_at_cap:
            msg += f' {skipped_at_cap} driver(s) skipped due to max points.'
        flash(msg, 'success')

    return redirect(url_for('main.sponsor_home'))

@main_bp.get("/sponsor/products")
def sponsor_products():
    r = require_role("Sponsor")
    if r:
        return r
    
    sponsor_id = session.get("sponsor_id")
    if not sponsor_id:
        return "Sponsor ID not found in session", 400

    categories = request.args.get("categories", "").strip()
    
    with engine.connect() as conn:
        category_filter = "AND Prod_Category IN :cats" if categories else ""
        products = conn.execute(text(f"""
            SELECT Item_ID, Item_Name, Prod_Description, Prod_Quantity, Prod_UnitPrice, Is_Available, Product_Image_URL, Point_Value
            FROM INVENTORY
            WHERE Sponsor_ID = :sid {category_filter}
        """), {"sid": sponsor_id, "cats": tuple(categories.split(",")) if categories else ()}).fetchall()

        sponsor = conn.execute(text("""
                                    SELECT Sponsor_Name, Sponsor_PointConversion, Sponsor_MaxPoints FROM SPONSORS WHERE Sponsor_ID = :sid
                                """), {"sid": sponsor_id}).fetchone()
        
        categories = conn.execute(text("""
            SELECT DISTINCT Prod_Category FROM INVENTORY WHERE Sponsor_ID = :sid AND Prod_Category IS NOT NULL AND Prod_Category != ''
        """), {"sid": sponsor_id}).fetchall()

    return render_template("sponsorProducts.html", nav_pages=NAV_PAGES, logged_in=is_logged_in(), products=products, sponsor=sponsor, categories=categories)

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
            SELECT Item_ID, Prod_SKU, Item_Name, Prod_Description, Prod_Quantity, Prod_UnitPrice, Is_Available, Product_Image_URL, Point_Value
            FROM INVENTORY
            WHERE Item_ID = :iid AND Sponsor_ID = :sid
        """), {"iid": item_id, "sid": sponsor_id}).fetchone()
    
    if not product:
        return "Product not found", 404


    return render_template("sponsorProductDetail.html", nav_pages=NAV_PAGES, logged_in=is_logged_in(), product=product)

@main_bp.route("/sponsor/products/search", methods=["GET"])
def api_search_products():
    """
    query params:
    - q: search query (required)
    - limit: max results (default 20)
    """
    r = require_role("Sponsor")
    if r:
        return {"error": "Unauthorized"}, 401
    search_query = request.args.get("q", "").strip()
    limit = int(request.args.get("limit", 20))
    if not search_query:
        return {"error": "Search query required"}, 400
    
    sponsor_id = session.get("sponsor_id")
    if not sponsor_id:
        return {"error": "Sponsor ID not found in session"}, 400
    with engine.connect() as conn:
        sponsor = conn.execute(text("SELECT Sponsor_PointConversion FROM SPONSORS WHERE Sponsor_ID = :sid"), {"sid": sponsor_id}).fetchone()
    if not sponsor:
        return {"error": "Sponsor not found"}, 404
    conversion_rate = float(sponsor.Sponsor_PointConversion or 0)
    
    try:
        ebay = ProductAPIService()
        products = ebay.get_products(search_query, limit=min(limit, 50))
        items = []
        for product in products:
            price = float(product.get("price", {}).get("value", 0) or 0)
            points = int(price/conversion_rate)
            categories = product.get("categories", [])
            category_name = categories[0].get("categoryName") if categories else "Uncategorized"
            items.append({
                "external_id": product.get("itemId"),
                "name": product.get("title"),
                "description": product.get("condition", ""),
                "category": category_name,
                "price": price,
                "points": points,
                "image": product.get("image", {}).get("imageUrl")
            })
        return {
            "success": True,
            "count": len(items),
            "products": items
        }, 200
        
    except Exception as e:
        return {"error": str(e)}, 500
    
@main_bp.route("/api/sponsor/products", methods=["POST"])
def api_add_product():
    """ request body:
        {
        "external_id": "ebay_item_id",
        "name": "Product Name",
        "description": "Product description",
        "price": 99.99,
        "image": "http://image-url.jpg",
        "quantity": 50
    }
    """
    r = require_role("Sponsor")
    if r:
        return {"error": "Unauthorized"}, 401
    sponsor_id = session.get("sponsor_id")
    if not sponsor_id:
        return {"error": "Sponsor ID not found"}, 400
    data = request.get_json()
    if not data:
        return {"error": "Invalid JSON body"}, 400
    required_fields = ["external_id", "name", "price"]
    for field in required_fields:
        if field not in data:
            return {"error": f"Missing required field: {field}"}, 400
    
    try:
        product_data = {
            "external_id": data["external_id"],
            "name": data["name"],
            "description": data.get("description", ""),
            "price": float(data["price"]),
            "category": data.get("category", "Uncategorized"),
            "image": data.get("image"),
            "quantity": data.get("quantity", 50)
        }
        item_id = InventoryService.add_product(sponsor_id, product_data)
        return {
            "success": True,
            "message": "Product added successfully",
            "item_id": item_id
        }, 201
        
    except ValueError as e:
        return {"error": str(e)}, 409
    except Exception as e:
        return {"error": str(e)}, 500

@main_bp.route("/sponsor/products/<int:item_id>", methods=["DELETE"])
def api_delete_product(item_id):

    r = require_role("Sponsor")
    if r:
        return {"error": "Unauthorized"}, 401
    
    sponsor_id = session.get("sponsor_id")
    if not sponsor_id:
        return {"error": "Sponsor ID not found"}, 400
    
    try:
        deleted = InventoryService.delete_product(sponsor_id, item_id)
        
        if not deleted:
            return {"error": "Product not found or does not belong to this sponsor"}, 404
        
        return {
            "success": True,
            "message": f"Product {item_id} deleted successfully"
        }, 200
        
    except Exception as e:
        return {"error": str(e)}, 500

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

@main_bp.post("/sponsor/point-conversion")
def sponsor_point_conversion():
    r = require_role("Sponsor")
    if r:
        return r
    
    sponsor_id = session.get("sponsor_id")
    if not sponsor_id:
        return "Sponsor ID not found in session", 400
    
    new_rate = request.form.get("conversion_rate")
    if not new_rate:
        flash("Conversion rate is required.", "error")
        return redirect(url_for("main.sponsor_home"))
    
    try:
        new_rate = float(new_rate)
        if new_rate <= 0:
            raise ValueError
    except ValueError:
        flash("Conversion rate must be a positive number.", "error")
        return redirect(url_for("main.sponsor_home"))
    
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE SPONSORS SET Sponsor_PointConversion = :rate WHERE Sponsor_ID = :sid
        """), {"rate": new_rate, "sid": sponsor_id})

        conn.execute(text("""
            UPDATE INVENTORY SET Point_Value = ROUND(Prod_UnitPrice / :rate) WHERE Sponsor_ID = :sid
        """), {"rate": new_rate, "sid": sponsor_id})
    
    flash("Point conversion rate updated successfully.", "success")
    return redirect(url_for("main.sponsor_home"))

@main_bp.post("/sponsor/max-points")
def sponsor_max_points():
    r = require_role("Sponsor")
    if r:
        return r
    sponsor_id = session.get("sponsor_id")
    if not sponsor_id:
        return "Sponsor ID not found in session", 400
    new_cap = request.form.get("max_points")
    if not new_cap:
        flash("Max points value is required.", "error")
        return redirect(url_for("main.sponsor_home"))
    try:
        new_cap = int(new_cap)
        if new_cap <= 0:
            raise ValueError
    except ValueError:
        flash("Max points must be a positive integer.", "error")
        return redirect(url_for("main.sponsor_home"))
    
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE SPONSORS SET Sponsor_MaxPoints = :cap WHERE Sponsor_ID = :sid
        """), {"cap": new_cap, "sid": sponsor_id})
    flash("Max points updated successfully.", "success")
    return redirect(url_for("main.sponsor_home"))

@main_bp.get("/admin/home")
def admin_home():
    r = require_role("Admin")
    if r:
        return r
    return render_template("adminHome.html", page_title="Admin Home", nav_pages=NAV_PAGES, logged_in=is_logged_in())


@main_bp.route('/admin/invoices', methods=['GET', 'POST'])
def admin_invoices():
    r = require_role('Admin')
    if r:
        return r

    sponsors = []
    invoices = []
    params = {}
    start_date = request.values.get('start_date')
    end_date = request.values.get('end_date')
    sponsor_filter = request.values.get('sponsor_id', '')

    with engine.connect() as conn:
        sponsors = conn.execute(text("SELECT Sponsor_ID, Sponsor_Name FROM SPONSORS ORDER BY Sponsor_Name")).fetchall()

        if request.method == 'POST':
            # Determine list of sponsor ids to generate for
            target_sponsors = []
            if sponsor_filter and sponsor_filter.lower() != 'all':
                try:
                    target_sponsors = [int(sponsor_filter)]
                except Exception:
                    target_sponsors = []
            else:
                target_sponsors = [s.Sponsor_ID for s in sponsors]

            # Parse dates (inclusive)
            start_dt = None
            end_dt = None
            if start_date:
                try:
                    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                except Exception:
                    start_dt = None
            if end_date:
                try:
                    # include full day
                    end_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                except Exception:
                    end_dt = None

            for sid in target_sponsors:
                inv = {
                    'Sponsor_ID': sid,
                    'Sponsor_Name': None,
                    'orders': [],
                    'drivers': {},
                    'totals': {'points': 0, 'amount': 0.0, 'fee': 0.0}
                }

                sponsor = conn.execute(text("SELECT Sponsor_ID, Sponsor_Name, Sponsor_PointConversion, Sponsor_Email, Sponsor_Phone, Sponsor_Address FROM SPONSORS WHERE Sponsor_ID = :sid"), {"sid": sid}).fetchone()
                if not sponsor:
                    continue
                inv['Sponsor_Name'] = sponsor.Sponsor_Name
                conversion = float(sponsor.Sponsor_PointConversion or 0)

                # Fetch orders (include Pending and Completed; exclude Cancelled)
                q = "SELECT o.Order_ID, o.Driver_ID, o.Total_Points, o.OrderTime, u.User_FName, u.User_LNAME FROM ORDERS o JOIN USERS u ON o.Driver_ID = u.User_ID WHERE o.Sponsor_ID = :sid AND o.Order_Status != 'Cancelled'"
                qparams = {"sid": sid}
                if start_dt:
                    q += " AND o.OrderTime >= :start"
                    qparams['start'] = start_dt
                if end_dt:
                    q += " AND o.OrderTime < :end"
                    qparams['end'] = end_dt
                q += " ORDER BY o.OrderTime"

                orders = conn.execute(text(q), qparams).fetchall()
                for o in orders:
                    pts = int(o.Total_Points or 0)
                    amount = round(pts * conversion, 2)
                    fee = round(amount * 0.01, 2)
                    driver_name = f"{o.User_FName} {o.User_LNAME}" if hasattr(o, 'User_FName') else ''

                    row = {
                        'Order_ID': o.Order_ID,
                        'OrderTime': o.OrderTime,
                        'Driver_ID': o.Driver_ID,
                        'Driver_Name': driver_name,
                        'Points': pts,
                        'Conversion': conversion,
                        'Amount_USD': amount,
                        'Fee_USD': fee
                    }
                    inv['orders'].append(row)

                    # accumulate per-driver
                    d = inv['drivers'].setdefault(o.Driver_ID, {'Driver_ID': o.Driver_ID, 'Driver_Name': driver_name, 'Points': 0, 'Amount_USD': 0.0, 'Fee_USD': 0.0})
                    d['Points'] += pts
                    d['Amount_USD'] = round(d['Amount_USD'] + amount, 2)
                    d['Fee_USD'] = round(d['Fee_USD'] + fee, 2)

                    inv['totals']['points'] += pts
                    inv['totals']['amount'] = round(inv['totals']['amount'] + amount, 2)
                    inv['totals']['fee'] = round(inv['totals']['fee'] + fee, 2)

                invoices.append(inv)

    return render_template('adminInvoices.html', nav_pages=NAV_PAGES, logged_in=is_logged_in(), sponsors=sponsors, invoices=invoices, selected_sponsor=sponsor_filter, start_date=start_date, end_date=end_date)


@main_bp.get('/admin/invoices/download/<int:sponsor_id>')
def admin_invoice_download(sponsor_id):
    r = require_role('Admin')
    if r:
        return r

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        except Exception:
            start_dt = None
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
        except Exception:
            end_dt = None

    # Build invoice (same logic as generation)
    with engine.connect() as conn:
        sponsor = conn.execute(text("SELECT Sponsor_ID, Sponsor_Name, Sponsor_PointConversion, Sponsor_Email, Sponsor_Phone, Sponsor_Address FROM SPONSORS WHERE Sponsor_ID = :sid"), {"sid": sponsor_id}).fetchone()
        if not sponsor:
            return "Sponsor not found", 404
        conversion = float(sponsor.Sponsor_PointConversion or 0)

        q = "SELECT o.Order_ID, o.Driver_ID, o.Total_Points, o.OrderTime, u.User_FName, u.User_LNAME FROM ORDERS o JOIN USERS u ON o.Driver_ID = u.User_ID WHERE o.Sponsor_ID = :sid AND o.Order_Status != 'Cancelled'"
        qparams = {"sid": sponsor_id}
        if start_dt:
            q += " AND o.OrderTime >= :start"
            qparams['start'] = start_dt
        if end_dt:
            q += " AND o.OrderTime < :end"
            qparams['end'] = end_dt
        q += " ORDER BY o.OrderTime"

        orders = conn.execute(text(q), qparams).fetchall()

    # Prepare CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    invoice_num = f"INV-{sponsor.Sponsor_ID}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    writer.writerow(['Invoice_Number', invoice_num])
    writer.writerow(['Invoice_Date', datetime.now().isoformat()])
    writer.writerow(['Sponsor_Name', sponsor.Sponsor_Name])
    writer.writerow(['Sponsor_ID', sponsor.Sponsor_ID])
    writer.writerow(['Start_Date', start_date or ''])
    writer.writerow(['End_Date', end_date or ''])
    writer.writerow([])

    # Column headers
    writer.writerow(['Order_ID', 'OrderTime', 'Driver_ID', 'Driver_Name', 'Points', 'Conversion', 'Amount_USD', 'Fee_USD'])

    totals_points = 0
    totals_amount = 0.0
    totals_fee = 0.0

    drivers = {}
    for o in orders:
        pts = int(o.Total_Points or 0)
        amount = round(pts * conversion, 2)
        fee = round(amount * 0.01, 2)
        driver_name = f"{o.User_FName} {o.User_LNAME}" if hasattr(o, 'User_FName') else ''

        writer.writerow([o.Order_ID, o.OrderTime.isoformat() if hasattr(o.OrderTime, 'isoformat') else str(o.OrderTime), o.Driver_ID, driver_name, pts, conversion, f"{amount:.2f}", f"{fee:.2f}"])

        totals_points += pts
        totals_amount = round(totals_amount + amount, 2)
        totals_fee = round(totals_fee + fee, 2)

        d = drivers.setdefault(o.Driver_ID, {'Driver_ID': o.Driver_ID, 'Driver_Name': driver_name, 'Points': 0, 'Amount_USD': 0.0, 'Fee_USD': 0.0})
        d['Points'] += pts
        d['Amount_USD'] = round(d['Amount_USD'] + amount, 2)
        d['Fee_USD'] = round(d['Fee_USD'] + fee, 2)

    # Blank line then driver summaries
    writer.writerow([])
    writer.writerow(['Driver_ID', 'Driver_Name', 'Total_Points', 'Total_Amount_USD', 'Total_Fee_USD'])
    for did, d in drivers.items():
        writer.writerow([d['Driver_ID'], d['Driver_Name'], d['Points'], f"{d['Amount_USD']:.2f}", f"{d['Fee_USD']:.2f}"])

    # Totals
    writer.writerow([])
    writer.writerow(['Total_Points', totals_points])
    writer.writerow(['Total_Amount_USD', f"{totals_amount:.2f}"])
    writer.writerow(['Total_Fee_USD', f"{totals_fee:.2f}"])

    output.seek(0)
    csv_bytes = output.getvalue().encode('utf-8')

    from flask import Response
    resp = Response(csv_bytes, mimetype='text/csv')
    resp.headers.set('Content-Disposition', 'attachment', filename=f"invoice_{sponsor.Sponsor_ID}_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv")
    return resp


@main_bp.get('/admin/sponsors')
def admin_sponsors():
    r = require_role('Admin')
    if r:
        return r

    # Fetch sponsors with driver counts
    with engine.connect() as conn:
        sponsors = conn.execute(text('''
            SELECT s.Sponsor_ID, s.Sponsor_Name, s.Sponsor_Email, s.Sponsor_Phone,
                   s.Sponsor_Address, s.Sponsor_PointConversion, s.Sponsor_MaxPoints,s.Sponsor_Creation,
                   COALESCE(COUNT(d.Driver_ID),0) AS driver_count
            FROM SPONSORS s
            LEFT JOIN DRIVER_SPONSORS d ON d.Sponsor_ID = s.Sponsor_ID
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
        'points': 'ds.Driver_Points'
    }
    order_by = allowed.get(sort, 'Username')

    with engine.connect() as conn:
        users = conn.execute(text(f'''
            SELECT u.User_ID, u.Username, u.User_FName, u.User_LNAME, u.User_Email, u.User_Phone_Num, u.User_Type, u.User_Creation,
                   ds.Driver_Points
            FROM USERS u
            LEFT JOIN DRIVER_SPONSORS ds ON ds.Driver_ID = u.User_ID
            ORDER BY {order_by}
        ''')).fetchall()

    return render_template('userList.html', nav_pages=NAV_PAGES, logged_in=is_logged_in(), users=users, current_sort=sort)

@main_bp.get("/store")
def storefront():
    r = require_role("Driver")
    if r:
        return r

    user = fetch_current_user()
    uid = session["user_id"]

    # Get query params safely
    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()
    sort_by = request.args.get("sort_by", "asc")

    try:
        min_points = int(request.args.get("min_price", 0))
    except:
        min_points = 0

    try:
        max_points = int(request.args.get("max_price", 999999))
    except:
        max_points = 999999

    if min_points > max_points:
        max_points = min_points

    # Build query 
    filters = ["i.Is_Available = TRUE"]
    params = {"uid": uid}

    if search:
        filters.append("i.Item_Name LIKE :search")
        params["search"] = f"%{search}%"

    if category:
        filters.append("i.Prod_Category = :category")
        params["category"] = category

    # Filter by points
    filters.append("i.Point_Value >= :min_points")
    filters.append("i.Point_Value <= :max_points")
    params["min_points"] = min_points
    params["max_points"] = max_points

    order_clause = "i.Point_Value ASC" if sort_by == "asc" else "i.Point_Value DESC"
    where_clause = " AND ".join(filters)

    # Query DB
    with engine.connect() as conn:

        # Get driver's sponsor
        sponsor_id = session.get("active_sponsor_id")
        params["sid"] = sponsor_id

        # Main product query
        products = conn.execute(text(f"""
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
        """), params).fetchall()

        # Categories for dropdown
        categories = conn.execute(text("""
            SELECT DISTINCT Prod_Category 
            FROM INVENTORY 
            WHERE Sponsor_ID = :sid 
              AND Prod_Category IS NOT NULL 
              AND Prod_Category != ''
        """), {"sid": sponsor_id}).fetchall()

        # Max points for slider
        max_point_cost_row = conn.execute(text("""
            SELECT MAX(Point_Value) AS max_points 
            FROM INVENTORY 
            WHERE Sponsor_ID = :sid AND Is_Available = TRUE
        """), {"sid": sponsor_id}).fetchone()

        max_point_cost = max_point_cost_row.max_points if max_point_cost_row and max_point_cost_row.max_points else 1000

        # User points
        points_row = conn.execute(text("""
            SELECT Driver_Points FROM DRIVER_SPONSORS WHERE Driver_ID = :uid AND Sponsor_ID = :sid
        """), {"uid": uid, "sid": sponsor_id}).fetchone()

        user_points = points_row.Driver_Points if points_row else 0

        # Cart count
        cart_row = conn.execute(text("""
            SELECT COALESCE(SUM(Quantity), 0) AS cnt
            FROM CART_ITEMS
            WHERE Driver_ID = :uid AND Sponsor_ID = :sid
        """), {"uid": uid, "sid": sponsor_id}).fetchone()

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
        cart_count=cart_count
    )



@main_bp.get("/cart")
def cart_page():
    r = require_role("Driver")
    if r: return r
    user = fetch_current_user()
    active_sponsor_id = session.get("active_sponsor_id")
    with engine.connect() as conn:
        cart_items = conn.execute(text("""
            SELECT ci.Item_ID as id, i.Item_Name as name, i.Prod_Description as description,
                   ROUND(i.Prod_UnitPrice / s.Sponsor_PointConversion) AS point_cost,
                   ci.Quantity as quantity, i.Prod_Quantity as stock, '' as image_url
            FROM CART_ITEMS ci
            JOIN INVENTORY i ON ci.Item_ID = i.Item_ID
            JOIN SPONSORS s ON i.Sponsor_ID = s.Sponsor_ID
            WHERE ci.Driver_ID = :uid AND i.Sponsor_ID = :sid
        """), {"uid": session["user_id"], "sid": active_sponsor_id}).fetchall()
        total_cost = sum(i.point_cost * i.quantity for i in cart_items)
    return render_template("cart.html", nav_pages=NAV_PAGES, logged_in=is_logged_in(),
                           user=user, cart_items=cart_items, total_cost=total_cost)


# Add to cart
@main_bp.post("/cart/add/<int:item_id>")
def cart_add(item_id):
    r = require_role("Driver")
    if r: return r
    active_sponsor_id = session.get("active_sponsor_id")
    with engine.begin() as conn:
        existing = conn.execute(text(
            "SELECT Quantity FROM CART_ITEMS WHERE Driver_ID=:uid AND Item_ID=:iid AND Sponsor_ID=:sid"
        ), {"uid": session["user_id"], "iid": item_id, "sid": active_sponsor_id}).fetchone()
        if existing:
            conn.execute(text("UPDATE CART_ITEMS SET Quantity=Quantity+1 WHERE Driver_ID=:uid AND Item_ID=:iid AND Sponsor_ID=:sid"),
                         {"uid": session["user_id"], "iid": item_id, "sid": active_sponsor_id})
        else:
            conn.execute(text("INSERT INTO CART_ITEMS (Driver_ID, Item_ID, Quantity, Sponsor_ID) VALUES (:uid, :iid, 1, :sid)"),
                         {"uid": session["user_id"], "iid": item_id, "sid": active_sponsor_id})
    return redirect(url_for("main.storefront"))


# Update quantity
@main_bp.post("/cart/update/<int:item_id>")
def cart_update(item_id):
    r = require_role("Driver")
    if r: return r
    quantity = int(request.form.get("quantity", 1))
    active_sponsor_id = session.get("active_sponsor_id")
    with engine.begin() as conn:
        if quantity <= 0:
            conn.execute(text("DELETE FROM CART_ITEMS WHERE Driver_ID=:uid AND Item_ID=:iid AND Sponsor_ID=:sid"),
                         {"uid": session["user_id"], "iid": item_id, "sid": active_sponsor_id})
        else:
            conn.execute(text("UPDATE CART_ITEMS SET Quantity=:qty WHERE Driver_ID=:uid AND Item_ID=:iid AND Sponsor_ID=:sid"),
                         {"qty": quantity, "uid": session["user_id"], "iid": item_id, "sid": active_sponsor_id})
    return redirect(url_for("main.cart_page"))


# Remove item
@main_bp.post("/cart/remove/<int:item_id>")
def cart_remove(item_id):
    r = require_role("Driver")
    if r: return r
    active_sponsor_id = session.get("active_sponsor_id")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM CART_ITEMS WHERE Driver_ID=:uid AND Item_ID=:iid AND Sponsor_ID=:sid"),
                     {"uid": session["user_id"], "iid": item_id, "sid": active_sponsor_id})
    return redirect(url_for("main.cart_page"))


# Checkout
@main_bp.post("/cart/checkout")
def cart_checkout():
    r = require_role("Driver")
    if r: return r
    uid = session["user_id"]
    try:
        with engine.begin() as conn:
            # Get cart items with point costs
            cart_items = conn.execute(text("""
                SELECT ci.Item_ID, i.Item_Name, i.Prod_SKU, i.Prod_Description, i.Prod_Quantity,
                       ROUND(i.Prod_UnitPrice / s.Sponsor_PointConversion) AS point_cost,
                    ci.Quantity, ds.Sponsor_ID
                FROM CART_ITEMS ci
                JOIN INVENTORY i ON ci.Item_ID = i.Item_ID
                JOIN SPONSORS s ON i.Sponsor_ID = s.Sponsor_ID
                JOIN DRIVER_SPONSORS ds ON ds.Driver_ID = ci.Driver_ID AND ds.Sponsor_ID = s.Sponsor_ID
                WHERE ci.Driver_ID = :uid
            """), {"uid": uid}).fetchall()

            if not cart_items:
                flash("Your cart is empty.", "error")
                return redirect(url_for("main.cart_page"))

            total_cost = sum(i.point_cost * i.Quantity for i in cart_items)
            sponsor_id = cart_items[0].Sponsor_ID

            if any(i.Sponsor_ID != sponsor_id for i in cart_items):
                flash("All items in the cart must be from the same sponsor.", "error")
                return render_template("cart.html", nav_pages=NAV_PAGES, logged_in=is_logged_in(), 
                                   error="All items in the cart must be from the same sponsor.", cart_items=cart_items, total_cost=total_cost)

            # Check driver has enough points
            driver = conn.execute(text(
                "SELECT Driver_Points FROM DRIVER_SPONSORS WHERE Driver_ID = :uid AND Sponsor_ID = :sid"
            ), {"uid": uid, "sid": sponsor_id}).fetchone()

            if not driver:
                flash("Driver not found.", "error")
                return render_template("cart.html", nav_pages=NAV_PAGES, logged_in=is_logged_in(), 
                                       error="Driver not found.", cart_items=cart_items, total_cost=total_cost)

            if driver.Driver_Points < total_cost:
                flash("You do not have enough points to complete this purchase.", "error")
                return render_template("cart.html", nav_pages=NAV_PAGES, logged_in=is_logged_in(), 
                                   error="You do not have enough points to complete this purchase.", cart_items=cart_items, total_cost=total_cost)
        
            for item in cart_items:
                if item.Quantity > item.Prod_Quantity:
                    flash(f"Not enough stock for {item.Item_Name}. Available: {item.Prod_Quantity}", "error")
                    return render_template("cart.html", nav_pages=NAV_PAGES, logged_in=is_logged_in(), 
                                           error=f"Not enough stock for {item.Item_Name}. Available: {item.Prod_Quantity}", cart_items=cart_items, total_cost=total_cost)

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
                UPDATE DRIVER_SPONSORS SET Driver_Points = Driver_Points - :total WHERE Driver_ID = :uid AND Sponsor_ID = :sid
            """), {"total": total_cost, "uid": uid, "sid": sponsor_id})

            # Log the point transaction
            conn.execute(text("""
                INSERT INTO POINT_TRANSACTIONS (Driver_ID, Sponsor_ID, Actor_User_ID, Points_Changed, Reason, Transaction_Time)
                VALUES (:uid, :sid, :uuid, :pts, 'Order placed', :time)
            """), {"uid": uid, "sid": sponsor_id, "uuid": session["user_id"], "pts": -total_cost, "time": datetime.now()})

            # Clear the cart
            conn.execute(text(
                "DELETE FROM CART_ITEMS WHERE Driver_ID = :uid AND Sponsor_ID = :sid"
            ), {"uid": uid, "sid": sponsor_id})

        flash("Your order has been placed successfully!", "success")
        return redirect(url_for("main.driver_home"))
    except Exception as e:
        flash(f"An error occurred while processing your order: {str(e)}", "error")
        return redirect(url_for("main.cart_page"))


@main_bp.get("/driver/orders")
def driver_orders():
    r = require_role("Driver")
    if r:
        return r
    uid = session["user_id"]
    with engine.connect() as conn:
        orders = conn.execute(text("""
            SELECT o.Order_ID, o.Order_Status, o.Total_Points, o.OrderTime, s.Sponsor_Name, COUNT(li.Line_ID) AS Item_Count
            FROM ORDERS o
            JOIN SPONSORS s ON o.Sponsor_ID = s.Sponsor_ID
            LEFT JOIN LINE_ITEMS li ON o.Order_ID = li.Order_ID
            WHERE o.Driver_ID = :uid
            GROUP BY o.Order_ID, o.Order_Status, o.Total_Points, o.OrderTime, s.Sponsor_Name
            ORDER BY o.OrderTime DESC
        """), {"uid": uid}).fetchall()

        full_orders = []
        for row in orders:
            items = conn.execute(text("""
                SELECT Item_Name, Prod_SKU, Price_Points, Line_Quantity FROM LINE_ITEMS WHERE Order_ID = :oid
            """), {"oid": row.Order_ID}).fetchall()

            full_orders.append({
                "Order_ID": row.Order_ID,
                "Order_Status": row.Order_Status,
                "Total_Points": row.Total_Points,
                "OrderTime": row.OrderTime,
                "Sponsor_Name": row.Sponsor_Name,
                "Item_Count": row.Item_Count,
                "items": items
            })

    return render_template("driverOrders.html", nav_pages=NAV_PAGES, logged_in=is_logged_in(), orders=full_orders)

    
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

    appFilters = []
    multiFilters = []
    params = {}

    with engine.connect() as conn:

        if start_date:
            appFilters.append("App_Time >= :start_date")
            multiFilters.append("Application_Time >= :start_date")
            params["start_date"] = start_date

        if end_date:
            appFilters.append("App_Time <= :end_date")
            multiFilters.append("Application_Time <= :end_date")
            params["end_date"] = end_date

        if session["user_type"] == "Admin" and sponsor_filter:
            appFilters.append("App_Sponsor_ID = :sponsor_id")
            multiFilters.append("Sponsor_ID = :sponsor_id")
            params["sponsor_id"] = sponsor_filter

        app_filter_statement = " AND ".join(appFilters) if appFilters else "1=1"
        multi_filter_statement = " AND ".join(multiFilters) if multiFilters else "1=1"
                
        if session["user_type"] == "Sponsor":
            apps = conn.execute(text(f""" SELECT a.Application_ID, a.App_Status, 'new_app' AS app_type, a.App_FName AS first_name, a.App_LNAME AS last_name, s.Sponsor_Name, a.App_Time, a.App_Status 
                                     FROM APPLICATIONS a
                                     JOIN SPONSORS s ON a.App_Sponsor_ID = s.Sponsor_ID
                                     WHERE a.App_Sponsor_ID = :sid AND {app_filter_statement} 
                                     UNION ALL 
                                     SELECT dsa.Driver_Sponsor_App_ID, dsa.Application_Status as App_Status, 'existing_app' AS app_type, u.User_FName AS first_name, u.User_LNAME AS last_name, s.Sponsor_Name, dsa.Application_Time, dsa.Application_Status 
                                     FROM DRIVER_SPONSOR_APPLICATIONS dsa
                                     JOIN USERS u ON dsa.Driver_ID = u.User_ID
                                     JOIN SPONSORS s ON dsa.Sponsor_ID = s.Sponsor_ID WHERE dsa.Sponsor_ID = :sid AND {multi_filter_statement} 
                                     """),
                                params | {"sid": session["sponsor_id"]}).fetchall()
        else:
            apps = conn.execute(text(f""" SELECT a.Application_ID, a.App_Status, 'new_app' AS app_type, a.App_FName AS first_name, a.App_LNAME AS last_name, s.Sponsor_Name, a.App_Time as app_time, a.App_Status 
                                     FROM APPLICATIONS a
                                     JOIN SPONSORS s ON a.App_Sponsor_ID = s.Sponsor_ID
                                     WHERE {app_filter_statement}
                                     UNION ALL 
                                     SELECT dsa.Driver_Sponsor_App_ID, dsa.Application_Status AS App_Status, 'existing_app' AS app_type, u.User_FName AS first_name, u.User_LNAME AS last_name, s.Sponsor_Name, dsa.Application_Time AS app_time
                                     FROM DRIVER_SPONSOR_APPLICATIONS dsa
                                     JOIN USERS u ON dsa.Driver_ID = u.User_ID
                                     JOIN SPONSORS s ON dsa.Sponsor_ID = s.Sponsor_ID WHERE {multi_filter_statement}
                                    ORDER BY app_time DESC"""),
                                params ).fetchall()
    return render_template("applications_list.html", apps=apps, nav_pages = NAV_PAGES, logged_in=is_logged_in())

@main_bp.get("/applications/<string:app_type>/<int:app_id>")
def application_details(app_type, app_id):
    r = require_role("Sponsor")
    if r:
        r2 = require_role("Admin")
        if r2:
            return r2
    with engine.connect() as conn:
        if app_type == "new_app":
            app = conn.execute(text(""" SELECT Application_ID, App_Sponsor_ID, App_Username,App_Status, App_FName AS first_name, App_LNAME AS last_name, App_Email, App_Phone_Num,
                                    License_Num, App_Time, Denial_Reason FROM APPLICATIONS
                                    WHERE Application_ID = :aid"""),
                                    {"aid": app_id}).fetchone()
        elif app_type == "existing_app":
            app = conn.execute(text(""" SELECT dsa.Driver_Sponsor_App_ID, dsa.Driver_ID, dsa.Sponsor_ID, dsa.Application_Status, dsa.Application_Time, dsa.Denial_Reason, u.User_FName AS first_name, u.User_LName AS last_name 
                                    FROM DRIVER_SPONSOR_APPLICATIONS dsa JOIN USERS u ON dsa.Driver_ID = u.User_ID WHERE Driver_Sponsor_App_ID = :aid"""), {"aid": app_id}).fetchone()
    if not app:
        return "Application not found", 404

    if session["user_type"] == "Sponsor":
        app_sponsor_id = app.App_Sponsor_ID if app_type == "new_app" else app.Sponsor_ID
        if int(app_sponsor_id) != int(session["sponsor_id"]):
            return "Forbidden", 403

    return render_template(
        "application_detail.html",
        app=app, app_type=app_type, nav_pages=NAV_PAGES, logged_in=is_logged_in())

@main_bp.post("/applications/<string:app_type>/<int:app_id>/evaluate")
def evaluate_applications(app_type, app_id):
    r = require_role("Sponsor")
    if r:
        r2 = require_role("Admin")
        if r2:
            return r2
    decision = request.form.get("decision")
    reason = request.form.get("reason")

    with engine.begin() as conn:
        if app_type == "new_app":
            app = conn.execute(text(""" SELECT App_Sponsor_ID FROM APPLICATIONS WHERE Application_ID = :aid"""), 
                            {"aid": app_id}).fetchone()
            if not app:
                return "Application not found", 404
            if session["user_type"] == "Sponsor":
                app_sponsor_id = app.App_Sponsor_ID if app_type == "new_app" else app.Sponsor_ID
                if int(app_sponsor_id) != int(session["sponsor_id"]):
                    return "Forbidden", 403
        
            if decision == "Denied" and not reason:
                return render_template(
                    "application_detail.html",
                    app=app, app_type="new_app", nav_pages=NAV_PAGES, logged_in=is_logged_in(),
                    error="Reason for denial is required when denying an application."
                )

            conn.execute(text("""UPDATE APPLICATIONS SET App_Status = :status, Denial_Reason = :reason WHERE Application_ID = :aid"""), {"status": decision, "reason": reason if decision == "Denied" else None, "aid": app_id})
            if decision == "Approved":
                conn.execute(text("""DELETE FROM APPLICATIONS WHERE Application_ID = :aid"""), {"aid": app_id})
        elif app_type == "existing_app":
            app = conn.execute(text(""" SELECT dsa.Driver_Sponsor_App_ID, dsa.Driver_ID, dsa.Sponsor_ID, dsa.Application_Status, dsa.Application_Time, dsa.Denial_Reason, u.User_FName, u.User_LName 
                                    FROM DRIVER_SPONSOR_APPLICATIONS dsa JOIN USERS u ON dsa.Driver_ID = u.User_ID WHERE Driver_Sponsor_App_ID = :aid"""), {"aid": app_id}).fetchone()
            if not app:
                return "Application not found", 404
            if session["user_type"] == "Sponsor" and int(app.Sponsor_ID) != int(session["sponsor_id"]):
                return "Forbidden", 403
            if decision == "Denied" and not reason:
                return render_template(
                    "application_detail.html",
                    app=app, app_type="existing_app", nav_pages=NAV_PAGES, logged_in=is_logged_in(),
                    error="Reason for denial is required when denying an application."
                ), 400
            if app.Application_Status != "Pending":
                return "This application has already been evaluated.", 400
            conn.execute(text("""UPDATE DRIVER_SPONSOR_APPLICATIONS SET Application_Status = :status, Denial_Reason = :reason WHERE Driver_Sponsor_App_ID = :aid"""), {"status": decision, "reason": reason if decision == "Denied" else None, "aid": app_id})
            if decision == "Approved":
                conn.execute(text("""DELETE FROM DRIVER_SPONSOR_APPLICATIONS WHERE Driver_Sponsor_App_ID = :aid"""), {"aid": app_id})
    return redirect(url_for("main.applications_list"))


@main_bp.get("/driver/multi-applications/apply")
def apply_multi_application_page():
    r = require_role("Driver")
    if r:
        return r
    active_sponsor_id = session.get("active_sponsor_id")
    with engine.connect() as conn:
        sponsors = conn.execute(text("""
            SELECT s.Sponsor_ID, s.Sponsor_Name FROM SPONSORS s WHERE s.Sponsor_ID NOT IN (
                SELECT Sponsor_ID FROM DRIVER_SPONSOR_APPLICATIONS WHERE Driver_ID = :did AND Application_Status = 'Pending') AND s.Sponsor_ID NOT IN (
                SELECT Sponsor_ID FROM DRIVER_SPONSORS WHERE Driver_ID = :did AND Is_Active = 1) ORDER BY s.Sponsor_Name
        """), {"did": session["user_id"]}).fetchall()
        existing_applications = conn.execute(text("""
            SELECT dsa.Sponsor_ID, s.Sponsor_Name FROM DRIVER_SPONSOR_APPLICATIONS dsa JOIN SPONSORS s ON dsa.Sponsor_ID = s.Sponsor_ID WHERE dsa.Driver_ID = :did AND dsa.Application_Status = 'Pending'
        """), {"did": session["user_id"]}).fetchall()
    return render_template("driver_multi_applications.html", sponsors=sponsors, existing_applications=existing_applications, active_sponsor_id=active_sponsor_id, nav_pages=NAV_PAGES, logged_in=is_logged_in())

@main_bp.post("/driver/multi-applications/apply")
def apply_multi_application():
    r = require_role("Driver")
    if r:
        return r
    sponsor_id = request.form.get("sponsor_id")
    if not sponsor_id:
        return "Sponsor ID is required", 400
    
    with engine.begin() as conn:
        existing_app = conn.execute(text("""
            SELECT Driver_Sponsor_App_ID FROM DRIVER_SPONSOR_APPLICATIONS 
            WHERE Driver_ID = :did AND Sponsor_ID = :sid
        """), {"did": session["user_id"], "sid": sponsor_id}).fetchone()
        if existing_app:
            flash("You have already applied to this sponsor.", "error")
            return redirect(url_for("main.apply_multi_application_page"))
        existing_user = conn.execute(text("""
            SELECT Driver_ID FROM DRIVER_SPONSORS WHERE Driver_ID = :did AND Sponsor_ID = :sid
        """), {"did": session["user_id"], "sid": sponsor_id}).fetchone()
        if existing_user:
            flash("You are already a driver for this sponsor.", "error")
            return redirect(url_for("main.apply_multi_application_page"))
        
        conn.execute(text("""
            INSERT INTO DRIVER_SPONSOR_APPLICATIONS (Driver_ID, Sponsor_ID, Application_Status, Application_Time)
            VALUES (:did, :sid, 'Pending', :time)
        """), {"did": session["user_id"], "sid": sponsor_id, "time": datetime.now()})
    
    flash("Your application has been submitted.", "success")
    return redirect(url_for("main.apply_multi_application_page"))





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
            SELECT Driver_ID FROM DRIVER_SPONSORS WHERE Driver_ID = :did AND Sponsor_ID = :sid
        """), {"did": driver_id, "sid": session["sponsor_id"]}).fetchone()
        if not driver:
            return "Driver not found or not associated with your sponsor account", 404
        
        conn.execute(text("""
            UPDATE DRIVER_SPONSORS SET Is_Active = FALSE WHERE Driver_ID = :did AND Sponsor_ID = :sid
        """), {"did": driver_id, "sid": session["sponsor_id"]})
    return redirect(url_for("main.sponsor_home"))

@main_bp.post("/driver/switch-sponsor")
def switch_sponsor():
    r = require_role("Driver")
    if r:
        return r
    new_sponsor_id = request.form.get("sponsor_id", type=int)
    if not new_sponsor_id:
        return "Sponsor ID is required", 400
    
    with engine.begin() as conn:
        sponsor = conn.execute(text("""
            SELECT ds.Sponsor_ID, s.Sponsor_Name FROM DRIVER_SPONSORS ds JOIN SPONSORS s ON ds.Sponsor_ID = s.Sponsor_ID WHERE ds.Driver_ID = :driver_id AND ds.Sponsor_ID = :sid AND ds.Is_Active = TRUE
        """), {"driver_id": session["user_id"], "sid": new_sponsor_id}).fetchone()
        if not sponsor:
            return "Sponsor not found", 404
        
    session["active_sponsor_id"] = sponsor.Sponsor_ID
    session["active_sponsor_name"] = sponsor.Sponsor_Name
    
    flash(f"Your sponsor has been switched successfully to {sponsor.Sponsor_Name}.", "success")
    return redirect(url_for("main.driver_home"))