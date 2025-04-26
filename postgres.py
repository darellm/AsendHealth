import os
import pg8000
import ssl
import certifi
import json
from google.cloud.sql.connector import Connector
import psycopg2
import psycopg2.extras

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

# AUTHENTICATE: Validate a patients username and password
def validate_user(username, password):
    # Replace these with your actual GCP Postgres connection details
    conn = get_connection()
    
    try:
        # Using DictCursor to fetch results as a dictionary
        #cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur = conn.cursor()
        
        # Use a parameterized query to prevent SQL injection
        query = "SELECT * FROM patients WHERE username = %s AND password = %s"
        cur.execute(query, (username, password))
        user = cur.fetchone()
        print("postgres user", user)
        
        return user #is not None
    except Exception as e:
        print("An error occurred:", e)
        return False
    finally:
        cur.close()
        conn.close()

# CREATE: Insert a new patient record
def create_patient(username, password, first_name, last_name, email):
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = """
            INSERT INTO patients (username, password, first_name, last_name, email)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
        """
        cur.execute(query, (username, password, first_name, last_name, email))
        new_id = cur.fetchone()[0]
        conn.commit()
        print("Created patient with id:", new_id)
        return new_id
    except Exception as e:
        print("An error occurred while creating patient:", e)
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()

# READ: Retrieve a patient record by id
def get_patient_by_id(patient_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = "SELECT * FROM patients WHERE id = %s;"
        cur.execute(query, (patient_id,))
        patient = cur.fetchone()
        print("Fetched patient:", patient)
        return patient
    except Exception as e:
        print("An error occurred while fetching patient:", e)
        return None
    finally:
        cur.close()
        conn.close()

# UPDATE: Update a patient's record
def update_patient(patient_id, username=None, password=None, first_name=None, last_name=None, email=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Build a dynamic update query based on provided fields
        fields = []
        values = []
        if username is not None:
            fields.append("username = %s")
            values.append(username)
        if password is not None:
            fields.append("password = %s")
            values.append(password)
        if first_name is not None:
            fields.append("first_name = %s")
            values.append(first_name)
        if last_name is not None:
            fields.append("last_name = %s")
            values.append(last_name)
        if email is not None:
            fields.append("email = %s")
            values.append(email)
        if not fields:
            print("No fields provided to update.")
            return False
        # Append patient_id for the WHERE clause
        values.append(patient_id)
        query = f"UPDATE patients SET {', '.join(fields)} WHERE id = %s;"
        cur.execute(query, values)
        conn.commit()
        print(f"Updated patient with id: {patient_id}")
        return True
    except Exception as e:
        print("An error occurred while updating patient:", e)
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

# DELETE: Remove a patient record
def delete_patient(patient_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = "DELETE FROM patients WHERE id = %s;"
        cur.execute(query, (patient_id,))
        conn.commit()
        print(f"Deleted patient with id: {patient_id}")
        return True
    except Exception as e:
        print("An error occurred while deleting patient:", e)
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

