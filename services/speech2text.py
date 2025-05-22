import os
import requests
import io
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
        
def speechtotext(service_key, audio_file_path):
    try:
        logging.info(f"Starting speech-to-text conversion for file: {audio_file_path}")
        DEEPGRAM_API_KEY = service_key
        DEEPGRAM_API_URL = 'https://api.deepgram.com/v1/listen'

        headers = {
            'Authorization': f'Token {DEEPGRAM_API_KEY}'
        }

        logging.debug(f"Opening audio file: {audio_file_path}")
        with open(audio_file_path, 'rb') as audio_file:
            response = requests.post(DEEPGRAM_API_URL, headers=headers, files={'file': audio_file})

        if response.status_code == 200:
            result = response.json()
            transcript = result['results']['channels'][0]['alternatives'][0]['transcript']
            logging.info("Speech-to-text conversion successful")
            logging.debug(f"Transcript: {transcript}")
            return transcript
        else:
            logging.error(f"Speech-to-Text API failed with status code {response.status_code}: {response.text}")
            raise Exception(f"Speech-to-Text API failed: {response.text}")
    except Exception as e:
        logging.error(f"Error during speech-to-text conversion: {e}")
        raise