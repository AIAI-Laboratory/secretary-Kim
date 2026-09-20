"""Registry and dispatcher for AI Agent skills."""

from typing import Any

from google.genai import types

from app.agent.models import SkillContext, SkillResult
from app.agent.skills.base import BaseSkill


class SkillRegistry:
    """Registry managing the list of Agent skills.

    Allows registering new skills, retrieving the list of tool declarations for LLM,
    and dispatching requests to the appropriate skill.
    """

    def __init__(self) -> None:
        """Initialize an empty skill registry."""
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        """Register a skill into the system.

        Args:
            skill (BaseSkill): Skill instance to register.

        Raises:
            ValueError: If a skill with the same name is already registered.
        """
        if skill.name in self._skills:
            raise ValueError(
                f"Skill with name '{skill.name}' already exists in Registry."
            )
        self._skills[skill.name] = skill

    def get_all_function_declarations(self) -> list[types.FunctionDeclaration]:
        """Collect and return the list of FunctionDeclaration from all registered skills.

        Returns:
            list[types.FunctionDeclaration]: All declarations for Gemini function calling.
        """
        declarations = []
        for skill in self._skills.values():
            declarations.extend(skill.get_function_declarations())
        return declarations

    def get_skill_descriptions(self) -> str:
        """Return a description string of available skills to append to the Agent's system prompt.

        Returns:
            str: Multi-line string describing each skill's capabilities.
        """
        descriptions = []
        for skill in self._skills.values():
            descriptions.append(f"- {skill.name}: {skill.description}")
        return "\n".join(descriptions)

    async def dispatch(
        self, function_name: str, args: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        """Search for which skill owns function_name and forward execution to that skill.

        Args:
            function_name (str): The name of the function to execute.
            args (dict[str, Any]): The arguments parsed by LLM.
            context (SkillContext): Context object containing runtime info.

        Returns:
            SkillResult: The execution result from the handling skill.
        """
        for skill in self._skills.values():
            # Check if function_name matches any declaration of the skill
            declarations = skill.get_function_declarations()
            for decl in declarations:
                if decl.name == function_name:
                    return await skill.execute(function_name, args, context)

        return SkillResult(
            success=False,
            message=f"No skill found to handle function '{function_name}'.",
        )
