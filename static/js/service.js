let recognition;
let isRecording = false;

// Check if the browser supports SpeechRecognition API
if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = 'en-US';
} else {
    alert("Speech Recognition API is not supported in this browser.");
}

// Start Recording
document.addEventListener('click', (event) => {
    if (event.target.id === 'startButton' && !isRecording && recognition) {
        isRecording = true;
        recognition.start();
    } else if (event.target.id === 'stopButton' && isRecording && recognition) {
        isRecording = false;
        recognition.stop();
    } else if (event.target.id === 'transferButton' && !isRecording && recognition) {
        const speechText = document.getElementById('speechToText').value.trim();
        if (speechText) {
            document.getElementById('textToSpeechInput').value = speechText;  // Transfer text
            convertTextToSpeech(speechText);  // Convert transferred text to speech
        } else {
            alert("No text to transfer.");
        }
    } else if (event.target.id === 'textToSpeechButton') {
        const text = document.getElementById('textToSpeechInput').value.trim();
        if (text) {
            convertTextToSpeech(text);  // Convert manually entered text to speech
        } else {
            alert("Please enter some text to convert to speech.");
        }
    } else if (event.target.id === 'submitButton') {
        const question = document.getElementById('proactiveCareReq').value.trim();
        if (question) {
            getProactiveCareAdvice(question);
        } else {
            alert("Please enter a question.");
        }
    } else if (event.target.id === 'saveButton') {
        const llmModel = document.getElementById('llmModel').value.trim();
        const t2sService = document.getElementById('t2sService').value.trim();
        const groq_key = document.getElementById('groq_key').value.trim();
        const deepgram_key = document.getElementById('deepgram_key').value.trim();

        data = {
            "llmModel": llmModel,
            "t2sService": t2sService,
            "groq_key": groq_key,
            "deepgram_key": deepgram_key
        }

        if (data) {
            saveSettings(data);
        } else {
            alert("Settings were not saved!");
        }
    }
});

// Handle speech recognition results
recognition.onresult = async (event) => {
    const transcript = Array.from(event.results)
        .map(result => result[0].transcript)
        .join('');

    // Display the transcribed text
    const speechToTextDiv = document.getElementById('speechToText');
    speechToTextDiv.value = transcript;

    // Send the transcript to the server for processing
    try {
        const response = await fetch('/process-audio', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ text: transcript })
        });

        const result = await response.json();

        // Display the generated answer in the proactive care section
        const proactiveCareResp = document.getElementById('proactiveCareResp');
        proactiveCareResp.value = result.answer || 'No response from server';
    } catch (error) {
        console.error('Error:', error);
    }
};

recognition.onerror = (event) => {
    console.error('Speech Recognition Error:', event.error);
};

recognition.onend = () => {
    if (isRecording) {
        recognition.start(); // Restart recognition if recording was interrupted
    }
};

// Convert Text to Speech
async function convertTextToSpeech(text) {
    try {
        const response = await fetch('/text-to-speech', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ text: text })
        });

        if (response.ok) {
            const audioUrl = URL.createObjectURL(await response.blob());
            const audio = new Audio(audioUrl);
            audio.play();
        } else {
            alert("Error generating speech.");
            console.error("Error response:", await response.text());
        }
    } catch (error) {
        console.error("Fetch error:", error);
    }
}

// Get Proactive Care Advice
async function getProactiveCareAdvice(question) {
    try {
        const response = await fetch('/preventative-care', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ question: question })
        });

        const result = await response.json();

        // Display the proactive care response
        const proactiveCareResp = document.getElementById('proactiveCareResp');
        proactiveCareResp.value = result.answer || 'No response from server';
    } catch (error) {
        console.error('Error:', error);
    }
}

async function saveSettings() {
    try {
        const response = await fetch('/save-settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ question: question })
        });

        const result = await response.json();

        // Display the proactive care response
        const proactiveCareResp = document.getElementById('proactiveCareResp');
        proactiveCareResp.value = result.answer || 'No response from server';
    } catch (error) {
        console.error('Error:', error);
    }
}

