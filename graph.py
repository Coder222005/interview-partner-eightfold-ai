from typing import TypedDict, List, Dict
from langgraph.graph import StateGraph, END
from api_client import ModalClient
from prompts import FEEDBACK_GENERATOR_PROMPT, SYSTEM_PROMPT_INTERVIEWER
from utils import create_pdf_report, clean_llm_response
from config import MAX_QUESTIONS, PROJECT_PERCENTAGE, TECHNICAL_PERCENTAGE
import json
import math

class AgentState(TypedDict):
    messages: List[str]
    llm_history: List[Dict]
    role: str
    level: str
    resume_summary: str
    question_count: int
    feedback_notes: List[str]
    pdf_report: bytes
    message_type: str
    project_questions_asked: int
    technical_questions_asked: int
    followup_questions_asked: int
    consecutive_struggles: int
    last_question_type: str
    topic_depth: int
    current_topic: str
    requesting_hint: bool 

async def node_ask_role(state: AgentState):
    msg = "Hello! I am your AI Interviewer. What role are you applying for?"
    return {
        "messages": [msg], 
        "llm_history": [{"role": "assistant", "content": msg}], 
        "question_count": 0, 
        "feedback_notes": [], 
        "pdf_report": None, 
        "level": None, 
        "message_type": "question",
        "project_questions_asked": 0,
        "technical_questions_asked": 0,
        "followup_questions_asked": 0,
        "consecutive_struggles": 0,
        "topic_depth": 0,
        "current_topic": "technical",
        "resume_summary": state.get("resume_summary", "")
    }

async def node_ask_level(state: AgentState):
    msg = "Choose your difficulty: Easy, Medium, or Hard."
    return {
        "messages": state.get("messages", []) + [msg],
        "llm_history": state["llm_history"] + [{"role": "assistant", "content": msg}], 
        "message_type": "question"
    }

async def node_ask_bio(state: AgentState):
    msg = f"Great. Let's begin the {state.get('level', 'medium')} interview for {state.get('role', 'candidate')}. Please introduce yourself and mention your key projects."
    return {
        "messages": state.get("messages", []) + [msg],
        "llm_history": state["llm_history"] + [{"role": "assistant", "content": msg}], 
        "question_count": 1, 
        "message_type": "question"
    }

async def node_interview_turn(state: AgentState):
    current_q_count = state.get("question_count", 1)
    topic_depth = state.get("topic_depth", 0)
    level = state.get("level", "medium").lower()
    new_notes = state.get("feedback_notes", [])
    
    # --- 0. INTENT CHECK ---
    if len(state["llm_history"]) > 0 and state["llm_history"][-1]["role"] == "user":
        last_user_input = state["llm_history"][-1]["content"]
        if len(last_user_input) > 5:
            intent = await ModalClient.check_intent(last_user_input)
            if "OFF_TOPIC" in intent:
                warning_msg = "Let's stay focused on the interview. Please answer the previous question."
                return {
                    "messages": state.get("messages", []) + [warning_msg],
                    "llm_history": state["llm_history"] + [{"role": "assistant", "content": warning_msg}],
                    "message_type": "hint",
                    "question_count": current_q_count 
                }

    # --- 1. Analysis & Probing Logic ---
    should_probe = False
    is_struggling = False
    consecutive_struggles = state.get("consecutive_struggles", 0)
    
    if len(state["llm_history"]) >= 2 and current_q_count > 1:
        last_q = state["llm_history"][-2]["content"]
        last_a = state["llm_history"][-1]["content"]
        
        # Only analyze if we are deep enough into the interview
        if "introduce" not in last_q.lower() and current_q_count > 2:
            anl = await ModalClient.analyze(last_q, last_a, level)
            try:
                # Robust cleaning for JSON
                anl_cleaned = anl.replace("```json", "").replace("```", "").strip()
                aj = json.loads(anl_cleaned)
                
                is_struggling = aj.get("is_struggling", False)
                should_probe = aj.get("should_probe", False)
                
                if is_struggling: consecutive_struggles += 1
                else: consecutive_struggles = 0
                
                new_notes.append(f"Q: {last_q}\nA: {last_a}\nRating: {aj.get('rating')}")
            except:
                new_notes.append(f"Q: {last_q}\nA: {last_a}")
        else:
            new_notes.append(f"Intro: {last_a}")

    # --- 2. Decision Engine ---
    project_count = state.get("project_questions_asked", 0)
    technical_count = state.get("technical_questions_asked", 0)
    project_target = math.ceil(MAX_QUESTIONS * PROJECT_PERCENTAGE)
    technical_target = math.ceil(MAX_QUESTIONS * TECHNICAL_PERCENTAGE)

    next_question_type = state.get("current_topic", "technical")
    phase = ""
    message_type = "question"
    question_increment = 1
    
    # CASE A: Hint (Struggling or Requested)
    if (is_struggling and consecutive_struggles >= 2) or state.get("requesting_hint"):
        phase = "Hint. The candidate is struggling or asked for a hint. Provide a brief, conceptual hint about the PREVIOUS question. Do NOT give the answer. End by asking the candidate to try answering again."
        message_type = "hint"
        question_increment = 0 # Do not move to next question yet
        consecutive_struggles = 0 # Reset struggle counter to avoid infinite hint loop
    
    # CASE B: Standard Flow (Only if NOT giving a hint)
    else:
        if current_q_count == 2:
            phase = "Project Deep-Dive. Ask one specific question about a project from the candidate's intro or resume."
            next_question_type = "project"
        elif project_count < project_target:
            if not is_struggling:
                phase = "Project Experience. Ask about a new, DIFFERENT project mentioned in the resume or intro."
            else:
                phase = "Project Deep-Dive. Go deeper into the project currently being discussed."
            next_question_type = "project"
        elif technical_count < technical_target:
            phase = "Core Technical Skills. Ask a fundamental question based on the candidate's role and resume."
            next_question_type = "technical"
        else:
            phase = f"Follow-up. Ask a relevant technical follow-up question for a {state.get('role')}."
            next_question_type = "followup"

    # --- 3. Generation ---
    resume_context = state.get('resume_summary', 'Not provided')
    full_context = f"Difficulty: {level}\nCandidate Resume Summary: {resume_context}"
    
    system_prompt = SYSTEM_PROMPT_INTERVIEWER.format(
        role=state['role'], 
        phase=phase, 
        context=full_context
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    for msg in state["llm_history"][-4:]: messages.append(msg)
        
    response_text = await ModalClient.llm(messages, max_tokens=60) 
    response_text = clean_llm_response(response_text)
    if not response_text: response_text = "Could you elaborate?"

    # --- 4. Update Counters ---
    project_count = state.get("project_questions_asked", 0)
    technical_count = state.get("technical_questions_asked", 0)
    followup_count = state.get("followup_questions_asked", 0)

    if message_type == "question":
        if next_question_type == "project": project_count += 1
        elif next_question_type == "technical": technical_count += 1
        elif next_question_type == "followup": followup_count += 1

    return {
        "messages": state.get("messages", []) + [response_text],
        "llm_history": state["llm_history"] + [{"role": "assistant", "content": response_text}],
        "question_count": current_q_count + question_increment,
        "feedback_notes": new_notes,
        "message_type": message_type,
        "consecutive_struggles": consecutive_struggles,
        "topic_depth": topic_depth,
        "current_topic": next_question_type,
        "last_question_type": state.get("current_topic"),
        "project_questions_asked": project_count,
        "technical_questions_asked": technical_count,
        "followup_questions_asked": followup_count
    }

async def node_feedback(state: AgentState):
    notes_str = "\n".join(state["feedback_notes"])
    full_notes = f"Role: {state.get('role')}\n{notes_str}"
    
    feedback_messages = [{"role": "user", "content": FEEDBACK_GENERATOR_PROMPT.format(notes=full_notes)}]
    report = await ModalClient.llm(feedback_messages, max_tokens=2500)
    
    if "Here is" in report: report = report.split(":", 1)[-1].strip()
    pdf = create_pdf_report("Candidate", state.get("role"), report)
    
    return {
        "messages": state.get("messages", []) + ["Interview complete. Here is your report."], 
        "pdf_report": pdf, 
        "message_type": "report"
    }

def master_router(state: AgentState):
    if state.get("pdf_report"): return END
    
    if state.get("requesting_hint"): return "interview_turn"
    if not state.get("role"): return "ask_role"
    if not state.get("level"): return "ask_level"
    if state.get("question_count", 0) == 0: return "ask_bio"
    if state.get("question_count", 0) > MAX_QUESTIONS: return "feedback"
    return "interview_turn"

workflow = StateGraph(AgentState)
workflow.add_node("ask_role", node_ask_role)
workflow.add_node("ask_level", node_ask_level)
workflow.add_node("ask_bio", node_ask_bio)
workflow.add_node("interview_turn", node_interview_turn)
workflow.add_node("feedback", node_feedback)

workflow.set_conditional_entry_point(master_router, 
    {"ask_role": "ask_role", "ask_level": "ask_level", "ask_bio": "ask_bio", 
     "interview_turn": "interview_turn", "feedback": "feedback", END: END})

workflow.add_edge("ask_role", END)
workflow.add_edge("ask_level", END)
workflow.add_edge("ask_bio", END)
workflow.add_edge("interview_turn", END)
workflow.add_edge("feedback", END)

app_graph = workflow.compile()