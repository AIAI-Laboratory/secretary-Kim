from typing import Any, Dict, List, Optional
from app.core.logger import get_logger

logger = get_logger(__name__)


class TaskService:
    """
    Pure business service for managing tasks/todos.
    This service will handle database persistence, assignment, and status updates.
    No LLM or parsing logic here.
    """

    def __init__(self):
        # In-memory storage mock (replace with database models later)
        self._tasks: List[Dict[str, Any]] = []
        self._next_id: int = 1

    async def create_task(
        self,
        title: str,
        description: Optional[str] = None,
        assignee_id: Optional[str] = None,
        assignee_name: Optional[str] = None,
        due_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates a new task.
        """
        task = {
            "id": self._next_id,
            "title": title,
            "description": description or "",
            "assignee_id": assignee_id,
            "assignee_name": assignee_name,
            "due_date": due_date,
            "status": "pending",
        }
        self._tasks.append(task)
        self._next_id += 1
        logger.info(
            f"Created task {task['id']}: {title} (assigned to: {assignee_name})"
        )
        return task

    async def get_tasks(
        self, assignee_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves all tasks or tasks assigned to a specific user.
        """
        if assignee_id:
            return [t for t in self._tasks if t["assignee_id"] == assignee_id]
        return self._tasks

    async def update_task_status(
        self, task_id: int, status: str
    ) -> Optional[Dict[str, Any]]:
        """
        Updates the status of a task (e.g. pending, in_progress, completed).
        """
        for task in self._tasks:
            if task["id"] == task_id:
                task["status"] = status
                logger.info(f"Updated task {task_id} status to: {status}")
                return task
        return None
