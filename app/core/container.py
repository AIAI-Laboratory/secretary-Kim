from dependency_injector import containers, providers
from app.services.music import MusicService
from app.services.event import EventService
from app.services.task import TaskService
from app.services.database import DatabaseService
from app.services.gacha import GachaService
from app.services.pomodoro import PomodoroService
from app.agent.registry import SkillRegistry
from app.agent.context import ContextEngine
from app.agent.skills.music_skill import MusicSkill
from app.agent.skills.event_skill import EventSkill
from app.agent.skills.gacha_skill import GachaSkill
from app.agent.core import KimAgent
from app.presentation.discord_bot import MusicBot
from app.services.pixellab import PixelLabService
from app.services.attendance import AttendanceService
from app.agent.skills.attendance_skill import AttendanceSkill


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(modules=["app.main"])

    # Core business services
    db_service = providers.Singleton(DatabaseService)

    pixellab_service = providers.Singleton(PixelLabService)

    gacha_service = providers.Singleton(
        GachaService, db_service=db_service, pixellab_service=pixellab_service
    )

    pomodoro_service = providers.Singleton(
        PomodoroService, db_service=db_service, gacha_service=gacha_service
    )

    music_service = providers.Singleton(MusicService)

    event_service = providers.Singleton(EventService)

    task_service = providers.Singleton(TaskService)

    attendance_service = providers.Singleton(AttendanceService, db_service=db_service)

    # Agent core components
    skill_registry = providers.Singleton(SkillRegistry)

    context_engine = providers.Singleton(ContextEngine)

    # Agent skills
    music_skill = providers.Singleton(MusicSkill, music_service=music_service)

    event_skill = providers.Singleton(EventSkill, event_service=event_service)

    gacha_skill = providers.Singleton(
        GachaSkill, gacha_service=gacha_service, pomodoro_service=pomodoro_service
    )

    attendance_skill = providers.Singleton(
        AttendanceSkill, attendance_service=attendance_service
    )

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
        db_service=db_service,
        gacha_service=gacha_service,
        pomodoro_service=pomodoro_service,
        attendance_service=attendance_service,
    )
