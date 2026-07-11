from google import genai
from google.genai import types
from app.core.config import settings
from app.core.logger import get_logger
from app.agent.registry import SkillRegistry
from app.agent.context import ContextEngine
from app.agent.models import AgentRequest, AgentResponse

logger = get_logger(__name__)

class KimAgent:
    """
    Central brain of Secretary Kim.
    Orchestrates natural language requests using Gemini Function Calling.
    """
    def __init__(self, skill_registry: SkillRegistry, context_engine: ContextEngine):
        self.registry = skill_registry
        self.context_engine = context_engine
        
        # Initialize Gemini client using API Key from configuration
        if not settings.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY is not configured. The agent may not work.")
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY or None)

    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process request from user:
        1. Build business Context
        2. Gather all Function Declarations from Registry
        3. Call Gemini API
        4. Dispatch function call to corresponding Skill or return chitchat text
        """
        # 1. Create specific business context for Skill
        skill_context = await self.context_engine.build_skill_context(request)
        
        # 2. Gather list of available tools
        tools = self.registry.get_all_function_declarations()
        
        # 3. Create system instructions integrated with skill descriptions
        skill_descriptions = self.registry.get_skill_descriptions()
        system_instruction = self.context_engine.build_system_instruction(skill_descriptions)
        
        try:
            logger.info(f"Agent is processing request: '{request.content}' with {len(tools)} registered tools.")
            
            # Configure LLM call
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
            )
            
            # Embed tools in configuration if any
            if tools:
                config.tools = [types.Tool(function_declarations=tools)]
            
            # Call Gemini API asynchronously
            response = await self.client.aio.models.generate_content(
                model=settings.GEMINI_PRIMARY_MODEL,
                contents=request.content,
                config=config
            )
            
            # 4. Check if Gemini decided to perform a Function Call (call tool)
            function_calls = response.function_calls
            if function_calls:
                call = function_calls[0]
                logger.info(f"Gemini proposed calling function: '{call.name}' with arguments: {call.args}")
                
                # Convert args to dict
                args_dict = dict(call.args) if call.args else {}
                
                # Dispatch call through Registry
                result = await self.registry.dispatch(call.name, args_dict, skill_context)
                
                if result.success:
                    return AgentResponse(
                        content=result.message,
                        embed=result.embed,
                        view=result.view,
                        skill_used=call.name
                    )
                else:
                    return AgentResponse(
                        content=f"❌ Failed to execute {call.name}: {result.message}",
                        skill_used=call.name
                    )
            
            # 5. If Gemini returns normal text (chitchat)
            return AgentResponse(
                content=response.text or "Kim does not fully understand your intent.",
                skill_used="chitchat"
            )
            
        except Exception as e:
            logger.error(f"System error when Agent Core processed the request: {e}", exc_info=True)
            return AgentResponse(content="❌ Secretary Kim encountered a technical error while processing this request.")
