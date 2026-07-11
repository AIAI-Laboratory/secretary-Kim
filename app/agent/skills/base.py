from abc import ABC, abstractmethod
from typing import Any, Dict, List
from google.genai import types

class BaseSkill(ABC):
    """
    Base class for all Agent Skills.
    To add a new feature, create a class that inherits from this BaseSkill.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Unique identifier name of the skill (e.g., 'music', 'event', 'weather').
        """
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """
        Brief description of the skill's functionality. The LLM can use this description
        to understand the general capability of the skill.
        """
        pass

    @abstractmethod
    def get_function_declarations(self) -> List[types.FunctionDeclaration]:
        """
        Return the list of tool/function declarations provided by this skill.
        These declarations will be sent to Gemini to perform Function Calling.
        """
        pass

    @abstractmethod
    async def execute(self, function_name: str, args: Dict[str, Any], context: Any) -> Any:
        """
        Execute the function requested by the LLM.

        Args:
            function_name: The name of the function designated by the LLM.
            args: The arguments passed into the function as a dict.
            context: The object containing execution context information (Discord guild, user, channel, etc.).
        """
        pass
