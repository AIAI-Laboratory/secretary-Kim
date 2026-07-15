import os
import aiosqlite
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class DatabaseService:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or settings.DATABASE_PATH

    async def init_db(self):
        """Initialize the database tables if they do not exist."""
        # Ensure target directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            logger.info(f"Created database directory: {db_dir}")

        async with aiosqlite.connect(self.db_path) as db:
            # Create users table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    discord_id TEXT PRIMARY KEY,
                    focus_points INTEGER DEFAULT 0,
                    focus_fruits INTEGER DEFAULT 0,
                    active_pet_id INTEGER DEFAULT NULL,
                    pomodoro_start_time TEXT DEFAULT NULL,
                    pomodoro_channel_id TEXT DEFAULT NULL,
                    pomodoro_text_channel_id TEXT DEFAULT NULL,
                    pomodoro_duration_mins INTEGER DEFAULT 25
                )
            """)

            # Upgrade schema for attendance tracking
            for col, col_def in [
                ("attendance_coins", "INTEGER DEFAULT 100"),
                ("voice_accumulated_minutes", "INTEGER DEFAULT 0"),
            ]:
                try:
                    await db.execute(f"ALTER TABLE users ADD COLUMN {col} {col_def}")
                    logger.info(
                        f"Database migration: Added column '{col}' to 'users' table."
                    )
                except Exception as e:
                    # Column already exists
                    logger.debug(f"Column '{col}' already exists in 'users' table: {e}")

            # Initialize existing users with 100 coins if they have 0 or NULL
            await db.execute(
                "UPDATE users SET attendance_coins = 100 WHERE attendance_coins IS NULL OR attendance_coins = 0"
            )

            # Create pets table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS pets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    rarity TEXT NOT NULL,
                    type1 TEXT NOT NULL,
                    type2 TEXT,
                    level INTEGER DEFAULT 1,
                    exp INTEGER DEFAULT 0,
                    hp INTEGER DEFAULT 100,
                    stage INTEGER DEFAULT 1,
                    concept TEXT NOT NULL,
                    mega_capable INTEGER DEFAULT 0,
                    stage1_name TEXT NOT NULL,
                    stage1_desc TEXT NOT NULL,
                    stage1_prompt TEXT NOT NULL,
                    stage1_img TEXT,
                    stage2_name TEXT NOT NULL,
                    stage2_desc TEXT NOT NULL,
                    stage2_prompt TEXT NOT NULL,
                    stage2_img TEXT,
                    stage3_name TEXT NOT NULL,
                    stage3_desc TEXT NOT NULL,
                    stage3_prompt TEXT NOT NULL,
                    stage3_img TEXT,
                    mega_name TEXT,
                    mega_desc TEXT,
                    mega_prompt TEXT,
                    mega_img TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(discord_id)
                )
            """)
            await db.commit()
            logger.info(f"SQLite database initialized at: {self.db_path}")

    async def get_db(self) -> aiosqlite.Connection:
        """Get an active aiosqlite connection."""
        return await aiosqlite.connect(self.db_path)
