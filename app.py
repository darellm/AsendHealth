import os
from dotenv import load_dotenv
from datetime import datetime, timezone
import requests, postgres, json, uuid
from flask import Flask, render_template, request, jsonify, send_from_directory
from vectors import get_existing_record,ask_medical_chatbot,update_patient_record
from agents import MayaAgent  # Make sure MayaAgent is defined in agents.py
import logging
from threading import Thread
import asyncio

load_dotenv()  # Load variables from .env
app = Flask(__name__, template_folder="templates", static_folder="static")

# Existing Routes
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@app.route("/areya")
def areya():
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

@app.route("/history")
def history():
    return render_template("history.html")

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()
    userType = data.get("userType")
    username = data.get("username")
    password = data.get("password")  
    if username and password and userType == "patient":
        result = postgres.validate_patient(username, password)
        if result is not None:
            print("Patient login successful!", result)
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
                        
                        # Create response object
                        response = jsonify({"guid": password, "point_id": point_id})
                        
                        # Set secure cookie with user info
                        cookie_value = json.dumps({
                            "username": username,
                            "userType": userType,
                            "point_id": point_id  
                        })
                        response.set_cookie(
                            'asendhealth',
                            cookie_value,
                            max_age=604800,  # 7 days
                            secure=False,     # Only sent over HTTPS
                            httponly=True,   # Not accessible via JavaScript
                            samesite='Strict' # Prevent CSRF
                        )
                        
                        return response
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
            return jsonify({"message": "Invalid credentials"}), 400
        
    elif username and password and userType == "provider":
        # Needs to be implemented
        result = postgres.validate_doctor(username, password)
        if result is not None:
            print("Provider login successful!")
            response = jsonify({"message": "Provider login successful!"})
            
            # Set secure cookie with user info
            cookie_value = json.dumps({
                "username": username,
                "userType": userType
            })
            response.set_cookie(
                'asendhealth',
                cookie_value,
                max_age=604800,  # 7 days
                secure=False,     # Only sent over HTTPS
                httponly=True,   # Not accessible via JavaScript
                samesite='Strict' # Prevent CSRF
            )
            
            return response
        else:
            print("Invalid username or password!")
            return jsonify({"message": "Invalid credentials"}), 400
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
            if payload:
                return jsonify(payload)
            else:
                return jsonify({"message": "Patient record has no payload"}), 404
        else:
            return jsonify({"message": "Patient not found"}), 404
    except Exception as e:
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

            # Initialize Maya agent and process message
            agent = MayaAgent()
            
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
                            "sender": "Maya",
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
                elif conv.get("sender") == "Maya" and current_group:
                    # Complete the group with Maya's response
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
        
        # Find related messages (user/Maya pairs)
        user_timestamp = None
        for conv in conversations:
            if conv.get("id") == conversation_id:
                # If we found the target conversation, get its timestamp
                user_timestamp = conv.get("timestamp")
                break
                
        # If we found a timestamp, find Maya's response that is close in time
        if user_timestamp:
            # Convert to datetime for comparison if it's a string
            if isinstance(user_timestamp, str):
                try:
                    user_dt = datetime.fromisoformat(user_timestamp.replace('Z', '+00:00'))
                    # Look for messages within 5 seconds of the user message
                    for conv in conversations:
                        if conv.get("sender") == "Maya":
                            conv_timestamp = conv.get("timestamp")
                            if conv_timestamp and isinstance(conv_timestamp, str):
                                try:
                                    conv_dt = datetime.fromisoformat(conv_timestamp.replace('Z', '+00:00'))
                                    # If the Maya message is within 5 seconds of the user message, it's likely the response
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

if __name__ == "__main__":
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