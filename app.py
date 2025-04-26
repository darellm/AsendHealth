import os
from dotenv import load_dotenv
load_dotenv()  # Load variables from .env

import requests, postgres, json, uuid
from flask import Flask, render_template, request, jsonify
from vectors import get_existing_record,ask_medical_chatbot

app = Flask(__name__, template_folder="templates", static_folder="static")

# Existing Routes
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@app.route("/maya")
def maya():
    return render_template("maya.html")

# New Routes for the updated navigation
@app.route("/home")
def home():
    return render_template("home.html")

@app.route("/appointments")
def appointments():
    return render_template("appointments.html")

@app.route("/feedback")
def feedback():
    return render_template("feedback.html")

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")  # password is treated as the GUID
    if username and password:
        result = postgres.validate_user(username, password)
        if result is not None:

            # Process patient data from postgres
            patient_GUID = str(result[20])
            patient_name = result[0] + " " + result[1]

            print("Login successful!", patient_name)

            # Retrieve patient data from qdrant
            qdrant_url = os.getenv("QDRANT_URL")
            qdrant_scroll_url = f"{qdrant_url}/collections/patient_records/points/scroll"
            payload = {
                "filter": {
                    "should": [
                        {"key": "guid", "match": {"value": patient_GUID}},
                        {"key": "name", "match": {"value": patient_name}}
                    ]
                }
            }
            headers = {
                "Content-Type": "application/json",
                "api-key": os.getenv("QDRANT_API_KEY", "YOUR_DEFAULT_API_KEY")
            }
            try:
                response = requests.post(qdrant_scroll_url, json=payload, headers=headers)
                if response.ok:
                    result = response.json()
                    points = result.get("result", {}).get("points", [])
                    if points:
                        point_id = points[0]['id']  # Store the point ID
                        return jsonify({"guid": password, "point_id": point_id})
                    else:
                        return jsonify({"message": "Patient record not found"}), 404
                else:
                    return jsonify({
                        "message": "Error retrieving patient record from Qdrant",
                        "status": response.status_code
                    }), response.status_code
            except Exception as e:
                return jsonify({"message": str(e)}), 500
        else:
            print("Invalid username or password!")
    else:
        print("Invalid username or password!")
        return jsonify({"message": "Invalid credentials"}), 400

@app.route("/api/patient-records", methods=["POST"])
def api_patient_records():
    data = request.get_json()
    point_id = data.get("point_id")  # Use point_id instead of guid
    if not point_id:
        return jsonify({"message": "No patient point ID provided"}), 400
    try:
        record = get_existing_record(point_id)
        if record:
            payload = record.get("payload")
            # Optionally: Ensure the payload contains "conversations"
            # For example, if not present, you might add:
            # payload["conversations"] = record.get("conversations", [])
            if payload:
                return jsonify(payload)
            else:
                return jsonify({"message": "Patient record has no payload"}), 404
        else:
            return jsonify({"message": "Patient not found"}), 404
    except Exception as e:
        return jsonify({"message": str(e)}), 500

@app.route("/api/chatbot", methods=["POST"])
def api_chatbot():
    data = request.get_json()
    user_query = data.get("query", "")
    point_id = data.get("point_id")
    show_thinking = data.get("show_thinking", False)

    if not user_query:
        return jsonify({"reply": "No query provided."}), 400
    
    reply = ask_medical_chatbot(user_query, point_id)
    return jsonify({"reply": reply})


if __name__ == "__main__":
    app.run()


# POSTGRES DATABASE USAGE EXAMPLES:

# Create a new patient record
new_patient_id = postgres.create_patient("jsnow", "Asend123!", "John", "Snow", "jsnow@example.com")

# # Read the newly created patient record
if new_patient_id is not None:
    print("Usecase1: New Patient created:", new_patient_id)
    patient = postgres.get_patient_by_id(new_patient_id)
    if patient is not None:
        print("Usecase2: Read New Patient", patient)

# Update the patient's email
if new_patient_id is not None:
    update_success = postgres.update_patient(new_patient_id, email="john.snow@example.com")
    if update_success is not None:
        print("Usecase3: Update new patient successful", update_success)

# Validate a user (example of a read operation using credentials)
user = postgres.validate_user("jsnow", "Asend123!")
if user is not None:
    print("usecase4: validate user successful", user)

# Delete the patient record
if new_patient_id is not None:
    delete_success = postgres.delete_patient(new_patient_id)
    if delete_success is not None:
        print("usercase5: Delete patient successful", delete_success)