import os
from dotenv import load_dotenv
from datetime import datetime, timezone
import requests
import postgres # Assuming this is your local postgress.py module
import json
import uuid
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_mail import Mail, Message # Added for Flask-Mail
from vectors import get_existing_record,ask_medical_chatbot,update_patient_record
from agents import AreyaAgent  # Make sure AreyaAgent is defined in agents.py
import logging
from threading import Thread
import asyncio

# Basic logging configuration - SET TO DEBUG TO CAPTURE MORE DETAIL
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(name)s - %(funcName)s - %(message)s')

load_dotenv()  # Load variables from .env
app = Flask(__name__, template_folder="templates", static_folder="static")
app.debug = True

# Flask-Mail configuration - READ FROM ENVIRONMENT VARIABLES
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER') # e.g., 'smtp.gmail.com'
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587)) # e.g., 587 for TLS, 465 for SSL
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() in ('true', '1', 't')
app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'False').lower() in ('true', '1', 't')
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME') # Your email address
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD') # Your email password or app password
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', app.config['MAIL_USERNAME'])

mail = Mail(app)

# Existing Routes
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@app.route("/areya")
def areya():
    return render_template("areya.html")

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

@app.route("/history")
def history():
    return render_template("history.html")

# """ @app.route("/areya")
# def areya():
#     return render_template("areya.html") """

@app.route("/api/login", methods=["POST"])
def api_login():
    logging.info("/api/login called")
    data = request.get_json()
    userType = data.get("userType")
    username = data.get("username")
    password = data.get("password")
    logging.info(f"Login attempt: userType={userType}, username={username}")

    if not all([userType, username, password]):
        logging.warning("Missing userType, username, or password in login request")
        return jsonify({"message": "Missing userType, username, or password"}), 400

    if userType == "patient":
        try:
            logging.info("Before validate_patient")
            result = postgres.validate_patient(username, password)
            logging.info("After validate_patient")
            logging.info(f"validate_patient returned type: {type(result)}, value: {result}")
            if result is not None:
                # Ensure result is a dictionary (due to RealDictCursor)
                if not isinstance(result, dict):
                    logging.error(f"validate_patient did not return a dict for user {username}. Got: {type(result)}")
                    return jsonify({"message": "Internal server error during login processing."}), 500

                logging.info(f"Patient login successful for {username}! Result: {result}")

                patient_GUID = str(result.get('patient_id')) # Use .get() for safety
                first_name = result.get('first_name')
                last_name = result.get('last_name')

                if not patient_GUID or not first_name or not last_name:
                    logging.error(f"Missing essential patient data (patient_id, first_name, or last_name) for user {username}. Result: {result}")
                    return jsonify({"message": "Patient data incomplete after login."}), 500
                
                patient_name = f"{first_name} {last_name}"
                logging.info(f"Processing login for patient: {patient_name} (GUID: {patient_GUID})")

                # Retrieve patient data from qdrant
                qdrant_url = os.getenv("QDRANT_URL")
                if not qdrant_url:
                    logging.error("QDRANT_URL environment variable not set.")
                    return jsonify({"message": "Qdrant service misconfiguration."}), 500
                
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
                    "api-key": os.getenv("QDRANT_API_KEY") # Default can be handled by Qdrant or env
                }
                
                qdrant_response = requests.post(qdrant_scroll_url, json=payload, headers=headers, timeout=10)
                qdrant_response.raise_for_status() # Will raise HTTPError for bad responses (4xx or 5xx)
                
                qdrant_result = qdrant_response.json()
                points = qdrant_result.get("result", {}).get("points", [])
                
                if points:
                    point_id = points[0].get('id')
                    if not point_id:
                        logging.error(f"Qdrant point_id missing for user {username}. Qdrant result: {qdrant_result}")
                        return jsonify({"message": "Patient vector record incomplete."}), 500
                        
                    # Create response object
                    response_data = {"guid": patient_GUID, "point_id": point_id, "userType": userType, "username": username, "name": patient_name}
                    response = jsonify(response_data)
                    
                    # Set secure cookie with user info
                    cookie_value = json.dumps({
                        "username": username,
                        "userType": userType,
                        "point_id": point_id,
                        "patient_id": patient_GUID, # Store patient_id (GUID) from DB
                        "name": patient_name
                    })
                    response.set_cookie(
                        'asendhealth',
                        cookie_value,
                        max_age=604800,  # 7 days
                        secure=app.config.get('SESSION_COOKIE_SECURE', False), # Use app config for secure
                        httponly=True, # Prevent JS access to cookie if possible
                        samesite=app.config.get('SESSION_COOKIE_SAMESITE', 'Lax') # Use app config
                    )
                    logging.info(f"Cookie set for patient {username} with point_id {point_id}")
                    return response
                else:
                    logging.warning(f"Patient record not found in Qdrant for user {username} (GUID: {patient_GUID})")
                    return jsonify({"message": "Patient vector record not found. Please contact support."}), 404
            
            elif result is None: # Explicitly handle None case for validate_patient
                logging.warning(f"Invalid patient credentials for username: {username}")
                return jsonify({"message": "Invalid username or password"}), 401 # 401 for unauthorized
            
        except requests.exceptions.HTTPError as http_err:
            logging.error(f"HTTP error occurred during Qdrant request for user {username}: {http_err} - Response: {http_err.response.text}")
            return jsonify({"message": "Error communicating with Qdrant service."}), 502 # 502 Bad Gateway
        except requests.exceptions.ConnectionError as conn_err:
            logging.error(f"Connection error during Qdrant request for user {username}: {conn_err}")
            return jsonify({"message": "Could not connect to Qdrant service."}), 503 # 503 Service Unavailable
        except requests.exceptions.Timeout as timeout_err:
            logging.error(f"Timeout during Qdrant request for user {username}: {timeout_err}")
            return jsonify({"message": "Qdrant service request timed out."}), 504 # 504 Gateway Timeout
        except Exception as e:
            logging.error(f"An unexpected error occurred during patient login for {username}: {str(e)}", exc_info=True)
            return jsonify({"message": "An internal error occurred. Please try again later."}), 500

    elif userType == "provider":
        try:
            result = postgres.validate_doctor(username, password)
            if result is not None:
                if not isinstance(result, dict):
                    logging.error(f"validate_doctor did not return a dict for user {username}. Got: {type(result)}")
                    return jsonify({"message": "Internal server error during login processing."}), 500

                logging.info(f"Provider login successful for {username}! Result: {result}")
                
                # Assuming validate_doctor returns at least 'doctor_id', 'first_name', 'last_name'
                doctor_id = str(result.get('doctor_id'))
                first_name = result.get('first_name')
                last_name = result.get('last_name')

                if not doctor_id or not first_name or not last_name:
                    logging.error(f"Missing essential doctor data (doctor_id, first_name, or last_name) for user {username}. Result: {result}")
                    return jsonify({"message": "Provider data incomplete after login."}), 500

                provider_name = f"Dr. {first_name} {last_name}"

                response_data = {"message": "Provider login successful!", "userType": userType, "username": username, "name": provider_name, "doctor_id": doctor_id}
                response = jsonify(response_data)
                
                cookie_value = json.dumps({
                    "username": username,
                    "userType": userType,
                    "doctor_id": doctor_id, # Store doctor_id from DB
                    "name": provider_name
                })
                response.set_cookie(
                    'asendhealth',
                    cookie_value,
                    max_age=604800,  # 7 days
                    secure=app.config.get('SESSION_COOKIE_SECURE', False),
                    httponly=True,
                    samesite=app.config.get('SESSION_COOKIE_SAMESITE', 'Lax')
                )
                logging.info(f"Cookie set for provider {username}")
                return response
            else:
                logging.warning(f"Invalid provider credentials for username: {username}")
                return jsonify({"message": "Invalid username or password"}), 401
        except Exception as e:
            logging.error(f"An unexpected error occurred during provider login for {username}: {str(e)}", exc_info=True)
            return jsonify({"message": "An internal error occurred. Please try again later."}), 500
    else:
        logging.warning(f"Invalid userType received: {userType}")
        return jsonify({"message": "Invalid user type specified"}), 400

@app.route("/api/patient-records", methods=["POST"])
def api_patient_records():
    data = request.get_json()
    point_id = data.get("point_id")  # Use point_id instead of guid
    if not point_id:
        return jsonify({"message": "No patient point ID provided"}), 400
    try:
        record = get_existing_record(point_id)
        if record:
            payload = record.get("payload", {}) # Ensure payload is a dict

            # Ensure all expected keys for the dashboard are present
            # This prevents KeyErrors if some records are missing these fields
            expected_keys_with_defaults = {
                "medical_conditions": [],
                "medications": [],
                "activity_log": [],
                "health_metrics": {},
                "alerts": [],
                "assessment": [], # Assuming 'assessment' is also used by the dashboard
                "name": "N/A",
                "age": "N/A",
                "gender": "N/A",
                "location": "N/A",
                "guid": "", # Ensure guid is present as it's used in chatbot
                "conditions": [], # Used by chatbot
                "last_visit": None, # Used by chatbot
                "last_condition": None # Used by chatbot
                # Add any other keys your dashboard or other parts of the app expect
            }
            for key, default_value in expected_keys_with_defaults.items():
                if key not in payload:
                    payload[key] = default_value
            
            # Ensure nested structures like 'assessment' also get a default if needed by frontend
            # For instance, if dashboard expects assessment to be a list even if empty from Qdrant
            if "assessment" in payload and payload["assessment"] is None:
                payload["assessment"] = []


            if payload: # payload will now always exist and have defaults
                return jsonify(payload)
            else: # This case should ideally not be hit if record exists
                return jsonify({"message": "Patient record has no payload"}), 404
        else:
            return jsonify({"message": "Patient not found"}), 404
    except Exception as e:
        app.logger.error(f"Error in /api/patient-records for point_id {point_id}: {str(e)}", exc_info=True) # Log full error
        return jsonify({"message": str(e)}), 500

def run_agent(coro, result_container):
    result_container.append(asyncio.run(coro))

@app.route('/api/chatbot', methods=['POST'])
def chatbot():
    try:
        data = request.get_json()
        user_query = data.get("query", "")
        point_id = data.get("point_id")
        show_thinking = data.get("show_thinking", False)
        deep_research_mode = data.get("deep_research_mode", False)

        if not user_query:
            return jsonify({
                "reply": "No query provided",
                "research": "",
                "thinking": "",
                "show_thinking": show_thinking
            }), 400

        try:
            # Get start time for performance tracking
            start_time = datetime.now()
            app.logger.info(f"Processing chatbot request for query: {user_query[:50]}...{' (Deep Research Mode)' if deep_research_mode else ' (Simple Mode)'}")
            
            # Fetch patient context
            try:
                patient_data = get_existing_record(point_id).get("payload", {})
                patient_context = {
                    "name": patient_data.get("name", "User"),
                    "last_visit": patient_data.get("last_visit"),
                    "last_condition": patient_data.get("last_condition"),
                    "medical_history": patient_data.get("medical_history", []),
                    "age": patient_data.get("age"),
                    "conditions": patient_data.get("conditions", []),
                    "medications": patient_data.get("medications", []),
                    "allergies": patient_data.get("allergies", []),
                    "guid": patient_data.get("guid", "")
                }
                app.logger.info(f"Patient context loaded for {patient_context['name']}")
            except Exception as e:
                app.logger.error(f"Error fetching patient context: {e}")
                patient_context = {"name": "User"}

            # Check if Ollama server is running first
            try:
                ollama_response = requests.get("http://localhost:11434/api/tags", timeout=5)
                if ollama_response.status_code != 200:
                    app.logger.error(f"Ollama server is not responding properly: {ollama_response.status_code}")
                    return jsonify({
                        "reply": "The medical AI service is currently experiencing technical difficulties. Please try again in a few minutes.",
                        "research": "<h3>Service Status</h3><p>The AI service is temporarily unavailable.</p>",
                        "show_thinking": False
                    }), 503
                else:
                    app.logger.info("Ollama server is running and responding")
            except requests.exceptions.RequestException as e:
                app.logger.error(f"Failed to connect to Ollama server: {e}")
                return jsonify({
                    "reply": "Unable to connect to the AI service. Please ensure the service is running.",
                    "research": f"<h3>Connection Error</h3><p>{str(e)}</p>",
                    "show_thinking": False
                }), 503

            # Initialize Areya agent and process message
            agent = AreyaAgent()
            
            # Use asyncio.run to call the async method
            response = asyncio.run(agent.process_message(
                user_query,
                patient_context=patient_context,
                deep_research_mode=deep_research_mode,
                show_thinking=show_thinking
            ))

            # Split response into parts if it contains the separator
            parts = response.split('|||')
            reply = parts[0].strip()
            research = parts[1].strip() if len(parts) > 1 else ""

            # Update patient record with conversation
            try:
                update_patient_record(
                    point_id, 
                    {
                        "conversations": [{
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "id": str(datetime.now().timestamp()),
                            "sender": "User",
                            "message": user_query
                        }, {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "id": str(datetime.now().timestamp() + 1),
                            "sender": "Areya",
                            "message": reply,
                            "research": research,
                            "sources": extract_sources_from_research(research)
                        }]
                    }
                )
                app.logger.info(f"Conversation history updated for user {patient_context['name']}")
            except Exception as e:
                app.logger.error(f"Error updating conversation history: {e}")

            return jsonify({
                "reply": reply,
                "research": research,
                "show_thinking": show_thinking
            })

        except Exception as e:
            app.logger.error(f"Error processing message: {str(e)}", exc_info=True)
            return jsonify({
                "reply": f"I encountered an error while processing your request: {str(e)}",
                "research": "<h3>Error Details</h3><p>An error occurred while processing your request. Please try again.</p>",
                "show_thinking": False
            }), 500

    except Exception as e:
        app.logger.error(f"Error in chatbot endpoint: {str(e)}", exc_info=True)
        return jsonify({
            "reply": "An unexpected error occurred. Please try again.",
            "research": f"<h3>Error Details</h3><p>{str(e)}</p>",
            "show_thinking": False
        }), 500

def extract_sources_from_research(research_text):
    """Extract source information from research text to store separately"""
    sources = []
    if not research_text:
        return sources
        
    try:
        # Using regex to find source domains and links
        import re
        
        # Multiple patterns to extract source information
        # First trying the div-based format
        domain_matches_div = re.findall(r"<div class=['\"]source-domain['\"]>(.*?)</div>", research_text)
        link_matches_div = re.findall(r"<a href=['\"]([^'\"]+)['\"][^>]*>.*?</a>", research_text)
        content_matches_div = re.findall(r"<div class=['\"]source-content['\"]>(.*?)</div>", research_text)
        
        #  trying h3/p format that might be used
        domain_matches_h3 = re.findall(r"<h3>(.*?)</h3>", research_text)
        content_matches_p = re.findall(r"<p>(.*?)</p>", research_text)
        
        # Using the format that found more matches
        if len(domain_matches_div) > 0:
            app.logger.info(f"Using div-based format: found {len(domain_matches_div)} domains")
            domain_matches = domain_matches_div
            content_matches = content_matches_div
            link_matches = link_matches_div
        else:
            app.logger.info(f"Using h3/p format: found {len(domain_matches_h3)} domains")
            domain_matches = domain_matches_h3
            content_matches = content_matches_p
            # Try to extract links from the research text
            link_matches = re.findall(r"<a href=['\"]([^'\"]+)['\"][^>]*>", research_text)
        
        # Combining the extracted information
        for i in range(min(len(domain_matches), max(1, len(content_matches)))):
            source = {
                "domain": domain_matches[i] if i < len(domain_matches) else "Medical Source",
                "url": link_matches[i] if i < len(link_matches) else "",
                "snippet": content_matches[i] if i < len(content_matches) else "Source information not available"
            }
            
            # Cleaning  up HTML tags from content
            source["snippet"] = re.sub(r"<[^>]+>", "", source["snippet"])
            
            # Limit snippet length
            if len(source["snippet"]) > 300:
                source["snippet"] = source["snippet"][:297] + "..."
                
            sources.append(source)
            
        if not sources and "source" in research_text.lower():
            # Fallback for research text that mentions sources but doesn't match our patterns
            # Extract for URLs from the text
            all_urls = re.findall(r"https?://[^\s<>\"']+", research_text)
            
            for url in all_urls:
                # Try to extract domain from URL
                domain_match = re.search(r"https?://(?:www\.)?([^/]+)", url)
                domain = domain_match.group(1) if domain_match else "Medical Source"
                
                source = {
                    "domain": domain,
                    "url": url,
                    "snippet": "Information from this source was referenced in the research."
                }
                sources.append(source)
                
        app.logger.info(f"Extracted {len(sources)} sources from research data")
    except Exception as e:
        app.logger.error(f"Error extracting sources from research: {e}")
        
    return sources

@app.route('/screenshots/<path:filename>')
def serve_screenshot(filename):
    return send_from_directory('screenshots', filename)

@app.route("/api/conversations", methods=["POST"])
def api_conversations():
    """Retrieve conversation history for a patient"""
    data = request.get_json()
    point_id = data.get("point_id")
    
    if not point_id:
        return jsonify({"message": "No patient point ID provided"}), 400
        
    try:
        record = get_existing_record(point_id)
        if record:
            payload = record.get("payload", {})
            conversations = payload.get("conversations", [])
            
            # Group conversations by pairs (user and response)
            grouped_conversations = []
            current_group = None
            
            for conv in conversations:
                if conv.get("sender") == "User" and not current_group:
                    # Start a new group with a user message
                    current_group = {
                        "id": conv.get("id", str(datetime.now().timestamp())),
                        "timestamp": conv.get("timestamp", datetime.now(timezone.utc).isoformat()),
                        "user_message": conv.get("message", ""),
                        "response": None,
                        "research": None,
                        "sources": []
                    }
                elif conv.get("sender") == "Areya" and current_group:
                    # Complete the group with Areya's response
                    current_group["response"] = conv.get("message", "")
                    current_group["research"] = conv.get("research", "")
                    current_group["sources"] = conv.get("sources", [])
                    grouped_conversations.append(current_group)
                    current_group = None
            
            # Sort by timestamp, newest first
            grouped_conversations.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            
            return jsonify({
                "conversations": grouped_conversations,
                "total": len(grouped_conversations)
            })
        else:
            return jsonify({"message": "Patient not found"}), 404
    except Exception as e:
        app.logger.error(f"Error retrieving conversation history: {e}")
        return jsonify({"message": str(e)}), 500

@app.route("/api/conversations/delete", methods=["POST"])
def api_delete_conversation():
    """Delete a specific conversation from patient history"""
    data = request.get_json()
    point_id = data.get("point_id")
    conversation_id = data.get("conversation_id")
    
    if not point_id or not conversation_id:
        return jsonify({"message": "Missing required parameters"}), 400
        
    try:
        record = get_existing_record(point_id)
        if not record:
            return jsonify({"message": "Patient not found"}), 404
            
        payload = record.get("payload", {})
        conversations = payload.get("conversations", [])
        
        # Find all conversation IDs that need to be removed
        # This includes the target ID and any responses tied to it
        ids_to_remove = set()
        ids_to_remove.add(conversation_id)
        
        # Find related messages (user/Areya pairs)
        user_timestamp = None
        for conv in conversations:
            if conv.get("id") == conversation_id:
                # If we found the target conversation, get its timestamp
                user_timestamp = conv.get("timestamp")
                break
                
        # If we found a timestamp, find Areya's response that is close in time
        if user_timestamp:
            # Convert to datetime for comparison if it's a string
            if isinstance(user_timestamp, str):
                try:
                    user_dt = datetime.fromisoformat(user_timestamp.replace('Z', '+00:00'))
                    # Look for messages within 5 seconds of the user message
                    for conv in conversations:
                        if conv.get("sender") == "Areya":
                            conv_timestamp = conv.get("timestamp")
                            if conv_timestamp and isinstance(conv_timestamp, str):
                                try:
                                    conv_dt = datetime.fromisoformat(conv_timestamp.replace('Z', '+00:00'))
                                    # If the Areya message is within 5 seconds of the user message, it's likely the response
                                    if abs((conv_dt - user_dt).total_seconds()) < 5:
                                        ids_to_remove.add(conv.get("id"))
                                except (ValueError, TypeError):
                                    continue
                except (ValueError, TypeError):
                    pass
        
        # Filter out the conversations with the IDs to remove
        new_conversations = [conv for conv in conversations if conv.get("id") not in ids_to_remove]
        
        # Update the patient record with the filtered conversations
        update_patient_record(point_id, {"conversations": new_conversations})
        
        return jsonify({
            "success": True,
            "message": "Conversation deleted successfully",
            "remaining": len(new_conversations) // 2  # Dividing by 2 to get conversation pairs
        })
    except Exception as e:
        app.logger.error(f"Error deleting conversation: {e}")
        return jsonify({"message": str(e)}), 500

@app.route("/api/book-appointment", methods=["POST"])
def api_book_appointment():
    data = request.get_json()
    app.logger.info(f"Received booking request: {data}")
    print(data.get("patient_id"))

    patient_id = data.get("patient_id") # This needs to come from logged-in user session/localStorage
    doctor_id = data.get("doctor_id")
    location_id = data.get("location_id")
    appointment_date_str = data.get("appointment_date") # Expected format YYYY-MM-DD
    appointment_time_str = data.get("appointment_time") # Expected format HH:MM AM/PM or HH:MM (24h)
    reason = data.get("reason", "N/A")
    patient_name_for_email = data.get("patient_name", "Patient") # Get from form, or better, from patient_id record
    # It's better to fetch patient_email from the database using patient_id for security and accuracy.

    if not all([patient_id, doctor_id, location_id, appointment_date_str, appointment_time_str]):
        app.logger.warning("Booking request missing required fields.")
        return jsonify({"success": False, "message": "Missing required appointment details."}), 400

    try:
        # Convert date and time strings to datetime objects
        # Assuming appointment_date_str is YYYY-MM-DD
        app_date_obj = datetime.strptime(appointment_date_str, "%Y-%m-%d").date()
        
        # Assuming appointment_time_str is like "09:00 AM" or "14:30"
        try:
            app_time_obj = datetime.strptime(appointment_time_str, "%I:%M %p").time() # Handles AM/PM
        except ValueError:
            app_time_obj = datetime.strptime(appointment_time_str, "%H:%M").time() # Handles 24-hour

    except ValueError as ve:
        app.logger.error(f"Invalid date or time format in booking request: {ve}")
        return jsonify({"success": False, "message": "Invalid date or time format."}), 400

    # Call postgres function to create appointment
    # Note: postgres.create_appointment expects date and time objects
    new_appointment_id = postgres.create_appointment(
        patient_id=patient_id,
        doctor_id=doctor_id,
        location_id=location_id,
        appointment_date=app_date_obj,
        appointment_time=app_time_obj,
        reason=reason
    )

    if new_appointment_id:
        app.logger.info(f"Appointment {new_appointment_id} created successfully in DB.")
        # Fetch details needed for the email (patient email, doctor name, location name)
        # This is a simplified example; you might have more direct ways or need more error handling
        patient_record = postgres.get_patient_by_id(patient_id)
        doctor_record = postgres.get_doctor_by_id(doctor_id) # Assuming this returns a dict-like object
        location_record = postgres.get_location_by_id(location_id) # Assuming this returns a dict-like object

        patient_email_address = "roccoroger34@gmail.com" # Using your specified email for now
        if patient_record and 'email' in patient_record:
             # In a real scenario, use patient_record['email'] after ensuring it's verified
             pass # For now, we will use the hardcoded one as requested
        else:
            app.logger.warning(f"Could not retrieve email for patient {patient_id}. Using default.")

        doc_name_for_email = "Dr. Brijesh"
        if doctor_record and 'first_name' in doctor_record and 'last_name' in doctor_record:
            doc_name_for_email = f"Dr. {doctor_record['first_name']} {doctor_record['last_name']}"
        
        loc_name_for_email = "Unknown Location"
        if location_record and isinstance(location_record, dict) and 'location_name' in location_record:
            loc_name_for_email = location_record['location_name']
        elif location_record and isinstance(location_record, (list, tuple)) and len(location_record) > 1: # Fallback for older tuple format if necessary
            loc_name_for_email = location_record[1]

        email_sent = send_appointment_confirmation_email(
            patient_email=patient_email_address,
            patient_name=patient_name_for_email, # Ideally fetched from patient_record
            doctor_name=doc_name_for_email,
            appointment_date=app_date_obj,
            appointment_time=app_time_obj,
            location_name=loc_name_for_email
        )
        
        if email_sent:
            return jsonify({"success": True, "message": "Appointment booked and confirmation email sent!", "appointment_id": new_appointment_id})
        else:
            return jsonify({"success": True, "message": "Appointment booked, but failed to send confirmation email.", "appointment_id": new_appointment_id})
    else:
        app.logger.error("Failed to create appointment in DB.")
        return jsonify({"success": False, "message": "Failed to book appointment. Please try again."}), 500

# --- START: New API Endpoint for Booking Appointment ---
def send_appointment_confirmation_email(patient_email, patient_name, doctor_name, appointment_date, appointment_time, location_name):
    if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
        app.logger.error("Mail server not configured. MAIL_USERNAME or MAIL_PASSWORD missing.")
        return False
    try:
        subject = "Your Appointment Confirmation - AsendHealth"
        # Format date and time for better readability in email if they are objects
        formatted_date = appointment_date
        if hasattr(appointment_date, 'strftime'):
            formatted_date = appointment_date.strftime("%A, %B %d, %Y")
        
        formatted_time = appointment_time
        if hasattr(appointment_time, 'strftime'):
            formatted_time = appointment_time.strftime("%I:%M %p")

        body = f"""Dear {patient_name},

This email confirms your appointment with AsendHealth.

Appointment Details:
---------------------
Doctor: {doctor_name}
Date: {formatted_date}
Time: {formatted_time}
Location: {location_name}

If you need to reschedule or cancel, please contact us as soon as possible.

We look forward to seeing you!

Sincerely,
The AsendHealth Team
"""
        # For HTML email, you would use render_template:
        # html_body = render_template('emails/appointment_confirmation.html', 
        #                             patient_name=patient_name, doctor_name=doctor_name, 
        #                             appointment_date=formatted_date, appointment_time=formatted_time, 
        #                             location_name=location_name)
        # msg = Message(subject, recipients=[patient_email], body=body, html=html_body)
        
        msg = Message(subject, recipients=[patient_email], body=body)
        mail.send(msg)
        app.logger.info(f"Confirmation email successfully sent to {patient_email} for appointment with {doctor_name}.")
        return True
    except Exception as e:
        app.logger.error(f"Failed to send confirmation email to {patient_email}: {e}", exc_info=True)
        return False
# --- END Email Sending Function ---

@app.route("/api/appointment-page-data", methods=["GET"])
def api_appointment_page_data():
    """
    API endpoint to fetch all necessary data for the appointments page.
    This includes locations (hospitals/clinics with their doctors),
    filter options (states, districts, specialties, types),
    and specialty ratings.
    """
    try:
        # Assume a function in postgres.py that fetches all this data
        # This function would need to be implemented in postgres.py
        # It should return data in a structure that's easy for the frontend to use,
        # similar to the hardcoded data currently in appointments.html.
        
        # Example of expected structure from postgres.get_appointment_page_details():
        # {
        #     "locations": [
        #         {
        #             "id": 1, "name": "AIIMS Delhi", "location": "New Delhi, Delhi", 
        #             "district": "New Delhi", "state": "Delhi", "type": "Government",
        #             "specialties": ["Cardiology", "Neurology"], "rating": 4.7,
        #             "doctors": [
        #                 {"id": 101, "name": "Dr. Rajesh Kumar", "specialty": "Cardiology", 
        #                  "qualification": "MD, DM", "experience": "15 years"}
        #             ]
        #         },
        #         # ... more locations
        #     ],
        #     "filter_options": {
        #         "states": ["Delhi", "Maharashtra", ...],
        #         "districts_by_state": {
        #             "Delhi": ["New Delhi", "South Delhi", ...],
        #             "Maharashtra": ["Mumbai City", "Pune", ...]
        #         },
        #         "specialties": ["Cardiology", "Neurology", ...],
        #         "hospital_types": ["Government", "Private", ...]
        #     },
        #     "specialty_ratings": { 
        #         "Cardiology": [1, 2, 4], 
        #         # ... more ratings
        #     }
        # }
        
        data = postgres.get_appointment_page_details() # You'll need to create this function
        
        if not data:
            app.logger.error("No data returned from postgres.get_appointment_page_details")
            return jsonify({
                "success": False, 
                "message": "Could not retrieve appointment page data."
            }), 500
            
        return jsonify({
            "success": True,
            "locations": data.get("locations", []),
            "filter_options": data.get("filter_options", {}),
            "specialty_ratings": data.get("specialty_ratings", {})
        })
        
    except AttributeError as ae:
        # This can happen if postgres.get_appointment_page_details is not defined
        app.logger.error(f"AttributeError: Possibly postgres.get_appointment_page_details is not defined or an attribute is missing. {str(ae)}", exc_info=True)
        return jsonify({"success": False, "message": "Server configuration error for appointment data."}), 500
    except Exception as e:
        app.logger.error(f"Error fetching appointment page data: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": "An error occurred while fetching appointment page data."}), 500

if __name__ == "__main__":
    # The basicConfig is already set up above, no need to call it again here
    # unless you want a different configuration for when run directly.
    # For consistency, relying on the top-level basicConfig.
    app.run(port=5000, debug=True, use_reloader=False)


# POSTGRES DATABASE USAGE EXAMPLES:

# # Create a new patient record
# new_patient_id = postgres.create_patient("jsnow", "Asend123!", "John", "Snow", "jsnow@example.com")

# # # Read the newly created patient record
# if new_patient_id is not None:
#     print("Usecase1: New Patient created:", new_patient_id)
#     patient = postgres.get_patient_by_id(new_patient_id)
#     if patient is not None:
#         print("Usecase2: Read New Patient", patient)

# # Update the patient's email
# if new_patient_id is not None:
#     update_success = postgres.update_patient(new_patient_id, email="john.snow@example.com")
#     if update_success is not None:
#         print("Usecase3: Update new patient successful", update_success)

# # Validate a user (example of a read operation using credentials)
# user = postgres.validate_user("jsnow", "Asend123!")
# if user is not None:
#     print("usecase4: validate user successful", user)

# # Delete the patient record
# if new_patient_id is not None:
#     delete_success = postgres.delete_patient(new_patient_id)
#     if delete_success is not None:
#         print("usercase5: Delete patient successful", delete_success)