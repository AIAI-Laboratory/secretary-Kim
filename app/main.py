import sys
from app.core.config import settings
from app.core.container import Container
from app.core.logger import get_logger

logger = get_logger(__name__)

def main():
    logger.info("Starting Discord bot Secretary Kim...")

    # Check Discord Bot token
    if not settings.DISCORD_BOT_TOKEN:
        logger.critical(
            "\n[CRITICAL ERROR] DISCORD_BOT_TOKEN has not been configured in the .env file!\n"
            "Please add the line 'DISCORD_BOT_TOKEN=your_bot_token' to the .env file in the project root directory."
        )
        sys.exit(1)

    # Initialize DI Container
    container = Container()

    # Register skills to registry
    registry = container.skill_registry()
    registry.register(container.music_skill())
    registry.register(container.event_skill())
    registry.register(container.gacha_skill())

    # Get the unique bot instance (Singleton) from Container
    bot = container.discord_bot()

    logger.info("Connecting to Discord...")
    try:
        bot.run(settings.DISCORD_BOT_TOKEN)
    except Exception as e:
        logger.critical(f"Error running Discord bot: {e}")
        sys.exit(1)
