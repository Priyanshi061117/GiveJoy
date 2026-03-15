from flask import Flask, render_template, request, redirect, session
from db import get_connection
from urgency import calculate_urgency
import math
from datetime import date

app = Flask(__name__)
app.secret_key = "givejoy_secret"

conn = get_connection()
cursor = conn.cursor(dictionary=True)

#DISTANCE CALCULATOR 
@app.route('/')
def home():
    return redirect('/login')

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
    if 'user_id' not in session:
        return redirect('/login')

    if session['role'] == 'donor':
        return render_template('donor_dashboard.html', name=session['name'])

    elif session['role'] == 'ngo':
        return render_template('ngo_dashboard.html', name=session['name'])

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


        conn = get_connection()
        cursor = conn.cursor()



        cursor.execute("""
            INSERT INTO donations (donor_id, item_name, quantity, date_posted,status,category)
            VALUES (%s, %s, %s,'2026-03-12', 'pending',%s)
        """,(session['user_id'], item_name, quantity,category))

        conn.commit()
        conn.close()

        return redirect('/dashboard')

    return render_template("donate_item.html")


# LOGOUT 
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


if __name__ == "__main__":
    app.run(debug=True)