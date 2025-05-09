import os
import pg8000
import ssl
import certifi
import json
from google.cloud.sql.connector import Connector
import psycopg2
import psycopg2.extras
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define connection parameters
PROJECT_ID = "AsendHealthLogin"
INSTANCE_CONNECTION_NAME = "asendhealthlogin:us-central1:asendhealth-cloud-sql"  # Format: project-id:region:instance-id
DB_USER = "postgres"
DB_PASS = "2Asendhealth!"
DB_NAME = "postgres"
ssl_context = ssl.create_default_context(cafile=certifi.where())


# Initialize Cloud SQL Connector
connector = Connector()

# Creates a connection to the Postgres database
def get_connection():
   """
   Establishes a connection to the PostgreSQL database on Google Cloud SQL.
   """
   conn = connector.connect(
   #conn = psycopg2.connect(
    INSTANCE_CONNECTION_NAME,
       "pg8000",
       user=DB_USER,
       password=DB_PASS,
       db=DB_NAME,
       #ssl=False
   )
   return conn

#####################
# LOCATION FUNCTIONS
#####################

# CREATE: Insert a new location record
def create_location(location_name, address, location_type, phone_number=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = """
            INSERT INTO locations (
                location_id, location_name, address, location_type, phone_number
            )
            VALUES (uuid_generate_v4(), %s, %s, %s, %s)
            RETURNING location_id;
        """
        cur.execute(query, (location_name, address, location_type, phone_number))
        new_id = cur.fetchone()[0]
        conn.commit()
        logging.info(f"Created location with id: {new_id}")
        return new_id
    except Exception as e:
        logging.error(f"An error occurred while creating location: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()

# READ: Retrieve a location record by id
def get_location_by_id(location_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = "SELECT * FROM locations WHERE location_id = %s;"
        cur.execute(query, (location_id,))
        location = cur.fetchone()
        logging.info(f"Fetched location: {location}")
        return location
    except Exception as e:
        logging.error(f"An error occurred while fetching location: {e}")
        return None
    finally:
        cur.close()
        conn.close()

# READ: Retrieve all locations, optionally filter by type
def get_locations(location_type=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        if location_type:
            query = "SELECT * FROM locations WHERE location_type = %s ORDER BY location_name;"
            cur.execute(query, (location_type,))
        else:
            query = "SELECT * FROM locations ORDER BY location_name;"
            cur.execute(query)
        locations = cur.fetchall()
        return locations
    except Exception as e:
        logging.error(f"An error occurred while fetching locations: {e}")
        return []
    finally:
        cur.close()
        conn.close()

# UPDATE: Update a location's record
def update_location(location_id, location_name=None, address=None, location_type=None, phone_number=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        fields = []
        values = []
        if location_name is not None: fields.append("location_name = %s"); values.append(location_name)
        if address is not None: fields.append("address = %s"); values.append(address)
        if location_type is not None: fields.append("location_type = %s"); values.append(location_type)
        if phone_number is not None: fields.append("phone_number = %s"); values.append(phone_number)
        if not fields: logging.warning("No fields provided to update location."); return False

        values.append(location_id)
        query = f"UPDATE locations SET {', '.join(fields)} WHERE location_id = %s;"
        cur.execute(query, values)
        conn.commit()
        logging.info(f"Updated location with id: {location_id}")
        return True
    except Exception as e:
        logging.error(f"An error occurred while updating location: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

# DELETE: Remove a location record
def delete_location(location_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Consider implications: deleting a location might orphan doctor_locations or appointments if ON DELETE CASCADE isn't set or desired
        query = "DELETE FROM locations WHERE location_id = %s;"
        cur.execute(query, (location_id,))
        conn.commit()
        logging.info(f"Deleted location with id: {location_id}")
        return True
    except Exception as e:
        logging.error(f"An error occurred while deleting location: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

#####################
# HOSPITAL FUNCTIONS (If still needed for metadata)
#####################
# Existing hospital CRUD functions (create_hospital, get_hospital_by_id, etc.)
# can remain largely unchanged if the `hospitals` table is kept for specific
# hospital metadata not present in the `locations` table.
# However, their relevance decreases if `locations` holds the primary address info.
# For brevity, I'm omitting the full repeat of those functions here,
# assuming they might be simplified or removed depending on final design choice.
# def create_hospital(...)
# def get_hospital_by_id(...)
# def get_hospitals(...)
# def update_hospital(...)
# def delete_hospital(...)


#####################
# DOCTOR FUNCTIONS
#####################

# AUTHENTICATE: Validate a doctor's username and password
#def validate_user(userType, username, password):
def validate_doctor(username, password):
    # IMPORTANT: Implement proper password hashing and verification here!
    # This example uses plain text passwords, which is INSECURE.
    # Use libraries like passlib or werkzeug.security for hashing.
    conn = get_connection()
    try:
        cur = conn.cursor()
        #query = "SELECT * FROM %s WHERE username = %s AND password = %s"
        query = "SELECT * FROM doctors WHERE username = %s AND password = %s"
        logging.info(query)
        cur.execute(query, (username, password))
        user_data = cur.fetchone()
        if user_data:
            logging.info(f"User {username} authenticated successfully.")
            return user_data # Return patient_id on success
            # stored_password = user_data[1]
            # Replace this with a proper hash check:
            # from werkzeug.security import check_password_hash
            # if check_password_hash(stored_password, password):
            # if stored_password == password: # INSECURE - REPLACE
            #     logging.info(f"User {username} authenticated successfully.")
            #     return user_data[0] # Return patient_id on success
        else:
            logging.warning(f"Authentication failed for user {username}: User not found or incorrect password provided")
            return None
    except Exception as e:
        logging.error(f"An error occurred during authentication: {e}")
        return None
    finally:
        cur.close()
        conn.close()

# CREATE: Insert a new doctor record (no hospital_id)
def create_doctor(first_name, last_name, specialization=None,
                 experience_years=None, qualifications=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = """
            INSERT INTO doctors (
                doctor_id, first_name, last_name, specialization, experience_years,
                qualifications
            )
            VALUES (uuid_generate_v4(), %s, %s, %s, %s, %s)
            RETURNING doctor_id;
        """
        cur.execute(query, (
            first_name, last_name, specialization, experience_years,
            qualifications
        ))
        new_id = cur.fetchone()[0]
        conn.commit()
        logging.info(f"Created doctor with id: {new_id}")
        # NOTE: Doctor is created but not linked to any location yet.
        # Call link_doctor_to_location separately.
        return new_id
    except Exception as e:
        logging.error(f"An error occurred while creating doctor: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()

# READ: Retrieve a doctor record by id (locations fetched separately or joined)
def get_doctor_by_id(doctor_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Get basic doctor info
        query = "SELECT * FROM doctors WHERE doctor_id = %s;"
        cur.execute(query, (doctor_id,))
        doctor = cur.fetchone() # This will be a tuple or None
        if not doctor:
             return None

        # Fetch associated locations
        loc_query = """
            SELECT l.location_id, l.location_name, l.address, l.location_type
            FROM locations l
            JOIN doctor_locations dl ON l.location_id = dl.location_id
            WHERE dl.doctor_id = %s;
        """
        cur.execute(loc_query, (doctor_id,))
        locations = cur.fetchall()

        # Combine into a dictionary or custom object (example with dict)
        doctor_dict = {
            'doctor_id': doctor[0],
            'first_name': doctor[1],
            'last_name': doctor[2],
            'specialization': doctor[3],
            'experience_years': doctor[4],
            'qualifications': doctor[5],
            'created_at': doctor[6],
            'updated_at': doctor[7],
            'locations': [dict(zip(['location_id', 'location_name', 'address', 'location_type'], loc)) for loc in locations]
        }

        logging.info(f"Fetched doctor: {doctor_dict['first_name']} {doctor_dict['last_name']}")
        return doctor_dict
    except Exception as e:
        logging.error(f"An error occurred while fetching doctor: {e}")
        return None
    finally:
        cur.close()
        conn.close()

# LINK/UNLINK Doctor and Location
def link_doctor_to_location(doctor_id, location_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = "INSERT INTO doctor_locations (doctor_id, location_id) VALUES (%s, %s) ON CONFLICT DO NOTHING;"
        cur.execute(query, (doctor_id, location_id))
        conn.commit()
        logging.info(f"Linked doctor {doctor_id} to location {location_id}")
        return True
    except Exception as e:
        logging.error(f"An error occurred linking doctor to location: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

def unlink_doctor_from_location(doctor_id, location_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = "DELETE FROM doctor_locations WHERE doctor_id = %s AND location_id = %s;"
        cur.execute(query, (doctor_id, location_id))
        conn.commit()
        logging.info(f"Unlinked doctor {doctor_id} from location {location_id}")
        return True
    except Exception as e:
        logging.error(f"An error occurred unlinking doctor from location: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

# READ: Retrieve doctors practicing at a specific location
def get_doctors_by_location(location_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = """
            SELECT d.*
            FROM doctors d
            JOIN doctor_locations dl ON d.doctor_id = dl.doctor_id
            WHERE dl.location_id = %s
            ORDER BY d.last_name, d.first_name;
        """
        cur.execute(query, (location_id,))
        doctors = cur.fetchall()
        return doctors
    except Exception as e:
        logging.error(f"An error occurred while fetching doctors by location: {e}")
        return []
    finally:
        cur.close()
        conn.close()

# READ: Search doctors by specialization (includes locations)
def search_doctors_by_specialization(specialization):
    conn = get_connection()
    try:
        cur = conn.cursor()
        # This query fetches doctor details along with ALL locations they practice at
        # It might produce multiple rows per doctor if they practice at multiple locations
        
        query = """
            SELECT d.*, l.location_id, l.location_name, l.address, l.location_type
            FROM doctors d
            LEFT JOIN doctor_locations dl ON d.doctor_id = dl.doctor_id
            LEFT JOIN locations l ON dl.location_id = l.location_id
            WHERE d.specialization LIKE %s
            ORDER BY d.last_name, d.first_name, l.location_name;
        """
        cur.execute(query, (f"%{specialization}%",))
        doctors_with_locations = cur.fetchall()
        # Process results (e.g., group by doctor_id)
        results = {}
        for row in doctors_with_locations:
            doc_id = row[0]
            if doc_id not in results:
                results[doc_id] = {
                    'doctor_id': row[0],
                    'first_name': row[1],
                    'last_name': row[2],
                    'specialization': row[3],
                    'experience_years': row[4],
                    'qualifications': row[5],
                    'created_at': row[6],
                    'updated_at': row[7],
                    'locations': []
                }
            if row[8]: # If location data exists (due to LEFT JOIN)
                 results[doc_id]['locations'].append({
                     'location_id': row[8],
                     'location_name': row[9],
                     'address': row[10],
                     'location_type': row[11]
                 })
        return list(results.values())

    except Exception as e:
        logging.error(f"An error occurred while searching doctors: {e}")
        return []
    finally:
        cur.close()
        conn.close()

# UPDATE: Update a doctor's core record (location links managed separately)
def update_doctor(doctor_id, first_name=None, last_name=None, specialization=None,
                 experience_years=None, qualifications=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        fields = []
        values = []
        if first_name is not None: fields.append("first_name = %s"); values.append(first_name)
        if last_name is not None: fields.append("last_name = %s"); values.append(last_name)
        if specialization is not None: fields.append("specialization = %s"); values.append(specialization)
        if experience_years is not None: fields.append("experience_years = %s"); values.append(experience_years)
        if qualifications is not None: fields.append("qualifications = %s"); values.append(qualifications)

        if not fields: logging.warning("No fields provided to update doctor."); return False

        values.append(doctor_id)
        query = f"UPDATE doctors SET {', '.join(fields)} WHERE doctor_id = %s;"
        cur.execute(query, values)
        conn.commit()
        logging.info(f"Updated doctor with id: {doctor_id}")
        return True
    except Exception as e:
        logging.error(f"An error occurred while updating doctor: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

# DELETE: Remove a doctor record (links in doctor_locations deleted by CASCADE)
def delete_doctor(doctor_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = "DELETE FROM doctors WHERE doctor_id = %s;"
        cur.execute(query, (doctor_id,))
        conn.commit()
        logging.info(f"Deleted doctor with id: {doctor_id}")
        return True
    except Exception as e:
        logging.error(f"An error occurred while deleting doctor: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

##########################
# PATIENT FUNCTIONS
##########################

# AUTHENTICATE: Validate a patient's username and password
#def validate_user(userType, username, password):
def validate_patient(username, password):
    # IMPORTANT: Implement proper password hashing and verification here!
    # This example uses plain text passwords, which is INSECURE.
    # Use libraries like passlib or werkzeug.security for hashing.
    conn = get_connection()
    try:
        cur = conn.cursor()
        #query = "SELECT * FROM %s WHERE username = %s AND password = %s"
        query = "SELECT * FROM patients WHERE username = %s AND password = %s"
        logging.info(query)
        cur.execute(query, (username, password))
        user_data = cur.fetchone()
        if user_data:
            logging.info(f"User {username} authenticated successfully.")
            return user_data # Return patient_id on success
            # stored_password = user_data[1]
            # Replace this with a proper hash check:
            # from werkzeug.security import check_password_hash
            # if check_password_hash(stored_password, password):
            # if stored_password == password: # INSECURE - REPLACE
            #     logging.info(f"User {username} authenticated successfully.")
            #     return user_data[0] # Return patient_id on success
        else:
            logging.warning(f"Authentication failed for user {username}: User not found or incorrect password provided")
            return None
    except Exception as e:
        logging.error(f"An error occurred during authentication: {e}")
        return None
    finally:
        cur.close()
        conn.close()

# CREATE: Insert a new patient record
def create_patient(username, password, first_name, last_name, email, date_of_birth=None, gender=None, phone_number=None, address=None):
    # IMPORTANT: Hash the password before storing!
    # from werkzeug.security import generate_password_hash
    # hashed_password = generate_password_hash(password)
    hashed_password = password # INSECURE - REPLACE

    conn = get_connection()
    try:
        cur = conn.cursor()
        query = """
            INSERT INTO patients (patient_id, username, password, first_name, last_name, email, date_of_birth, gender, phone_number, address)
            VALUES (uuid_generate_v4(), %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING patient_id;
        """
        cur.execute(query, (username, hashed_password, first_name, last_name, email, date_of_birth, gender, phone_number, address))
        new_id = cur.fetchone()[0]
        conn.commit()
        logging.info(f"Created patient with id: {new_id}")
        return new_id
    except Exception as e:
        # Check for duplicate username/email errors (unique constraints)
        if "unique constraint" in str(e).lower():
             logging.error(f"Failed to create patient: Username or Email already exists.")
        else:
             logging.error(f"An error occurred while creating patient: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()

# READ: Retrieve a patient record by id
def get_patient_by_id(patient_id):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) # Use DictCursor
        query = "SELECT * FROM patients WHERE patient_id = %s;"
        cur.execute(query, (patient_id,))
        patient = cur.fetchone()
        # Application logic should check patient['consent_share_location'] before displaying address
        logging.info(f"Fetched patient information for id: {patient_id}")
        return dict(patient) if patient else None
    except Exception as e:
        logging.error(f"An error occurred while fetching patient: {e}")
        return None
    finally:
        cur.close()
        conn.close()

# UPDATE: Update a patient's record (add consent flag)
def update_patient(patient_id, username=None, password=None, first_name=None, last_name=None, email=None,
                   date_of_birth=None, gender=None, phone_number=None, address=None, consent_share_location=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        fields = []
        values = []
        if username is not None: fields.append("username = %s"); values.append(username)
        if password is not None:
            # Hash password before updating
            # hashed_password = generate_password_hash(password)
            hashed_password = password # INSECURE
            fields.append("password = %s"); values.append(hashed_password)
        if first_name is not None: fields.append("first_name = %s"); values.append(first_name)
        if last_name is not None: fields.append("last_name = %s"); values.append(last_name)
        if email is not None: fields.append("email = %s"); values.append(email)
        if date_of_birth is not None: fields.append("date_of_birth = %s"); values.append(date_of_birth)
        if gender is not None: fields.append("gender = %s"); values.append(gender)
        if phone_number is not None: fields.append("phone_number = %s"); values.append(phone_number)
        if address is not None: fields.append("address = %s"); values.append(address)
        if consent_share_location is not None: fields.append("consent_share_location = %s"); values.append(consent_share_location)

        if not fields: logging.warning("No fields provided to update patient."); return False

        values.append(patient_id)
        query = f"UPDATE patients SET {', '.join(fields)} WHERE patient_id = %s;"
        cur.execute(query, values)
        conn.commit()
        logging.info(f"Updated patient with id: {patient_id}")
        return True
    except Exception as e:
        logging.error(f"An error occurred while updating patient: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

# DELETE: Remove a patient record (Appointments deleted by CASCADE)
def delete_patient(patient_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = "DELETE FROM patients WHERE patient_id = %s;"
        cur.execute(query, (patient_id,))
        conn.commit()
        logging.info(f"Deleted patient with id: {patient_id}")
        return True
    except Exception as e:
        logging.error(f"An error occurred while deleting patient: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

###########################
# APPOINTMENT FUNCTIONS
###########################

# CREATE: Book a new appointment (includes location_id)
def create_appointment(patient_id, doctor_id, location_id, appointment_date, appointment_time, reason=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Optional: Verify that the doctor actually practices at the given location_id
        # verify_query = "SELECT 1 FROM doctor_locations WHERE doctor_id = %s AND location_id = %s;"
        # cur.execute(verify_query, (doctor_id, location_id))
        # if not cur.fetchone():
        #     logging.error(f"Doctor {doctor_id} does not practice at location {location_id}")
        #     return None

        query = """
            INSERT INTO appointments (
                appointment_id, patient_id, doctor_id, location_id, appointment_date,
                appointment_time, reason, status
            )
            VALUES (uuid_generate_v4(), %s, %s, %s, %s, %s, %s, 'scheduled')
            RETURNING appointment_id;
        """
        cur.execute(query, (
            patient_id, doctor_id, location_id, appointment_date,
            appointment_time, reason
        ))
        new_id = cur.fetchone()[0]
        conn.commit()
        logging.info(f"Created appointment with id: {new_id} at location {location_id}")
        return new_id
    except Exception as e:
        logging.error(f"An error occurred while creating appointment: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()

# READ: Get appointments for a patient (includes location details)
def get_patient_appointments(patient_id):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) # Use DictCursor
        query = """
            SELECT
                a.appointment_id, a.appointment_date, a.appointment_time,
                a.reason, a.status, a.created_at,
                d.doctor_id, d.first_name as doctor_first_name,
                d.last_name as doctor_last_name, d.specialization,
                l.location_id, l.location_name, l.address as location_address, l.location_type
            FROM appointments a
            JOIN doctors d ON a.doctor_id = d.doctor_id
            JOIN locations l ON a.location_id = l.location_id
            WHERE a.patient_id = %s
            ORDER BY a.appointment_date DESC, a.appointment_time DESC;
        """
        cur.execute(query, (patient_id,))
        appointments = cur.fetchall()
        return [dict(app) for app in appointments]
    except Exception as e:
        logging.error(f"An error occurred while fetching patient appointments: {e}")
        return []
    finally:
        cur.close()
        conn.close()

# READ: Get appointments for a doctor (includes location and patient details)
def get_doctor_appointments(doctor_id):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) # Use DictCursor
        query = """
            SELECT
                a.appointment_id, a.appointment_date, a.appointment_time,
                a.reason, a.status, a.created_at,
                p.patient_id, p.first_name as patient_first_name,
                p.last_name as patient_last_name,
                l.location_id, l.location_name, l.address as location_address
            FROM appointments a
            JOIN patients p ON a.patient_id = p.id
            JOIN locations l ON a.location_id = l.location_id
            WHERE a.doctor_id = %s
            ORDER BY a.appointment_date DESC, a.appointment_time DESC;
        """
        cur.execute(query, (doctor_id,))
        appointments = cur.fetchall()
        return [dict(app) for app in appointments]
    except Exception as e:
        logging.error(f"An error occurred while fetching doctor appointments: {e}")
        return []
    finally:
        cur.close()
        conn.close()

# UPDATE: Update appointment status or details
def update_appointment(appointment_id, status=None, appointment_date=None, appointment_time=None, reason=None, location_id=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        fields = []
        values = []

        if status is not None:
            valid_statuses = ['scheduled', 'confirmed', 'cancelled', 'completed']
            if status not in valid_statuses:
                logging.error(f"Invalid appointment status: {status}")
                return False
            fields.append("status = %s"); values.append(status)
        if appointment_date is not None: fields.append("appointment_date = %s"); values.append(appointment_date)
        if appointment_time is not None: fields.append("appointment_time = %s"); values.append(appointment_time)
        if reason is not None: fields.append("reason = %s"); values.append(reason)
        if location_id is not None: fields.append("location_id = %s"); values.append(location_id)

        if not fields: logging.warning("No fields provided to update appointment."); return False

        values.append(appointment_id)
        query = f"UPDATE appointments SET {', '.join(fields)} WHERE appointment_id = %s;"
        cur.execute(query, values)
        conn.commit()
        logging.info(f"Updated appointment {appointment_id}")
        return True
    except Exception as e:
        logging.error(f"An error occurred while updating appointment: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

# DELETE: Cancel/delete an appointment
def delete_appointment(appointment_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = "DELETE FROM appointments WHERE appointment_id = %s;"
        cur.execute(query, (appointment_id,))
        conn.commit()
        logging.info(f"Deleted appointment with id: {appointment_id}")
        return True
    except Exception as e:
        logging.error(f"An error occurred while deleting appointment: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close() 

