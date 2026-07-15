from dependency_injector import containers, providers
from app.services.music import MusicService
from app.services.event import EventService
from app.services.task import TaskService
from app.agent.registry import SkillRegistry
from app.agent.context import ContextEngine
from app.agent.skills.music_skill import MusicSkill
from app.agent.skills.event_skill import EventSkill
from app.agent.core import KimAgent
from app.presentation.discord_bot import MusicBot


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(modules=["app.main"])

    # Core business services
    music_service = providers.Singleton(MusicService)

    event_service = providers.Singleton(EventService)

    task_service = providers.Singleton(TaskService)

    # Agent core components
    skill_registry = providers.Singleton(SkillRegistry)

    context_engine = providers.Singleton(ContextEngine)

    # Agent skills
    music_skill = providers.Singleton(MusicSkill, music_service=music_service)

    event_skill = providers.Singleton(EventSkill, event_service=event_service)

    # Central AI Agent
    kim_agent = providers.Singleton(
        KimAgent, skill_registry=skill_registry, context_engine=context_engine
    )

    discord_bot = providers.Singleton(
        MusicBot,
        kim_agent=kim_agent,
        music_service=music_service,
        event_service=event_service,
        task_service=task_service,
    )
