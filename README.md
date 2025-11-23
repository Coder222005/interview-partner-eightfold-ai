![Interview Planner](image.png)

# Interview Planner Changelog

This document summarizes recent changes made to the application code.

---

### 1. Added Question Distribution Configuration

*   **File:** `config.py`
*   **Reason:** The application was crashing on startup due to an `ImportError`. The `graph.py` file required percentage configurations that were missing.
*   **Change:** Added `PROJECT_PERCENTAGE`, `TECHNICAL_PERCENTAGE`, and `FOLLOWUP_PERCENTAGE` variables to define the distribution of question types.

```python
# config.py

# ... existing content ...

# Determines the rough percentage of questions per category
PROJECT_PERCENTAGE = 0.4
TECHNICAL_PERCENTAGE = 0.4
FOLLOWUP_PERCENTAGE = 0.2
```

---

### 2. Fixed Incomplete Feedback Reports

*   **File:** `prompts.py`
*   **Reason:** The AI was often generating an incomplete feedback report, usually stopping after the "Executive Summary".
*   **Change:** Modified the `FEEDBACK_GENERATOR_PROMPT` to use a "fill-in-the-blanks" template. This guides the AI to complete all required sections of the report.

---

### 3. Fixed Garbled AI Responses

*   **File:** `graph.py`
*   **Reason:** On the first question after the user's introduction, the AI would sometimes respond with a garbled "series of communications" instead of a clean question.
*   **Change:** Limited the conversation history sent to the AI to the last 4 messages. This prevents the AI from getting confused by the full chat history.
*   **Location:** `node_interview_turn` function.

```python
# Before
messages = [{"role": "system", "content": prompt}] + state["llm_history"]

# After
messages = [{"role": "system", "content": prompt}] + state["llm_history"][-4:]
```

---

### 4. Implemented "Hint on Demand" Feature

*   **Files:** `app.py`, `graph.py`
*   **Reason:** To allow the user to explicitly ask for a hint.
*   **Changes:**
    1.  In `app.py`: Added logic to detect if the user's input is "hint" and set a `requesting_hint` flag in the application state.
    2.  In `graph.py`: Added logic in the `node_interview_turn` function to check for the `requesting_hint` flag and generate a hint for the last question if present.

---

### 5. Added Fallback for Null Feedback

*   **File:** `graph.py`
*   **Reason:** In case of an error, the feedback generation could result in a null or empty report.
*   **Change:** Added a check in the `node_feedback` function. If the generated report is empty or too short, it creates a fallback PDF containing the raw interview notes.

---

### 6. Fixed Hint Feature Routing

*   **File:** `graph.py`
*   **Reason:** The hint feature was not working during the initial setup phase (e.g., when being asked for role/difficulty).
*   **Change:** Updated the `master_router` function to prioritize checking for a hint request *before* checking for the setup steps. This ensures hint requests are always handled immediately.

```python
# graph.py - master_router function

# Before
def master_router(state: AgentState):
    if not state.get("role"): 
        return "ask_role"
    # ...

# After
def master_router(state: AgentState):
    if state.get("requesting_hint"):
        return "interview_turn"
    if not state.get("role"): 
        return "ask_role"
    # ...
```