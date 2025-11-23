import chainlit as cl
import os
import uuid
from graph import app_graph
from api_client import ModalClient
from config import MAX_QUESTIONS
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter

@cl.on_chat_start
async def start():
    # Ask for resume
    files = None
    while files is None:
        files = await cl.AskFileMessage(
            content="Hello! To help tailor the interview, please upload your resume (PDF).",
            accept=["application/pdf"],
            max_size_mb=10,
            timeout=180,
        ).send()

    resume_file = files[0]
    
    # Process the resume
    resume_summary = ""
    msg = cl.Message(content=f"Processing `{resume_file.name}`...")
    await msg.send()

    try:
        reader = PdfReader(resume_file.path)
        resume_text = ""
        for page in reader.pages:
            resume_text += page.extract_text()

        # Chunk the text
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        chunks = text_splitter.split_text(resume_text)

        # Summarize the chunks
        summaries = []
        for chunk in chunks:
            summary = await ModalClient.llm([{"role": "user", "content": f"Summarize the key skills and experiences in this section of a resume:\n\n{chunk}"}])
            summaries.append(summary)
        
        final_summary = "\n".join(summaries)
        
        # Final combined summary
        resume_summary = await ModalClient.llm([{"role": "user", "content": f"Combine these summaries into a single, coherent overview of the candidate's skills and project history:\n\n{final_summary}"}])
        
        cl.user_session.set("resume_summary", resume_summary)
        await cl.Message(content=f"Thank you. I've reviewed the resume.").send()

    except Exception as e:
        await cl.Message(content=f"Sorry, I couldn't process the resume. Let's proceed without it. Error: {e}").send()
        cl.user_session.set("resume_summary", "")

    # Initialize state and start the interview
    initial_state = {
        "messages": [], 
        "llm_history": [], 
        "role": None, 
        "level": None, 
        "resume_summary": cl.user_session.get("resume_summary", ""),
        "question_count": 0, 
        "feedback_notes": [], 
        "pdf_report": None, 
        "message_type": "question",
        "project_questions_asked": 0,
        "technical_questions_asked": 0,
        "followup_questions_asked": 0,
        "consecutive_struggles": 0,
        "last_question_type": None,
        "requesting_hint": False,
        "topic_depth": 0,
        "current_topic": "technical"
    }
    
    res = await app_graph.ainvoke(initial_state)
    cl.user_session.set("state", res)
    
    text = res["messages"][0]
    audio = await ModalClient.tts(text)
    
    if audio:
        await cl.Message(content="", elements=[cl.Audio(name="greeting.wav", content=audio, display="inline", auto_play=True)]).send()

@cl.on_message
async def main(message: cl.Message):
    state = cl.user_session.get("state")
    user_text = ""
    
    # Audio Input Handling with UNIQUE FILENAMES
    if message.elements:
        loading = cl.Message(content="Listening...", author="System")
        await loading.send()
        
        # Use UUID to prevent file collisions between users
        unique_filename = f"temp_{uuid.uuid4()}.wav"
        
        with open(unique_filename, "wb") as f:
            with open(message.elements[0].path, "rb") as aud: f.write(aud.read())
            
        user_text = await ModalClient.stt(unique_filename)
        
        if os.path.exists(unique_filename): os.remove(unique_filename)
        await loading.remove()
    else:
        user_text = message.content
    
    if not user_text:
        await cl.Message(content="I couldn't hear you.").send()
        return

    # Handle hint request
    if user_text.lower().strip() == "hint":
        state["requesting_hint"] = True
    else:
        state["requesting_hint"] = False
        # State Updates
        if not state["role"]: state["role"] = user_text
        elif not state["level"]: state["level"] = "hard" if "hard" in user_text.lower() else ("easy" if "easy" in user_text.lower() else "medium")
        state["llm_history"].append({"role": "user", "content": user_text})
    
    # Agent Logic
    async with cl.Step(name="Thinking") as step:
        res = await app_graph.ainvoke(state)
        step.output = "Done"
    
    bot_text = res["messages"][-1]
    state = res
    cl.user_session.set("state", state)
    
    msg_type = res.get("message_type", "question")
    
    # Display progress
    if state.get("question_count", 0) > 1 and state.get("question_count", 0) <= MAX_QUESTIONS:
        prog = f"Q: {state['question_count']}/{MAX_QUESTIONS} | Topic: {state.get('current_topic', 'N/A').title()}"
        await cl.Message(content=f"📊 **Progress:** {prog}", author="System").send()
    
    # --- DISPLAY LOGIC ---
    if msg_type == "hint":
        await cl.Message(content=f"💡 **HINT:** {bot_text}").send()
    
    elif res.get("pdf_report"):
        audio = await ModalClient.tts("Here is your feedback report.")
        els = [cl.Pdf(name="report.pdf", content=res["pdf_report"], display="inline")]
        if audio: els.append(cl.Audio(name="end.wav", content=audio, display="inline", auto_play=True))
        await cl.Message(content="Interview Complete.", elements=els).send()
    
    else:
        audio = await ModalClient.tts(bot_text)
        if audio:
            await cl.Message(content="", elements=[cl.Audio(name="reply.wav", content=audio, display="inline", auto_play=True)]).send()