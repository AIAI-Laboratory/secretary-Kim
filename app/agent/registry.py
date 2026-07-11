from typing import Dict, List, Any
from google.genai import types
from app.agent.skills.base import BaseSkill
from app.agent.models import SkillContext, SkillResult

class SkillRegistry:
    """
    Registry managing the list of Agent skills.
    Allows registering new skills, retrieving the list of tool declarations for LLM, and dispatching requests to the appropriate skill.
    """
    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        """
        Register a skill into the system.
        """
        if skill.name in self._skills:
            raise ValueError(f"Skill with name '{skill.name}' already exists in Registry.")
        self._skills[skill.name] = skill

    def get_all_function_declarations(self) -> List[types.FunctionDeclaration]:
        """
        Collect and return the list of FunctionDeclaration from all registered skills.
        """
        declarations = []
        for skill in self._skills.values():
            declarations.extend(skill.get_function_declarations())
        return declarations

    def get_skill_descriptions(self) -> str:
        """
        Return a description string of available skills to append to the Agent's system prompt.
        """
        descriptions = []
        for skill in self._skills.values():
            descriptions.append(f"- {skill.name}: {skill.description}")
        return "\n".join(descriptions)

    async def dispatch(self, function_name: str, args: Dict[str, Any], context: SkillContext) -> SkillResult:
        """
        Search for which skill owns function_name and forward the execution to that skill.
        """
        for skill in self._skills.values():
            # Check if function_name matches any declaration of the skill
            declarations = skill.get_function_declarations()
            for decl in declarations:
                if decl.name == function_name:
                    return await skill.execute(function_name, args, context)
        
        return SkillResult(
            success=False,
            message=f"No skill found to handle function '{function_name}'."
        )
