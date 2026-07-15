from dependency_injector import containers, providers
from app.services.music import MusicService
from app.services.agent.event_management import EventAgentService
from app.services.agent.task_management import TaskManagementAgentService
from app.presentation.discord_bot import MusicBot


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(modules=["app.main"])

    music_service = providers.Singleton(MusicService)

    event_agent_service = providers.Singleton(EventAgentService)

    task_management_agent_service = providers.Singleton(TaskManagementAgentService)

    discord_bot = providers.Singleton(
        MusicBot,
        music_service=music_service,
        event_agent_service=event_agent_service,
        task_management_agent_service=task_management_agent_service,
    )
