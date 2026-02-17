"""Task Planner - Multi-step task decomposition and execution tracking."""
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional
from uuid import uuid4

from loguru import logger

if TYPE_CHECKING:
    from src.api.nvidia_client import NVIDIAClient


class TaskStatus(Enum):
    """Status of a task or step."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


@dataclass
class TaskStep:
    """A single step within a task."""

    description: str
    status: TaskStatus = TaskStatus.PENDING
    result: str = ""
    error: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def start(self):
        """Mark step as started."""
        self.status = TaskStatus.IN_PROGRESS
        self.started_at = datetime.now()

    def complete(self, result: str = ""):
        """Mark step as completed."""
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.completed_at = datetime.now()

    def fail(self, error: str = ""):
        """Mark step as failed."""
        self.status = TaskStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()

    @property
    def status_icon(self) -> str:
        """Get status icon for display."""
        icons = {
            TaskStatus.PENDING: "○",
            TaskStatus.IN_PROGRESS: "⟳",
            TaskStatus.COMPLETED: "✓",
            TaskStatus.FAILED: "✗",
            TaskStatus.PAUSED: "⏸",
        }
        return icons.get(self.status, "?")


@dataclass
class AgentTask:
    """A multi-step task being executed by the agent."""

    goal: str
    task_id: str = field(default_factory=lambda: str(uuid4())[:8])
    steps: List[TaskStep] = field(default_factory=list)
    current_step_index: int = 0
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    context: str = ""  # Additional context for execution

    @property
    def current_step(self) -> Optional[TaskStep]:
        """Get current step being worked on."""
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    @property
    def is_complete(self) -> bool:
        """Check if all steps are done."""
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)

    @property
    def progress_pct(self) -> int:
        """Get completion percentage."""
        if not self.steps:
            return 0
        completed = sum(1 for s in self.steps if s.status == TaskStatus.COMPLETED)
        return int((completed / len(self.steps)) * 100)

    def advance(self):
        """Move to next step."""
        self.current_step_index += 1
        if self.current_step_index >= len(self.steps):
            self.status = TaskStatus.COMPLETED
            self.completed_at = datetime.now()

    def get_summary(self) -> str:
        """Get human-readable task summary."""
        lines = [f"Task: {self.goal}", f"Status: {self.status.value} ({self.progress_pct}%)", ""]
        for i, step in enumerate(self.steps):
            prefix = "→ " if i == self.current_step_index else "  "
            lines.append(f"{prefix}{step.status_icon} {i + 1}. {step.description}")
            if step.result and step.status == TaskStatus.COMPLETED:
                lines.append(f"     Result: {step.result[:100]}")
            if step.error:
                lines.append(f"     Error: {step.error[:100]}")
        return "\n".join(lines)


class TaskPlanner:
    """Plans and tracks multi-step task execution."""

    def __init__(self):
        self.active_tasks: dict[str, AgentTask] = {}
        self.completed_tasks: list[AgentTask] = []
        logger.info("TaskPlanner initialized")

    async def create_plan(
        self,
        goal: str,
        nvidia_client: "NVIDIAClient",
        context: str = "",
    ) -> AgentTask:
        """Break down a goal into executable steps using LLM.

        Args:
            goal: The task goal to plan
            nvidia_client: LLM client for planning
            context: Additional context about available tools

        Returns:
            AgentTask with populated steps
        """
        logger.info(f"Creating plan for: {goal}")

        # Ask LLM to break down the task
        system_prompt = """You are a task planning assistant. Break down the user's goal into
specific, actionable steps. Each step should be clear and executable.

Format your response as a numbered list:
1. First step description
2. Second step description
3. ...

Keep steps concrete and achievable. Maximum 8 steps.
Do not include any other text, just the numbered list."""

        user_prompt = f"Goal: {goal}"
        if context:
            user_prompt += f"\n\nAvailable capabilities: {context}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        plan_text = ""
        try:
            async for chunk in nvidia_client.chat_completion(
                messages, stream=False, max_tokens=512, temperature=0.3
            ):
                plan_text = chunk
        except Exception as e:
            logger.error(f"LLM planning failed: {e}")
            # Fallback: single step
            plan_text = f"1. {goal}"

        # Parse steps from numbered list
        steps = self._parse_steps(plan_text)
        if not steps:
            steps = [TaskStep(description=goal)]

        task = AgentTask(
            goal=goal,
            steps=steps,
            context=context,
        )
        task.status = TaskStatus.PENDING

        self.active_tasks[task.task_id] = task
        logger.info(f"Created plan with {len(steps)} steps for task {task.task_id}")
        return task

    def _parse_steps(self, plan_text: str) -> List[TaskStep]:
        """Parse numbered steps from LLM response.

        Args:
            plan_text: LLM response with numbered steps

        Returns:
            List of TaskStep objects
        """
        steps = []
        lines = plan_text.strip().split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Match numbered items: "1.", "1)", "Step 1:", etc.
            match = re.match(r"^(?:step\s*)?(\d+)[.):\s]+(.+)$", line, re.IGNORECASE)
            if match:
                description = match.group(2).strip()
                if description:
                    steps.append(TaskStep(description=description))
            elif line and not line.startswith("#") and len(steps) == 0:
                # If no numbered format found, treat each non-empty line as a step
                steps.append(TaskStep(description=line))

        return steps

    def start_task(self, task: AgentTask):
        """Mark a task as started.

        Args:
            task: Task to start
        """
        task.status = TaskStatus.IN_PROGRESS
        if task.steps:
            task.steps[0].start()
        logger.info(f"Started task {task.task_id}: {task.goal}")

    def complete_step(self, task: AgentTask, result: str = ""):
        """Mark current step as completed and advance.

        Args:
            task: Task being executed
            result: Result of the completed step
        """
        if task.current_step:
            task.current_step.complete(result)

        task.advance()

        if not task.is_complete and task.current_step:
            task.current_step.start()

        if task.is_complete:
            self._finish_task(task)

    def fail_step(self, task: AgentTask, error: str = ""):
        """Mark current step as failed.

        Args:
            task: Task being executed
            error: Error message
        """
        if task.current_step:
            task.current_step.fail(error)
        task.status = TaskStatus.FAILED
        task.completed_at = datetime.now()
        self._finish_task(task)
        logger.error(f"Task {task.task_id} failed at step {task.current_step_index}: {error}")

    def pause_task(self, task_id: str):
        """Pause a running task.

        Args:
            task_id: ID of task to pause
        """
        task = self.active_tasks.get(task_id)
        if task and task.status == TaskStatus.IN_PROGRESS:
            task.status = TaskStatus.PAUSED
            logger.info(f"Paused task {task_id}")

    def cancel_task(self, task_id: str):
        """Cancel a task.

        Args:
            task_id: ID of task to cancel
        """
        task = self.active_tasks.pop(task_id, None)
        if task:
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now()
            self.completed_tasks.append(task)
            logger.info(f"Cancelled task {task_id}")

    def _finish_task(self, task: AgentTask):
        """Move task from active to completed.

        Args:
            task: Completed/failed task
        """
        self.active_tasks.pop(task.task_id, None)
        self.completed_tasks.append(task)
        # Keep only last 50 completed tasks
        if len(self.completed_tasks) > 50:
            self.completed_tasks = self.completed_tasks[-50:]

    def get_active_tasks(self) -> list[AgentTask]:
        """Get all active tasks."""
        return list(self.active_tasks.values())

    def get_all_tasks(self) -> list[AgentTask]:
        """Get all tasks (active + recently completed)."""
        return list(self.active_tasks.values()) + self.completed_tasks[-10:]
