import asyncio
import json
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db as firebase_db
from typing import Any, Dict
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class DatabaseService:
    def __init__(self):
        self._initialized = False

    async def init_db(self) -> None:
        """Initialize the Firebase App and connect to the Realtime Database."""
        if self._initialized:
            return

        # Ensure credentials are provided
        if (
            not settings.FIREBASE_CREDENTIALS_JSON
            and not settings.FIREBASE_CREDENTIALS_PATH
        ):
            raise ValueError(
                "Neither FIREBASE_CREDENTIALS_JSON nor FIREBASE_CREDENTIALS_PATH is set in environment settings."
            )

        if not settings.FIREBASE_DATABASE_URL:
            raise ValueError(
                "FIREBASE_DATABASE_URL is not set in environment settings."
            )

        def _init():
            if not firebase_admin._apps:
                if settings.FIREBASE_CREDENTIALS_JSON:
                    try:
                        cred_dict = json.loads(settings.FIREBASE_CREDENTIALS_JSON)
                        cred = credentials.Certificate(cred_dict)
                        logger.info(
                            "Initializing Firebase using FIREBASE_CREDENTIALS_JSON."
                        )
                    except Exception as e:
                        logger.error(f"Failed to parse FIREBASE_CREDENTIALS_JSON: {e}")
                        raise e
                else:
                    logger.info(
                        f"Initializing Firebase using key path: {settings.FIREBASE_CREDENTIALS_PATH}"
                    )
                    cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)

                firebase_admin.initialize_app(
                    cred, {"databaseURL": settings.FIREBASE_DATABASE_URL}
                )
                logger.info(
                    f"Firebase initialized successfully with DB URL: {settings.FIREBASE_DATABASE_URL}"
                )

        await asyncio.to_thread(_init)
        self._initialized = True

    async def get_ref(self, path: str = "/") -> firebase_db.Reference:
        """Get a reference to a path in the database. Thread-safe."""
        if not self._initialized:
            await self.init_db()
        return firebase_db.reference(path)

    async def get_data(self, path: str) -> Any:
        """Read data from a path asynchronously."""
        ref = await self.get_ref(path)
        return await asyncio.to_thread(ref.get)

    async def set_data(self, path: str, data: Any) -> None:
        """Write/overwrite data to a path asynchronously."""
        ref = await self.get_ref(path)
        await asyncio.to_thread(ref.set, data)

    async def update_data(self, path: str, data: Dict[str, Any]) -> None:
        """Update fields at a path asynchronously."""
        ref = await self.get_ref(path)
        await asyncio.to_thread(ref.update, data)

    async def push_data(self, path: str, data: Any) -> str:
        """Push (append) data to a list and return the new child's key/ID."""
        ref = await self.get_ref(path)
        new_ref = await asyncio.to_thread(ref.push, data)
        return new_ref.key

    async def delete_data(self, path: str) -> None:
        """Delete data at a path asynchronously."""
        ref = await self.get_ref(path)
        await asyncio.to_thread(ref.delete)

    async def run_transaction(self, path: str, transaction_fn) -> Any:
        """Run a transaction at the given path asynchronously."""
        ref = await self.get_ref(path)
        return await asyncio.to_thread(ref.transaction, transaction_fn)
