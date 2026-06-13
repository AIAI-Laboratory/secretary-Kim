from dependency_injector import containers, providers
from app.services.music import MusicService
from app.presentation.discord_bot import MusicBot

class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(modules=["app.main"])

    music_service = providers.Singleton(
        MusicService
    )

    discord_bot = providers.Singleton(
        MusicBot,
        music_service=music_service
    )
