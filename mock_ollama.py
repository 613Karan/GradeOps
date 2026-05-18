"""
Mock Ollama server for local development on low-memory machines.
Serves POST /api/chat on port 11434, mimicking the real Ollama API.
Handles both OCR (vision model) and grading (text model) based on model name.
Run instead of `ollama serve` when you don't have enough RAM for real models.
"""
import json
import re

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Mock Ollama")

MOCK_TRANSCRIPTS = {
    "math": (
        "The Arrhenius equation is given by:\n\n"
        "$$k = A e^{-E_a / RT}$$\n\n"
        "Where $k$ is the rate constant, $A$ is the pre-exponential factor, "
        "$E_a$ is the activation energy, $R = 8.314\\,\\text{J mol}^{-1}\\text{K}^{-1}$, "
        "and $T$ is temperature in Kelvin."
    ),
    "prose": (
        "Newton's second law states that the net force acting on an object is equal to "
        "the product of its mass and acceleration: F = ma. The unit of force is the Newton (N), "
        "which equals kg·m/s². For example, a 2 kg object accelerating at 5 m/s² "
        "experiences a net force of 10 N."
    ),
    "mixed": (
        "Newton's second law: $F = ma$, where $F$ is force in Newtons, $m$ is mass in kg, "
        "and $a$ is acceleration in m/s². This means that doubling the force doubles "
        "the acceleration for the same mass."
    ),
}


class ChatMessage(BaseModel):
    role: str
    content: object
    images: list[str] = []


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    format: str = ""


def _mock_classify(_prompt: str) -> str:
    return "mixed"


def _mock_ocr(prompt: str) -> str:
    if "math" in prompt.lower() or "latex" in prompt.lower():
        return MOCK_TRANSCRIPTS["math"]
    if "prose" in prompt.lower():
        return MOCK_TRANSCRIPTS["prose"]
    return MOCK_TRANSCRIPTS["mixed"]


def _mock_grade(user_content: str) -> str:
    max_marks_match = re.search(r"MAX MARKS:\s*([\d.]+)", user_content)
    max_marks = float(max_marks_match.group(1)) if max_marks_match else 5.0

    steps = re.findall(r"Step\s+(step_\w+):\s*(.+?)\s+\[([\d.]+)\s*pts\]", user_content)
    if not steps:
        steps = [("step_1", "Default step", str(max_marks))]

    step_results = []
    total_awarded = 0.0
    for step_id, description, points_str in steps:
        pts = float(points_str)
        awarded = round(pts * 0.8, 1)
        total_awarded += awarded
        step_results.append({
            "step_id": step_id,
            "description": description.strip(),
            "max_points": pts,
            "awarded_points": awarded,
            "verdict": "correct" if awarded >= pts else "partial",
            "justification": "Student demonstrated solid understanding with minor errors.",
        })

    return json.dumps({
        "step_results": step_results,
        "total_awarded": round(total_awarded, 1),
        "total_max": max_marks,
        "overall_justification": (
            "The student showed a solid understanding of the concepts. "
            "Most steps were completed correctly with minor errors in the final step."
        ),
    })


@app.post("/api/chat")
async def chat(req: ChatRequest):
    last_msg = req.messages[-1]
    prompt = str(last_msg.content)
    has_images = bool(getattr(last_msg, "images", []))

    # Classify request type by model name
    if "vl" in req.model or has_images:
        # Vision model — cover detection, question identification, content classification, or OCR
        if "cover" in prompt.lower() or "roll no" in prompt.lower():
            # Cover page detection — mock can't see images, always not a cover
            content = json.dumps({"is_cover": False, "roll_no": "", "name": "", "course": ""})
        elif "question_number" in prompt.lower() or "new question" in prompt.lower():
            # Question identification — mock can't see images, always treat as continuation
            # so all answer pages accumulate under auto-assigned q1 for local dev
            content = json.dumps({"question_number": None})
        elif "reply with exactly one word" in prompt.lower():
            content = _mock_classify(prompt)
        else:
            content = _mock_ocr(prompt)
    else:
        # Text model — grading
        content = _mock_grade(prompt)

    return {
        "model": req.model,
        "message": {"role": "assistant", "content": content},
        "done": True,
    }


@app.get("/api/tags")
async def tags():
    return {
        "models": [
            {"name": "qwen2.5:0.5b"},
            {"name": "qwen2.5vl:3b"},
            {"name": "qwen2.5:7b"},
        ]
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "mock-ollama"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=11434)
