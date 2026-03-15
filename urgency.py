from db import get_connection
from datetime import date

def calculate_urgency():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM ngo_requests WHERE status='active'")
    requests = cursor.fetchall()

    for req in requests:
        quantity = req['quantity_needed']
        days_pending = (date.today() - req['date_posted'].date()).days

        cursor.execute("SELECT category FROM users WHERE id=%s", (req['ngo_id'],))
        category = cursor.fetchone()['category']
        

        weights = {
            "Disaster Relief": 3,
            "Orphanage": 2,
            "Shelter": 1,
            "General NGO": 1
        }

        category_weight = weights.get(category, 1)

        urgency_score = (quantity / 10) + (days_pending * 0.5) + category_weight

        if urgency_score >= 9:
            urgency_level = 5
        elif urgency_score >= 5:
            urgency_level = 3
        else:
            urgency_level = 1

        cursor.execute("""
            UPDATE ngo_requests
            SET urgency_score=%s, urgency_level=%s
            WHERE id=%s
        """, (urgency_score, urgency_level, req['id']))

    conn.commit()
    conn.close()

    print("Urgency Updated Successfully")
