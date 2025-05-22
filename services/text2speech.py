import os
import requests
import io
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
        
def text2speech(service_key, text):
    try:
        logging.info("Starting text-to-speech conversion")
        DEEPGRAM_API_KEY = service_key
        DEEPGRAM_API_URL = 'https://api.deepgram.com/v1/speak'

        headers = {
            'Authorization': f'Token {DEEPGRAM_API_KEY}',
            'Content-Type': 'application/json'
        }
        # data = {
        #     'text': text,
        #     'voice': 'en_us_male',  # Customize the voice as needed
        #     'language': 'en'        # Customize the language as needed
        # }

        payload = {
            "text": text  # Ensure only 'text' is provided
        }

        logging.debug(f"Requesting text-to-speech for text: {text}")
        response = requests.post(DEEPGRAM_API_URL, headers=headers, json=payload)

        if response.status_code == 200:
            logging.info("Text-to-speech conversion successful")
            return io.BytesIO(response.content)  # Return audio as a byte stream
        else:
            logging.error(f"Text-to-Speech API failed with status code {response.status_code}: {response.text}")
            raise Exception(f"Text-to-Speech API failed: {response.text}")
    except Exception as e:
        logging.error(f"Error during text-to-speech conversion: {e}")
        raise