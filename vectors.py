import requests
import json
from pydantic import BaseModel
import logging
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance
import os
from langchain_ollama import OllamaEmbeddings

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Constants
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = "patient_records"

# Initialize Qdrant and embeddings
client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
embeddings = OllamaEmbeddings(model="deepseek-r1:7b")
VECTOR_SIZE = 3072
VECTOR_PARAMS = VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)

# Data model for Patient
class Patient(BaseModel):
    id: str
    name: str
    age: int
    location: str
    notes: str = None

# CRUD Operations
def create_patient_record(point_id, vector, payload_data):
    """Create a new patient record."""
    url = f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points"
    payload = {
        "points": [
            {
                "id": point_id,
                "vector": vector,
                "payload": payload_data
            }
        ]
    }
    headers = {'api-key': QDRANT_API_KEY, 'Content-Type': 'application/json'}
    try:
        response = requests.put(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()  # Raise an HTTPError for bad responses
        logging.info(f"Patient record created successfully for ID: {point_id}")
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error creating patient record for ID: {point_id}. Exception: {e}")
        raise

def get_existing_record(point_id):
    """Retrieve a patient record by point ID."""
    url = f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points/{point_id}"
    headers = {'api-key': QDRANT_API_KEY, 'Content-Type': 'application/json'}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()["result"]
    except requests.exceptions.RequestException as e:
        logging.error(f"Error reading patient record for ID: {point_id}. Exception: {e}")
        raise

def put_patient_record(url, api_key, collection_name, point_id, vector, payload):
    """Upserts a patient record into Qdrant."""
    endpoint = f"{url}/collections/{collection_name}/points"
    headers = {'api-key': api_key, 'Content-Type': 'application/json'}
    data = {
        "points": [
            {
                "id": point_id,
                "vector": vector,
                "payload": payload
            }
        ]
    }
    try:
        response = requests.put(endpoint, json=data, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error upserting record for ID: {point_id}. Exception: {e}")
        raise

def update_patient_record(point_id, updated_payload, new_vector=None):
    """Update an existing patient record with new data."""
    try:
        # Retrieve the existing record
        existing_record = get_existing_record(point_id)
        existing_payload = existing_record.get("payload", {})
        existing_vector = existing_record.get("vector", [])

        # Merge the new data with the existing payload
        merged_payload = {**existing_payload, **updated_payload}

        # Handle lists explicitly to append data (if needed)
        for key in updated_payload:
            if isinstance(existing_payload.get(key), list) and isinstance(updated_payload[key], list):
                merged_payload[key] = existing_payload[key] + updated_payload[key]

        # Use the existing vector if a new one is not provided
        final_vector = new_vector if new_vector else existing_vector

        # Upsert the merged record back to Qdrant
        put_patient_record(QDRANT_URL, QDRANT_API_KEY, COLLECTION_NAME, point_id, final_vector, merged_payload)

        logging.info(f"Patient record with ID '{point_id}' has been updated successfully.")
        logging.debug(f"Merged Record: {json.dumps(merged_payload, indent=2)}")

    except Exception as e:
        logging.error(f"Failed to update the record for ID: {point_id}. Exception: {e}")

def delete_patient_record(point_id):
    """Delete a patient record by point ID."""
    url = f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points/delete"
    payload = {"points": [point_id]}
    headers = {'api-key': QDRANT_API_KEY, 'Content-Type': 'application/json'}
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        logging.info(f"Patient record deleted successfully for ID: {point_id}")
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error deleting patient record for ID: {point_id}. Exception: {e}")
        raise

def ensure_model_is_pulled(model_name="deepseek-r1:7b"):
    """Ensure the required model is pulled before using it."""
    pull_url = "http://localhost:11434/api/pull"
    try:
        response = requests.post(pull_url, json={"name": model_name})
        response.raise_for_status()
        logging.info(f"Model {model_name} is ready")
        return True
    except requests.exceptions.ConnectionError:
        logging.error("Cannot connect to Ollama. Is the service running?")
        print("ERROR: Ollama service is not running. Please start Ollama first.")
        return False
    except Exception as e:
        logging.error(f"Error pulling model: {e}")
        return False

def ask_medical_chatbot(user_query, point_id):
    """Uses local Ollama to generate a medical-focused response."""
    # Check if it's a greeting
    greeting_words = {'hi', 'hello', 'hey', 'greetings'}
    is_greeting = any(word.lower() in user_query.lower() for word in greeting_words)
    
    if is_greeting:
        return "Hello! How can I assist you today?"

    # Retrieve context if available
    context = ""
    try:
        record = get_existing_record(point_id)
        if record and "payload" in record and "medical_history" in record["payload"]:
            context = record["payload"]["medical_history"]
    except Exception as e:
        logging.error(f"Error retrieving context for chatbot for ID: {point_id}. Exception: {e}")

    # Construct prompt based on query type
    if "what" in user_query.lower() and "am" in user_query.lower() and "i" in user_query.lower():
        prompt = (
            "You are Maya, an AI medical assistant. Respond in this EXACT format:\n\n"
            "[AI Medical Disclaimer: I am an AI assistant, not a licensed medical professional.]\n\n"
            "## Important Notice\n"
            "• Without a proper medical examination, I cannot diagnose specific conditions\n"
            "• Please provide more specific symptoms or concerns\n"
            "• Consider discussing your symptoms with a healthcare provider\n\n"
            "## Recommended Next Steps\n"
            "• Document any specific symptoms you're experiencing\n"
            "• Note when these symptoms started\n"
            "• Schedule an appointment with a healthcare provider\n\n"
            "Please seek professional medical advice for an accurate diagnosis.\n"
        )
    else:
        prompt = (
            "You are Maya, an AI medical assistant. Format your response EXACTLY as follows:\n\n"
            "[AI Medical Disclaimer]\n\n"
            "## Current Understanding\n"
            "• Brief explanation of the condition/query\n"
            "• Key points about the topic\n\n"
            "## Important Information\n"
            "• Relevant details\n"
            "• Key considerations\n\n"
            "## Medical Advisory\n"
            "Consult healthcare professionals for personalized medical advice.\n\n"
            f"Context: {context}\nQuery: {user_query}"
        )

    # Call Ollama
    try:
        response = requests.post("http://localhost:11434/api/generate", 
            json={
                "model": "deepseek-r1:7b",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 1024
                }
            })
        response.raise_for_status()
        result = response.json()
        return result.get("response", "").strip()
        
    except Exception as e:
        logging.error(f"Error calling Ollama for chatbot: {e}")
        return "Sorry, something went wrong with the chatbot."

