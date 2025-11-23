from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import io
import re

def clean_llm_response(text: str) -> str:
    """
    Cleans LLM output for TTS - removes prefixes, extracts single question.
    """
    if not text:
        return ""

    # Remove common prefixes
    patterns = [
        r"^(Assistant|AI|Interviewer|User|Candidate)\s*:\s*",
        r"^(Assistant|AI|Interviewer|User|Candidate)\s+-\s+",
        r"^\*\*(Assistant|AI|Interviewer|User|Candidate)\*\*\s*:\s*",
    ]
    for pattern in patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.MULTILINE)

    # Remove dialogue lines with labels
    lines = text.split('\n')
    clean_lines = [line for line in lines if not re.match(r'^\s*(User|Candidate|Assistant|AI|Interviewer)\s*:', line, re.IGNORECASE)]
    text = '\n'.join(clean_lines)

    # Extract first question/sentence until a question mark or sentence boundary
    sentences = re.split(r'([.!?])\s+', text)
    if len(sentences) > 0:
        first_sentence = sentences[0]
        if len(sentences) > 1 and sentences[1] in ['.', '!', '?']:
            first_sentence += sentences[1]
        text = first_sentence.strip()

    if text.count('?') > 1:
        text = text.split('?')[0] + '?'

    # Remove markdown decorations
    text = re.sub(r'[\*_]+', '', text)

    text = re.sub(r'\s+', ' ', text).strip()

    if not text or len(text) < 3:
        text = "Could you elaborate on that?"

    return text

def create_pdf_report(candidate_name, role, content):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"Interview Feedback: {candidate_name}", styles['Title']))
    story.append(Paragraph(f"Role: {role}", styles['Heading2']))
    story.append(Spacer(1, 12))

    for line in content.split('\n'):
        if line.strip().startswith('#'):
            story.append(Paragraph(line.replace('#', ''), styles['Heading3']))
        else:
            story.append(Paragraph(line, styles['BodyText']))
        story.append(Spacer(1, 6))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
