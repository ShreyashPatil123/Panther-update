"""Smart model routing — maps task categories to optimal NVIDIA NIM models."""
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Optional


class TaskCategory(str, Enum):
    """Supported task categories for smart model routing."""
    CHAT = "chat"
    CODE = "code"
    REASONING = "reasoning"
    VISION = "vision"
    CREATIVE = "creative"
    DOCUMENT = "document"
    AGENTIC = "agentic"
    TRANSLATION = "translation"
    SAFETY = "safety"


@dataclass
class TaskPreset:
    """Configuration for a task-specific model preset."""
    category: TaskCategory
    emoji: str
    label: str
    description: str
    model: str
    fast_model: str
    system_prompt: str
    tooltip: str = ""

    def __post_init__(self):
        if not self.tooltip:
            self.tooltip = f"{self.description}\nModel: {self.model}"


# ── Best-model presets (based on Perplexity research, Feb 2026) ──────────────

TASK_PRESETS: Dict[TaskCategory, TaskPreset] = {
    TaskCategory.CHAT: TaskPreset(
        category=TaskCategory.CHAT,
        emoji="💬",
        label="Chat",
        description="General conversation, Q&A, everyday assistance",
        model="deepseek-ai/deepseek-v3.2",
        fast_model="meta/llama-3.2-3b-instruct",
        system_prompt=(
            "You are a friendly, helpful, and concise AI assistant. "
            "Provide clear answers. Use markdown formatting when helpful. "
            "Be conversational but informative."
        ),
    ),
    TaskCategory.CODE: TaskPreset(
        category=TaskCategory.CODE,
        emoji="💻",
        label="Code",
        description="Code generation, debugging, code review, refactoring",
        model="qwen/qwen3-coder-480b-a35b-instruct",
        fast_model="mistralai/mamba-codestral-7b-v0.1",
        system_prompt=(
            "You are an expert software engineer. Write clean, efficient, "
            "well-documented code. Always include error handling. "
            "Explain your approach briefly before writing code. "
            "Use appropriate language idioms and best practices."
        ),
    ),
    TaskCategory.REASONING: TaskPreset(
        category=TaskCategory.REASONING,
        emoji="🧠",
        label="Reasoning",
        description="Math, logic, chain-of-thought, analytical problems",
        model="qwen/qwq-32b",
        fast_model="mistralai/mathstral-7b-v0.1",
        system_prompt=(
            "You are a rigorous analytical thinker. Break down problems "
            "step by step. Show your reasoning clearly. Verify your answers. "
            "For math, show all work. For logic, state assumptions explicitly."
        ),
    ),
    TaskCategory.VISION: TaskPreset(
        category=TaskCategory.VISION,
        emoji="👁️",
        label="Vision",
        description="Image analysis, screenshots, diagrams, visual Q&A",
        model="meta/llama-3.2-90b-vision-instruct",
        fast_model="meta/llama-3.2-11b-vision-instruct",
        system_prompt=(
            "You are a visual analysis expert. Describe what you see in detail. "
            "Identify text, objects, layouts, and relationships in images. "
            "Provide structured observations."
        ),
    ),
    TaskCategory.CREATIVE: TaskPreset(
        category=TaskCategory.CREATIVE,
        emoji="✍️",
        label="Creative",
        description="Stories, poetry, marketing copy, creative writing",
        model="mistralai/mistral-large-3-675b-instruct-2512",
        fast_model="google/gemma-2-9b-it",
        system_prompt=(
            "You are a talented creative writer with a vivid imagination. "
            "Write engaging, original content with strong voice and style. "
            "Use literary techniques like metaphor, rhythm, and imagery. "
            "Adapt tone to the request — formal for business, playful for stories."
        ),
    ),
    TaskCategory.DOCUMENT: TaskPreset(
        category=TaskCategory.DOCUMENT,
        emoji="📄",
        label="Document",
        description="Text extraction, summarization, document analysis",
        model="meta/llama-3.1-405b-instruct",
        fast_model="nvidia/llama-3.1-nemotron-nano-8b-v1",
        system_prompt=(
            "You are a document analysis specialist. Extract key information "
            "accurately. Summarize concisely while preserving critical details. "
            "Use structured formats (bullet points, tables) for clarity. "
            "Quote relevant passages when appropriate."
        ),
    ),
    TaskCategory.AGENTIC: TaskPreset(
        category=TaskCategory.AGENTIC,
        emoji="🤖",
        label="Agentic",
        description="Multi-step planning, tool use, complex task execution",
        model="moonshotai/kimi-k2-instruct",
        fast_model="meta/llama-3.2-1b-instruct",
        system_prompt=(
            "You are an autonomous AI agent skilled at breaking complex tasks "
            "into actionable steps. Plan before executing. Be precise with "
            "tool calls and parameters. Report progress at each step. "
            "Handle errors gracefully and adapt your plan."
        ),
    ),
    TaskCategory.TRANSLATION: TaskPreset(
        category=TaskCategory.TRANSLATION,
        emoji="🌐",
        label="Translate",
        description="Multilingual translation between languages",
        model="nvidia/riva-translate-4b-instruct-v1.1",
        fast_model="nvidia/nemotron-mini-4b-instruct",
        system_prompt=(
            "You are a professional translator. Translate accurately while "
            "preserving meaning, tone, and cultural nuance. If the source "
            "language is ambiguous, ask for clarification. Provide the "
            "translated text directly without excessive commentary."
        ),
    ),
    TaskCategory.SAFETY: TaskPreset(
        category=TaskCategory.SAFETY,
        emoji="🛡️",
        label="Safety",
        description="Content moderation, safety checks, policy compliance",
        model="meta/llama-guard-4-12b",
        fast_model="nvidia/llama-3.1-nemoguard-8b-content-safety",
        system_prompt=(
            "You are a content safety analyst. Evaluate content against "
            "safety policies. Identify potential risks including: violence, "
            "hate speech, self-harm, illegal activity, and PII exposure. "
            "Provide clear verdicts with reasoning."
        ),
    ),
}


def get_task_preset(category: TaskCategory) -> TaskPreset:
    """Get the preset configuration for a task category."""
    return TASK_PRESETS[category]


def get_all_presets() -> Dict[TaskCategory, TaskPreset]:
    """Get all task presets for UI rendering."""
    return TASK_PRESETS


def get_category_by_name(name: str) -> Optional[TaskCategory]:
    """Look up a TaskCategory by its string value."""
    try:
        return TaskCategory(name)
    except ValueError:
        return None
