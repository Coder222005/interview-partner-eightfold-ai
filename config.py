import os

# Your specific Modal endpoints
BASE_URL = "YOUR_MODAL_BASE_URL_HERE" 
TTS_URL = f"{BASE_URL}/tts"
STT_URL = f"{BASE_URL}/stt"
LLM_URL = f"{BASE_URL}/llm"

# Settings
MAX_QUESTIONS = 10
# Question Distribution (percentages)
# 40% Personal Projects, 30% Technical, 30% Follow-up
PROJECT_PERCENTAGE = 0.40
TECHNICAL_PERCENTAGE = 0.50
FOLLOWUP_PERCENTAGE = 0.10
