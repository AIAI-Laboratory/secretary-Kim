# AI Agent Framework Documentation

This document describes the design, components, and extensibility patterns of the **Secretary Kim AI Agent Framework**. 

The framework is built using the **Agent-Skill Architecture**, allowing modular development where new features/services can be plugged in as "Skills" without touching the core orchestration logic.

---

## 1. Architectural Overview

```
                        +----------------------+
                        |   Discord User Input |
                        +----------+-----------+
                                   |
                                   v
                        +----------+-----------+
                        |  Presentation Layer  |
                        |     (AgentCog)       |
                        +----------+-----------+
                                   | (AgentRequest)
                                   v
                        +----------+-----------+
                        |    🧠 KimAgent Core  |<=======> [Memory Engine]
                        +----------+-----------+
                                   |
                     +-------------+-------------+
                     | (Collect Context & Tools) |
                     v                           v
             +-------+-------+           +-------+-------+
             | ContextEngine |           | SkillRegistry |
             +-------+-------+           +-------+-------+
                     |                           | (Tool Declarations)
                     v                           v
             +-----------------------------------+-------+
             |         LLM Client (Gemini API)           |
             |       (Matches prompt to function)        |
             +-----------------------+-------------------+
                                     | (Function Call / Arguments)
                                     v
                        +------------+-----------+
                        |     Skill Registry     |
                        +------------+-----------+
                                     | (Dispatch)
                                     v
                        +------------+-----------+
                        |    Specific Skill      |
                        |  (e.g., MusicSkill)    |
                        +------------+-----------+
```

### Flow of Execution
1. **Request Reception**: The presentation layer (e.g., Discord Cog) receives a natural language query from the user and wraps it in an `AgentRequest`.
2. **Context Enrichment**: The `ContextEngine` builds state, user, time, and environment context (`SkillContext`).
3. **Tool Aggregation**: The `SkillRegistry` gathers all registered skill capabilities represented as Gemini `FunctionDeclaration` objects.
4. **LLM Inference**: The LLM Client issues a request with the system prompts, active context, and available function declarations.
5. **Dispatching**:
   - If the LLM selects a function, the `SkillRegistry` dispatches it to the respective `BaseSkill` execution handler.
   - If no function is matched, the agent handles it as a general chat or fallback response.
6. **Execution**: The chosen skill processes the request and returns a standardized `SkillResult` back to the presentation layer.

---

## 2. Core Components

### `BaseSkill`
The base class for all capability modules. Any new capability (e.g., calendar integration, music control, task creation) must implement this interface.
* **Path**: [app/agent/skills/base.py](file:///home/myduy/Workspace/projects/secretary-Kim/app/agent/skills/base.py)

### `AgentModels`
Pydantic data models enforcing strict types across the orchestration layer.
* **Path**: [app/agent/models.py](file:///home/myduy/Workspace/projects/secretary-Kim/app/agent/models.py)
* **Key Models**:
  - `AgentRequest`: Representation of raw text input and platform-specific objects (like Discord Guild/Member).
  - `SkillContext`: Evaluated environmental variables passed during execution.
  - `SkillResult`: Execution state returned by skills, defining whether client-side interactive elements (Embeds, UI Views) or confirmations are required.
  - `AgentResponse`: Final packaged payload back to the gateway.

### `SkillRegistry`
Maintains a dictionary of registered skills. Acts as a registry during initialization and handles routing at runtime.
* **Path**: [app/agent/registry.py](file:///home/myduy/Workspace/projects/secretary-Kim/app/agent/registry.py)

### `ContextEngine`
Prepares environment metadata, standardizes localized date/time representation, and generates core instructions for the LLM.
* **Path**: [app/agent/context.py](file:///home/myduy/Workspace/projects/secretary-Kim/app/agent/context.py)

---

## 3. Creating a New Skill (Step-by-Step)

To add a new service or capability to Secretary Kim:

### Step 3.1: Define the Skill Class
Create a new file in `app/agent/skills/your_skill_skill.py` subclassing `BaseSkill`.

```python
from typing import Any, Dict, List
from google.genai import types
from app.agent.skills.base import BaseSkill
from app.agent.models import SkillContext, SkillResult

class WeatherSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "weather"

    @property
    def description(self) -> str:
        return "Provides current weather updates and forecasts for specified locations."

    def get_function_declarations(self) -> List[types.FunctionDeclaration]:
        return [
            types.FunctionDeclaration(
                name="get_current_weather",
                description="Retrieve the current weather conditions for a city.",
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "location": {
                            "type": "STRING",
                            "description": "City name and optional country (e.g. 'Hanoi, Vietnam')"
                        }
                    },
                    "required": ["location"]
                }
            )
        ]

    async def execute(self, function_name: str, args: Dict[str, Any], context: SkillContext) -> SkillResult:
        if function_name == "get_current_weather":
            location = args.get("location")
            # Implement integration with weather APIs / business service here
            result_msg = f"The weather in {location} is currently sunny, 32°C."
            return SkillResult(success=True, message=result_msg)
            
        return SkillResult(success=False, message=f"Action '{function_name}' not supported.")
```

### Step 3.2: Register the Service & Skill
Instantiate the service and skill, then add it to the `SkillRegistry` inside your Dependency Injection container (`container.py`):

```python
# app/core/container.py
from app.agent.registry import SkillRegistry
from app.agent.skills.weather_skill import WeatherSkill

class Container(containers.DeclarativeContainer):
    # Registry
    skill_registry = providers.Singleton(SkillRegistry)

    # Weather Skill
    weather_skill = providers.Singleton(
        WeatherSkill,
        # Inject dependencies or APIs here
    )

# In your startup/initialization sequence (main.py):
registry = container.skill_registry()
registry.register(container.weather_skill())
```

---

## 4. Design Guidelines & Best Practices

1. **Keep Skills Stateless**: Maintain state inside backend services or dedicated memory layers, never inside the Skill object itself.
2. **Explicit Descriptions**: Write accurate, conversational descriptions for both your Skill class and parameters. The LLM uses these descriptions to decide which function to route to.
3. **Time Sensitivity**: Always leverage `context.current_time_info` inside your skill logic or calculations when interpreting relative periods like "next Friday" or "tomorrow evening".
4. **Fallback Handling**: Gracefully handle missing parameters by returning an instructive error message or asking the user for clarification.
