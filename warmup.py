import requests
import json
import os

# --- CONFIGURATION ---
BASE_URL = "https://bommireddyvenkatadheerajreddy--open-source-interview-tra-3173fc.modal.run"
# specific endpoints
URL_HEALTH = f"{BASE_URL}/health"
URL_LLM = f"{BASE_URL}/llm"
URL_TTS = f"{BASE_URL}/tts"
URL_STT = f"{BASE_URL}/stt"

# Colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"

def test_health():
    print(f"Testing Health ({URL_HEALTH})...", end=" ")
    try:
        resp = requests.get(URL_HEALTH, verify=False)
        if resp.status_code == 200:
            print(f"{GREEN}PASSED{RESET}")
            return True
    except Exception as e:
        print(f"{RED}FAILED{RESET} - {e}")
    return False

def test_llm():
    print(f"Testing LLM ({URL_LLM})...", end=" ")
    # Matching your docs: {"history": [{"role": "user", "content": "..."}]}
    payload = {
        "history": [
            {"role": "user", "content": "I am testing your API. Say hello."}
        ]
    }
    try:
        resp = requests.post(URL_LLM, json=payload, verify=False)
        data = resp.json()
        if "response" in data:
            print(f"{GREEN}PASSED{RESET}")
            print(f"   └── Response: {data['response']}")
            return True
        else:
            print(f"{RED}FAILED{RESET} (Unexpected format): {data}")
    except Exception as e:
        print(f"{RED}FAILED{RESET} - {e}")
    return False

def test_tts():
    print(f"Testing TTS ({URL_TTS})...", end=" ")
    payload = {"text": "System check complete. Audio generation successful."}
    try:
        resp = requests.post(URL_TTS, json=payload, verify=False)
        if resp.status_code == 200:
            with open("warmup_audio.wav", "wb") as f:
                f.write(resp.content)
            print(f"{GREEN}PASSED{RESET}")
            print(f"   └── Saved to 'warmup_audio.wav'")
            return True
        else:
            print(f"{RED}FAILED{RESET} Status: {resp.status_code}")
    except Exception as e:
        print(f"{RED}FAILED{RESET} - {e}")
    return False

def test_stt():
    print(f"Testing STT ({URL_STT})...", end=" ")
    # We will use the audio generated in the previous step
    if not os.path.exists("warmup_audio.wav"):
        print(f"{RED}SKIPPED{RESET} (No audio file from TTS step)")
        return False

    try:
        with open("warmup_audio.wav", "rb") as f:
            files = {'file': ('test.wav', f, 'audio/wav')}
            resp = requests.post(URL_STT, files=files, verify=False)
        
        data = resp.json()
        if "text" in data:
            print(f"{GREEN}PASSED{RESET}")
            print(f"   └── Transcribed: '{data['text']}'")
            return True
        else:
            print(f"{RED}FAILED{RESET} (Unexpected format): {data}")
    except Exception as e:
        print(f"{RED}FAILED{RESET} - {e}")
    return False

if __name__ == "__main__":
    print("--- STARTING SYSTEM WARMUP ---\n")
    
    if test_health():
        test_llm()
        if test_tts():
            test_stt() # Only runs if TTS successfully created the file
            
    print("\n--- WARMUP COMPLETE ---")