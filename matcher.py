from db import get_connection
from datetime import date

def match_donations():

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # get pending donations
    cursor.execute("SELECT * FROM donations WHERE status='pending'")
    donations = cursor.fetchall()

    for d in donations:

        # find matching NGO
        cursor.execute("""
        SELECT * FROM ngo_requests
        WHERE item_required = %s
        AND status = 'active'
        ORDER BY urgency_score DESC
        """, (d['item_name'],))

        ngo_results = cursor.fetchall()

        if ngo_results:
            request = ngo_results[0]
            ngo_id = request['ngo_id']

            #  STEP: GET DELIVERY PARTNER
            cursor.execute("""
            SELECT * FROM delivery_partners
            WHERE availability = 'available'
            LIMIT 1
            """)

            partner = cursor.fetchone()

            if partner:
                delivery_partner_id = partner['id']
                date1=date.today()

                # insert assignment
                cursor.execute("""
                INSERT INTO assignments 
                (donation_id, ngo_id, delivery_partner_id, assignment_date, status)
                VALUES (%s, %s, %s, %s, 'assigned')
                """, (d['id'], ngo_id, delivery_partner_id,date1))

                # update donation
                cursor.execute("""
                UPDATE donations
                SET status='assigned'
                WHERE id=%s
                """, (d['id'],))

                # update delivery partner → now busy
                cursor.execute("""
                UPDATE delivery_partners
                SET availability='busy'
                WHERE id=%s
                """, (delivery_partner_id,))

    conn.commit()
    conn.close()