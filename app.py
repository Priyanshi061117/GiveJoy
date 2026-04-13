from flask import Flask, render_template, request, redirect, session
from db import get_connection
from urgency import calculate_urgency
import math
from datetime import datetime
from matcher import match_donations
app = Flask(__name__)
app.secret_key = "givejoy_secret"



#DISTANCE CALCULATOR 
@app.route('/')
def home():
    return render_template('index.html')

def calculate_distance(lat1, lon1, lat2, lon2):

    R = 6371  

    lat1 = math.radians(float(lat1))
    lon1 = math.radians(float(lon1))
    lat2 = math.radians(float(lat2))
    lon2 = math.radians(float(lon2))

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    distance = R * c

    return round(distance, 2)


#SIGNUP
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        latitude = request.form['latitude']
        longitude = request.form['longitude']
        category = request.form.get('category')

        if role == "donor":
            category = None

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO users (name, email, password, role, latitude, longitude, category)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (name, email, password, role, latitude, longitude, category))

        conn.commit()
        conn.close()

        return redirect('/login')

    return render_template('signup.html')


#LOGIN
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT * FROM users WHERE email=%s AND password=%s
        """, (email, password))

        user = cursor.fetchone()
        conn.close()

        if user:
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['name'] = user['name']
            return redirect('/dashboard')
        else:
            return "Invalid credentials"

    return render_template('login.html')


#DASHBOARD 
@app.route('/dashboard')
def dashboard():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    if 'user_id' not in session:
        return redirect('/login')

    if session['role'] == 'donor':
        return render_template('donor_dashboard.html', name=session['name'])

    elif session['role'] == 'ngo':
        cursor.execute("""
            SELECT pf.*
            FROM prepared_food pf
            JOIN prepared_food_notifications n 
                ON pf.id = n.food_id
            WHERE n.ngo_id = %s 
            AND n.status = 'pending'
            AND pf.status = 'pending'
            LIMIT 1
        """, (session['user_id'],))

        food = cursor.fetchone()
        conn.close()

        return render_template('ngo_dashboard.html', name=session['name'], food=food)

    else:
        return "Admin Panel"

# NGO POST REQUEST 
@app.route('/post_request', methods=['GET', 'POST'])
def post_request():

    if 'user_id' not in session or session['role'] != 'ngo':
        return redirect('/login')

    if request.method == 'POST':
        item_name = request.form['item_required']
        quantity = request.form['quantity']

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO ngo_requests (ngo_id, item_required, quantity_needed)
            VALUES (%s, %s, %s)
        """, (session['user_id'], item_name,quantity))

        conn.commit()
        conn.close()

        calculate_urgency()

        return redirect('/dashboard')

    return render_template('post_requests.html')

#NGO SEE PAST REQUESTS
@app.route('/my_requests')
def my_requests():

    if 'user_id' not in session or session['role'] != 'ngo':
        return redirect('/login')
    
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)


    cursor.execute("""
        SELECT id, item_required, quantity_needed, urgency_score, status, date_posted
        FROM ngo_requests
        WHERE ngo_id = %s
        ORDER BY date_posted DESC
    """, (session['user_id'],))

    requests = cursor.fetchall()

    conn.close()

    return render_template("my_requests.html", requests=requests)

#DONOR VIEW NGO REQUESTS
@app.route('/view_requests')
def view_requests():

    if 'user_id' not in session or session['role'] != 'donor':
        return redirect('/login')

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    
    cursor.execute("SELECT latitude, longitude FROM users WHERE id=%s", (session['user_id'],))
    donor = cursor.fetchone()

    donor_lat = donor['latitude']
    donor_lon = donor['longitude']

    cursor.execute("""
        SELECT ngo_requests.*, users.name, users.latitude, users.longitude
        FROM ngo_requests
        JOIN users ON ngo_requests.ngo_id = users.id
        WHERE ngo_requests.status='active'
    """)

    requests = cursor.fetchall()

    results = []

    for r in requests:

        distance = calculate_distance(
            donor_lat,
            donor_lon,
            r['latitude'],
            r['longitude']
        )

        r['distance'] = distance
        results.append(r)

    results = sorted(results, key=lambda x: (-x['urgency_score'], x['distance']))

    conn.close()

    return render_template("view_requests.html", requests=results)


#DONATE ITEMS
@app.route('/donate_item', methods=['GET','POST'])
def donate_item():

    if 'user_id' not in session or session['role'] != 'donor':
        return redirect('/login')

    if request.method == 'POST':

        category = request.form['category']
        item_name = request.form['item_name']
        quantity = request.form['quantity']
        expiry_date = request.form.get('expiry_date')

        # 🔥 VALIDATION FOR PACKAGED FOOD
        if category == "Packaged Food":

            if not expiry_date:
                return "Please provide expiry date for packaged food!"

            expiry = datetime.strptime(expiry_date, "%Y-%m-%d").date()
            today = datetime.today().date()

            if expiry <= today:
                return render_template("donate_item.html", error="Cannot donate expired food!")

        else:
            expiry_date = None

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO donations 
            (donor_id, item_name, quantity, date_posted, status, category, expiry_date)
            VALUES (%s, %s, %s, CURDATE(), 'pending', %s, %s)
        """, (session['user_id'], item_name, quantity, category, expiry_date))

        conn.commit()
        conn.close()

        match_donations()

        return redirect('/dashboard')

    return render_template("donate_item.html")



#INCOMING DONATIONS
@app.route('/incoming_donations')
def incoming_donations():

    if 'user_id' not in session or session['role'] != 'ngo':
        return redirect('/login')
    
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # 🔹 NORMAL DONATIONS
    cursor.execute("""
    SELECT donations.item_name, donations.quantity, donations.status, users.name AS donor_name
    FROM assignments
    JOIN donations ON assignments.donation_id = donations.id
    JOIN users ON donations.donor_id = users.id
    WHERE assignments.ngo_id = %s
    """, (session['user_id'],))

    normal_data = cursor.fetchall()

    # 🔹 PREPARED FOOD
    cursor.execute("""
    SELECT pf.item_name, pf.quantity, pf.delivery_status AS status,
           u.name AS donor_name
    FROM prepared_food pf
    JOIN users u ON pf.donor_id = u.id
    WHERE pf.accepted_by = %s
    """, (session['user_id'],))

    food_data = cursor.fetchall()

    #  COMBINE BOTH
    data = normal_data + food_data

    conn.close()

    return render_template("incoming_donations.html", data=data)


#TRACK DONATIONS
@app.route('/my_donations')
def my_donations():

    if 'user_id' not in session or session['role'] != 'donor':
        return redirect('/login')

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # 🔹 NORMAL DONATIONS
    cursor.execute("""
    SELECT donations.item_name, donations.quantity, donations.status, users.name AS ngo_name
    FROM donations
    LEFT JOIN assignments ON donations.id = assignments.donation_id
    LEFT JOIN users ON assignments.ngo_id = users.id
    WHERE donations.donor_id = %s
    """, (session['user_id'],))

    normal_data = cursor.fetchall()

    # 🔹 PREPARED FOOD
    cursor.execute("""
    SELECT pf.item_name, pf.quantity, pf.delivery_status AS status,
           u.name AS ngo_name
    FROM prepared_food pf
    LEFT JOIN users u ON pf.accepted_by = u.id
    WHERE pf.donor_id = %s
    """, (session['user_id'],))

    food_data = cursor.fetchall()

    # 🔥 COMBINE
    data = normal_data + food_data

    conn.close()

    return render_template("my_donations.html", data=data)

#FUNC PREPFOOD
def expire_prepared_food():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE prepared_food
        SET status='expired'
        WHERE status='pending'
        AND TIMESTAMPDIFF(MINUTE, created_at, NOW()) > 10
    """)

    conn.commit()
    conn.close()

#PREPARED FOOD
@app.route('/prep_food', methods=['GET', 'POST'])
def donate_prepared_food():

    if 'user_id' not in session or session['role'] != 'donor':
        return redirect('/login')

    if request.method == 'POST':

        item_name = request.form['item_name']
        quantity = request.form['quantity']
        prepared_time = request.form['prepared_time']
        notes = request.form.get('notes')

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Get donor location
        cursor.execute("SELECT latitude, longitude FROM users WHERE id=%s", (session['user_id'],))
        donor = cursor.fetchone()

        donor_lat = donor['latitude']
        donor_lon = donor['longitude']

        # Find nearby NGOs
        cursor.execute("SELECT id, latitude, longitude FROM users WHERE role='ngo'")
        ngos = cursor.fetchall()

        nearby_ngos = []

        for ngo in ngos:
            distance = calculate_distance(donor_lat, donor_lon, ngo['latitude'], ngo['longitude'])
            if distance <= 10:
                nearby_ngos.append(ngo['id'])

        if not nearby_ngos:
            return render_template("prep_food.html", error="No NGOs within 10 km!")

        # Insert donation
        # Insert food
        cursor.execute("""
        INSERT INTO prepared_food (donor_id, item_name, quantity, prepared_time, notes, status)
        VALUES (%s, %s, %s, %s, %s, 'pending')
        """, (session['user_id'], item_name, quantity, prepared_time, notes))

        food_id = cursor.lastrowid

        # Insert notifications for nearby NGOs
        for ngo_id in nearby_ngos:
            cursor.execute("""
                INSERT INTO prepared_food_notifications (food_id, ngo_id)
                VALUES (%s, %s)
            """, (food_id, ngo_id))

        conn.commit()
        conn.close()

        return render_template("prep_food.html", success="Nearby NGOs notified! First to accept will get it.")

    return render_template("prep_food.html")

#DONOR STATUS CHECK
@app.route('/my_prepared_food')
def my_prepared_food():

    if 'user_id' not in session:
        return redirect('/login')
    
    expire_prepared_food()

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT pf.*, users.name AS ngo_name
        FROM prepared_food pf
        LEFT JOIN users ON pf.accepted_by = users.id
        WHERE pf.donor_id = %s
    """, (session['user_id'],))

    data = cursor.fetchall()

    conn.close()

    return render_template("prep_food.html", data=data)


#SEEALERTS-NGO
@app.route('/prepared_food_requests')
def prepared_food_requests():

    if 'user_id' not in session or session['role'] != 'ngo':
        return redirect('/login')
    
    expire_prepared_food()

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT * FROM prepared_food
        WHERE status='pending'
        AND TIMESTAMPDIFF(MINUTE, created_at, NOW()) <= 10
    """)

    data = cursor.fetchall()

    conn.close()

    return render_template("prep_food.html", data=data)

#ACCEPTBUTTON-NGO
@app.route('/accept_food/<int:id>')
def accept_food(id):

    if 'user_id' not in session or session['role'] != 'ngo':
        return redirect('/login')

    conn = get_connection()
    cursor = conn.cursor()

    # accept only if pending
    cursor.execute("""
        UPDATE prepared_food
        SET status='accepted', accepted_by=%s
        WHERE id=%s AND status='pending'
    """, (session['user_id'], id))

    if cursor.rowcount == 1:

        # update notifications
        cursor.execute("""
            UPDATE prepared_food_notifications
            SET status='accepted'
            WHERE food_id=%s
        """, (id,))

        conn.commit()
        conn.close()

        # 🔥 assign delivery AFTER accept
        assign_delivery_partner(id, session['user_id'])

    else:
        cursor.execute("""
            UPDATE prepared_food_notifications
            SET status='expired'
            WHERE food_id=%s
        """, (id,))
        conn.commit()
        conn.close()

    return redirect('/dashboard')


@app.route('/decline_food/<int:id>')
def decline_food(id):

    if 'user_id' not in session or session['role'] != 'ngo':
        return redirect('/login')

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE prepared_food_notifications
        SET status='declined'
        WHERE food_id=%s AND ngo_id=%s
    """, (id, session['user_id']))

    conn.commit()
    conn.close()

    return redirect('/dashboard')

def assign_delivery_partner(food_id, ngo_id):

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # NGO location
    cursor.execute("SELECT latitude, longitude FROM users WHERE id=%s", (ngo_id,))
    ngo = cursor.fetchone()

    ngo_lat = ngo['latitude']
    ngo_lon = ngo['longitude']

    # available partners
    cursor.execute("""
        SELECT * FROM delivery_partners
        WHERE availability = 'available'
    """)
    partners = cursor.fetchall()

    best_partner = None
    min_distance = 999999

    for p in partners:
        dist = calculate_distance(ngo_lat, ngo_lon, p['latitude'], p['longitude'])
        if dist < min_distance:
            min_distance = dist
            best_partner = p

    if best_partner:

        # ✅ UPDATE PREPARED FOOD
        cursor.execute("""
            UPDATE prepared_food
            SET delivery_partner_id=%s, delivery_status='assigned'
            WHERE id=%s
        """, (best_partner['id'], food_id))

        # ✅ INSERT INTO ASSIGNMENTS TABLE 🔥
        cursor.execute("""
            INSERT INTO assignments
            (donation_id, ngo_id, delivery_partner_id, assignment_date, status)
            VALUES (%s, %s, %s, CURDATE(), 'assigned')
        """, (food_id, ngo_id, best_partner['id']))

        # mark partner busy
        cursor.execute("""
            UPDATE delivery_partners
            SET availability='busy'
            WHERE id=%s
        """, (best_partner['id'],))

    conn.commit()
    conn.close()



import os

UPLOAD_FOLDER = 'static/uploads/products'

@app.route('/add_product', methods=['GET', 'POST'])
def add_product():

    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = request.form['price']
        stock = request.form['stock']
        ngo_id = session['user_id']

        image = request.files['image']

        import os
        filename = image.filename
        filepath = os.path.join('static/images/', filename)
        image.save(filepath)

        db_path = 'static/images/' + filename

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO products (ngo_id, product_name, price, stock, description, image)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (ngo_id, name, price, stock, description, db_path))

        conn.commit()
        conn.close()

        return redirect('/dashboard')

    # THIS FIXES YOUR ERROR
    return render_template('add_product.html')


@app.route('/browse_products')
def browse_products():

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT p.*, u.name AS ngo_name
        FROM products p
        JOIN users u ON p.ngo_id = u.id
        WHERE u.role = 'ngo' AND p.stock > 0
    """)
    
    products = cursor.fetchall()
    conn.commit()
    conn.close()
    return render_template('browse_products.html', products=products)

@app.route('/buy_now/<int:product_id>')
def buy_now(product_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
    product = cursor.fetchone()
    conn.commit()
    conn.close()

    return render_template('buy_now.html', product=product)

@app.route('/place_order', methods=['POST'])
def place_order():
    donor_id = session['user_id']
    product_id = request.form['product_id']
    quantity = int(request.form['quantity'])

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Get product
    cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
    product = cursor.fetchone()

    total = product['price'] * quantity

    # Create order
    cursor.execute("""
        INSERT INTO orders (donor_id, ngo_id, total_amount, payment_method)
        VALUES (%s, %s, %s, 'COD')
    """, (donor_id, product['ngo_id'], total))

    order_id = cursor.lastrowid

    # Insert item
    cursor.execute("""
        INSERT INTO order_items (order_id, product_id, quantity, price)
        VALUES (%s, %s, %s, %s)
    """, (order_id, product_id, quantity, product['price']))

    # Reduce stock
    cursor.execute("""
        UPDATE products
        SET stock = stock - %s
        WHERE id = %s
    """, (quantity, product_id))

    # Assign delivery partner (reuse your logic)
    assign_delivery_partner_order(order_id, product['ngo_id'])



    conn.commit()
    conn.close()

    return redirect('/order_success')

@app.route('/order_success')
def order_success():
    return render_template('order_success.html')

def assign_delivery_partner_order(order_id, ngo_id):

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # NGO location
    cursor.execute("SELECT latitude, longitude FROM users WHERE id=%s", (ngo_id,))
    ngo = cursor.fetchone()

    ngo_lat = ngo['latitude']
    ngo_lon = ngo['longitude']

    # available partners
    cursor.execute("""
        SELECT * FROM delivery_partners
        WHERE availability = 'available'
    """)
    partners = cursor.fetchall()

    best_partner = None
    min_distance = 999999

    for p in partners:
        dist = calculate_distance(ngo_lat, ngo_lon, p['latitude'], p['longitude'])
        if dist < min_distance:
            min_distance = dist
            best_partner = p

    if best_partner:

        # Insert into assignments (ORDER BASED)
        cursor.execute("""
            INSERT INTO assignments
            (order_id, ngo_id, delivery_partner_id, assignment_date, status)
            VALUES (%s, %s, %s, NOW(), 'assigned')
        """, (order_id, ngo_id, best_partner['id']))

        # mark partner busy
        cursor.execute("""
            UPDATE delivery_partners
            SET availability='busy'
            WHERE id=%s
        """, (best_partner['id'],))

    conn.commit()
    conn.close()

@app.route('/my_products')
def my_products():

    ngo_id = session['user_id']
    print("ROUTE HIT")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products WHERE ngo_id = %s", (ngo_id,))
    products = cursor.fetchall()

    print("Products:", products)  # DEBUG
    conn.close()

    return render_template('my_products.html', products=products)


@app.route('/ngo_orders')
def ngo_orders():
    ngo_id = session['user_id']
    print("ROUTE HIT")
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT o.id, o.status, o.total_amount,
               oi.quantity,
               p.product_name AS product_name
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        JOIN products p ON oi.product_id = p.id
        WHERE p.ngo_id = %s
    """, (ngo_id,))

    orders = cursor.fetchall()
    conn.close()

    print("NGO Orders:", orders)  # DEBUG

    return render_template('ngo_orders.html', orders=orders)

@app.route('/my_orders')
def my_orders():
    donor_id = session['user_id']
    print("ROUTE HIT")
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT o.id, o.status, o.total_amount,
               p.product_name AS product_name,
               oi.quantity
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        JOIN products p ON oi.product_id = p.id
        WHERE o.donor_id = %s
    """, (donor_id,))

    orders = cursor.fetchall()

    print("Donor Orders:", orders)  # DEBUG
    conn.close()

    return render_template('my_orders.html', orders=orders)

# LOGOUT 
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


if __name__ == "__main__":
    app.run(debug=True)