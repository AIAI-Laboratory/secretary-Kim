"""Business service for managing tasks, assignments, and statuses."""

from typing import Any

from app.core.logger import get_logger

logger = get_logger(__name__)


class TaskService:
    """Pure business service for managing tasks and todos.

    Handles database persistence, assignment, and status updates.
    """

    def __init__(self) -> None:
        """Initialize in-memory task repository."""
        self._tasks: list[dict[str, Any]] = []
        self._next_id: int = 1

    async def create_task(
        self,
        title: str,
        description: str | None = None,
        assignee_id: str | None = None,
        assignee_name: str | None = None,
        due_date: str | None = None,
    ) -> dict[str, Any]:
        """Create a new task in the registry.

        Args:
            title (str): Title or summary of the task.
            description (str | None): Detailed description. Defaults to None.
            assignee_id (str | None): Discord ID of the assigned user. Defaults to None.
            assignee_name (str | None): Display name of the assigned user. Defaults to None.
            due_date (str | None): ISO string deadline. Defaults to None.

        Returns:
            dict[str, Any]: Newly created task record dictionary.
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

    async def get_tasks(self, assignee_id: str | None = None) -> list[dict[str, Any]]:
        """Retrieve all tasks or tasks assigned to a specific user.

        Args:
            assignee_id (str | None): Optional filter for assignee ID. Defaults to None.

        Returns:
            list[dict[str, Any]]: List of matching task records.
        """
        if assignee_id:
            return [t for t in self._tasks if t["assignee_id"] == assignee_id]
        return self._tasks

    async def update_task_status(
        self, task_id: int, status: str
    ) -> dict[str, Any] | None:
        """Update the status of a task.

        Args:
            task_id (int): Identifier of the task to update.
            status (str): New status string (e.g. pending, completed).

        Returns:
            dict[str, Any] | None: Updated task dictionary if found, else None.
        """
        for task in self._tasks:
            if task["id"] == task_id:
                task["status"] = status
                logger.info(f"Updated task {task_id} status to: {status}")
                return task
        return None
