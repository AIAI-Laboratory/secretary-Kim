---
name: create_kim_skill
description: Guidelines and instructions for creating new agent skills for the Secretary Kim Agent-Skill framework.
---

# Instruction for Creating a New Skill

When the user asks you to add a new service or capability to the "Secretary Kim" bot (e.g. reminding users, checking weather, fetching documents, skipping music), follow this protocol to structure it into the Agent-Skill architecture.

## Step 1: Validate Prerequisites
Ensure you are using the Clean Architecture project structure:
- Core business/integration logic lives in `app/services/`
- Skill mapping & LLM declarations live in `app/agent/skills/`

## Step 2: Implement the Skill Class
Create a new file in `app/agent/skills/{skill_name}_skill.py` extending `BaseSkill`.

Use this code template:

```python
from typing import Any, Dict, List
from google.genai import types
from app.agent.skills.base import BaseSkill
from app.agent.models import SkillContext, SkillResult

class NewFeatureSkill(BaseSkill):
    def __init__(self, business_service: Any):
        # Inject the underlying service that handles raw business logic
        self.service = business_service

    @property
    def name(self) -> str:
        return "your_skill_name"

    @property
    def description(self) -> str:
        return "Brief description explaining what this skill does so LLM understands its capability"

    def get_function_declarations(self) -> List[types.FunctionDeclaration]:
        return [
            types.FunctionDeclaration(
                name="execute_action",
                description="Detail description of when the LLM should invoke this function.",
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "param_name": {
                            "type": "STRING",
                            "description": "Clarifying instructions for the model on how to extract this value."
                        }
                    },
                    "required": ["param_name"]
                }
            )
        ]

    async def execute(self, function_name: str, args: Dict[str, Any], context: SkillContext) -> SkillResult:
        if function_name == "execute_action":
            param = args.get("param_name")
            try:
                # Call business logic service
                result = await self.service.run(param)
                return SkillResult(
                    success=True,
                    message=f"Successfully executed: {result}"
                )
            except Exception as e:
                return SkillResult(
                    success=False,
                    message=f"Error executing action: {str(e)}"
                )
                
        return SkillResult(
            success=False,
            message=f"Action '{function_name}' not supported by NewFeatureSkill."
        )
```

## Step 3: Wire in Container and Startup
1. Open `app/core/container.py` and register the business service and the skill provider:
   ```python
   your_service = providers.Singleton(YourService)
   your_skill = providers.Singleton(YourSkill, business_service=your_service)
   ```
2. Open `app/main.py` or the initialization hook and register the skill in the main `SkillRegistry`:
   ```python
   registry = container.skill_registry()
   registry.register(container.your_skill())
   ```
