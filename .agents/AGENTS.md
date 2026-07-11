# Workspace Rules: Secretary Kim AI Agent Framework

As an AI development assistant working on the **secretary-Kim** repository, you MUST adhere to the following architectural guidelines and rules at all times.

---

## 1. Core Architectural Constraints

- **Clean Architecture Principles**: Maintain a strict separation of layers:
  - `presentation/`: Handles IO and incoming platform events (Discord bots, commands, hooks). No business or LLM orchestrating logic should be written here.
  - `agent/`: Houses the core brain, LLM orchestration client, models, and skill layers.
  - `services/`: Houses pure business logic and third-party integrations (e.g., Music stream retrievers, database models).
  - `domain/`: Contains interfaces, base classes, and core entity objects.

- **No Directly Scattered LLM Parsers**:
  Do NOT add standalone LLM content-generation scripts or hardcode Gemini Clients in presentation cogs/controllers. All interactions with the Gemini API for natural language execution must route through the central `KimAgent` core and the `SkillRegistry` mapping logic.

---

## 2. Rules for Developing New Capabilities

Whenever you are tasked with adding a new feature, service, or integration (e.g., Spotify control, Google Calendar, Reminder system):

1. **Implement as a Skill**:
   - You must write the capability as a new module within `app/agent/skills/`.
   - Your skill class MUST inherit from `BaseSkill` (`app/agent/skills/base.py`).
   - Implement `name`, `description`, `get_function_declarations()`, and `execute()` methods.

2. **Leverage Gemini Function Calling**:
   - Instead of manual regex, intent classifiers, or multi-step prompt classification, represent all capabilities of the new feature as `FunctionDeclaration` specs.
   - Write highly descriptive parameter descriptions to ensure the Gemini model routes correctly and provides validated payloads.

3. **Standardize Data Flow**:
   - Inputs to the skill must be encapsulated in a `SkillContext` object.
   - Outputs must return a `SkillResult` with structural flags (`success`, `message`, `embed`, `view`, `needs_confirmation`, `data`).

4. **Integration via Dependency Injection**:
   - Register your new skill service and the skill instance inside the `Container` (`app/core/container.py`).
   - Wire registration into the startup sequence of the bot.

---

## 3. General Code Style

- Keep type hints comprehensive on all interface signatures.
- Keep system prompts localized. Use the localized timezone (+07:00 / GMT+7) for all relative dates.
- Preserves existing docstrings, logs, and error configurations unless refactoring is requested.
