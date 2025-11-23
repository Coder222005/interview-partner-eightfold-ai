import os
import modal
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, Response
import re

def create_model_image():
    return (
        modal.Image.debian_slim(python_version="3.11")
        .pip_install(
            "torch",
            "transformers>=4.40.0",  # CRITICAL: Llama 3 requires >=4.40
            "accelerate",
            "bitsandbytes",
            "huggingface-hub",
            "openai-whisper",
            "TTS",
            "soundfile",
            "numpy",
            "fastapi",
            "uvicorn",
            "python-multipart",
            "sentencepiece",
            "protobuf"
        )
        .apt_install("espeak-ng")
    )

model_image = create_model_image()

app = modal.App(
    "open-source-interview-trainer",
    image=model_image,
    secrets=[modal.Secret.from_name("dr-sense-secrets")]
)

# --- STT (Whisper Large) ---
@app.cls(gpu="t4", max_containers=4)
class STTModel:
    @modal.enter()
    def load(self):
        import whisper
        self.model = whisper.load_model("large-v3", device="cuda")

    @modal.method()
    def transcribe(self, audio_bytes: bytes) -> str:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()
            try:
                result = self.model.transcribe(tmp.name, fp16=True)
            except:
                result = self.model.transcribe(tmp.name, fp16=False)
            return result["text"].strip()

# --- LLM (Llama 3 70B on H100) ---
# UPDATES:
# 1. gpu="h100": Upgraded for speed.
# 2. scaledown_window=1200: Replaces deprecated 'container_idle_timeout'.
# 3. timeout=1200: Allows 20 mins for the model to download/load.
@app.cls(
    gpu="h100", 
    max_containers=1, 
    scaledown_window=1200, 
    timeout=1200
)
class LLMModel:
    @modal.enter()
    def load(self):
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
        
        # Using the environment variable for the token
        hf_token = os.environ["HF_TOKEN"]
        
        # The model you requested
        model_repo = "meta-llama/Meta-Llama-3-70B-Instruct"

        print(f"Loading {model_repo} on H100...")

        quant = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4"
        )

        self.tokenizer = AutoTokenizer.from_pretrained(model_repo, token=hf_token)
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token_id = self.tokenizer.eos_token_id

        self.model = AutoModelForCausalLM.from_pretrained(
            model_repo,
            quantization_config=quant,
            device_map="auto",
            token=hf_token
        )
        self.device = next(self.model.parameters()).device
        self.model.eval()
        print("Llama 3 loaded successfully.")

    @modal.method()
    def generate_response(self, messages: list, max_tokens: int = 512, temperature: float = 0.7) -> str:
        try:
            # Apply Llama 3 Chat Template
            templ = self.tokenizer.apply_chat_template(
                messages, return_dict=True, return_tensors="pt", add_generation_prompt=True
            )
            ids = templ["input_ids"].to(self.device)
            mask = templ.get("attention_mask", (ids != self.tokenizer.pad_token_id).long()).to(self.device)
        except Exception as e:
            # Fallback if template fails
            print(f"Template Error: {e}")
            return "I encountered an error processing your request."

        output = self.model.generate(
            input_ids=ids,
            attention_mask=mask,
            max_new_tokens=max_tokens,
            do_sample=True,
            temperature=temperature,
            pad_token_id=self.tokenizer.eos_token_id,
            eos_token_id=self.tokenizer.eos_token_id
        )

        generated_text = self.tokenizer.decode(output[0][ids.shape[1]:], skip_special_tokens=True).strip()

        # --- STRICT SANITIZATION ---
        # Removes dialogue labels like "Assistant:" or "AI:" to prevent the bot from talking to itself
        pattern = r"(?i)^(assistant|ai|user|candidate|interviewer)\s*:\s*"
        cleaned_text = re.sub(pattern, "", generated_text).strip()
        
        # Remove hallucinated user turns (common in 70B models)
        if "User:" in cleaned_text:
            cleaned_text = cleaned_text.split("User:")[0].strip()
        
        return cleaned_text

# --- TTS (VCTK) ---
@app.cls(gpu="t4", max_containers=4)
class TTSModel:
    @modal.enter()
    def load(self):
        from TTS.api import TTS
        # VCTK VITS is a high quality open source TTS
        self.model_name = "tts_models/en/vctk/vits"
        self.tts = TTS(self.model_name, gpu=True)

    @modal.method()
    def synthesize(self, text: str) -> bytes:
        import tempfile, os
        
        # Pre-processing for better speech
        text = text.replace("*", " ").replace("#", " ").replace("-", " ")
        pattern = r"(?i)^(assistant|ai)\s*:\s*"
        text = re.sub(pattern, "", text).strip()

        if not text: return None

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            path = tmp.name

        # Speaker "p225" is generally clear and professional
        self.tts.tts_to_file(text=text, file_path=path, speaker="p225")

        with open(path, "rb") as f:
            audio = f.read()

        try:
            os.remove(path)
        except:
            pass
        return audio

# --- FastAPI ---
fastapi_app = FastAPI()

@fastapi_app.post("/stt")
async def stt(file: UploadFile = File(...)):
    return {"text": STTModel().transcribe.remote(await file.read())}

@fastapi_app.post("/llm")
async def llm(payload: dict):
    # Pass max_tokens and temperature to the model
    return {
        "response": LLMModel().generate_response.remote(
            payload.get("messages", []),
            payload.get("max_tokens", 512),
            payload.get("temperature", 0.7)
        )
    }

@fastapi_app.post("/tts")
async def tts(payload: dict):
    wav = TTSModel().synthesize.remote(payload.get("text", ""))
    return Response(content=wav, media_type="audio/wav")

@app.function()
@modal.asgi_app()
def asgi_app():
    return fastapi_app