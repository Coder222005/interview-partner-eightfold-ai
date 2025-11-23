# api_client.py
import aiohttp
import json
from typing import List, Dict
# Ensure you update this URL after deploying the backend again
BASE_URL = ""
TTS_URL = f"{BASE_URL}/tts"
STT_URL = f"{BASE_URL}/stt"
LLM_URL = f"{BASE_URL}/llm"

class ModalClient:
    @staticmethod
    async def stt(audio_path: str) -> str:
        try:
            data = aiohttp.FormData()
            data.add_field('file', open(audio_path, 'rb'), filename='input.wav', content_type='audio/wav')
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
                async with session.post(STT_URL, data=data) as response:
                    if response.status == 200:
                        res_json = await response.json()
                        return res_json.get("text", "")
                    return ""
        except Exception as e:
            print(f"STT Exception: {e}")
            return ""

    @staticmethod
    async def tts(text: str) -> bytes:
        try:
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
                async with session.post(TTS_URL, json={"text": text}) as response:
                    if response.status == 200:
                        return await response.read()
                    return None
        except Exception as e:
            print(f"TTS Exception: {e}")
            return None

    @staticmethod
    async def llm(messages: List[Dict], max_tokens: int = 150, temperature: float = 0.7) -> str:
        try:
            limited_messages = messages[:1] + messages[-6:] if len(messages) > 7 else messages
            payload = {
                "messages": limited_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stop": ["\n\n", "User:", "Candidate:", "Assistant:"]
            }
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
                async with session.post(LLM_URL, json=payload) as response:
                    if response.status == 200:
                        res_json = await response.json()
                        return res_json.get("response", "")
                    return ""
        except Exception as e:
            print(f"LLM Exception: {e}")
            return ""

    @staticmethod
    async def check_intent(last_input: str) -> str:
        from prompts import INTENT_CHECK_PROMPT
        try:
            prompt = INTENT_CHECK_PROMPT.format(last_user_input=last_input)
            messages = [{"role": "user", "content": prompt}]
            resp = await ModalClient.llm(messages, max_tokens=10, temperature=0.1)
            return resp.strip().upper()
        except Exception:
            return "VALID" 

    @staticmethod
    async def analyze(question: str, answer: str, difficulty: str = "medium") -> str:
        from prompts import SYSTEM_PROMPT_ANALYZER
        try:
            prompt = SYSTEM_PROMPT_ANALYZER.format(
                question=question, 
                answer=answer, 
                difficulty=difficulty
            )
            messages = [{"role": "user", "content": prompt}]
            resp = await ModalClient.llm(messages, max_tokens=150, temperature=0.3)
            return resp
        except Exception:
            return "{}"