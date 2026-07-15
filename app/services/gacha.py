import json
import random
import io
import httpx
from typing import Dict, Any, Tuple, Optional
from google import genai
from google.genai import types
from app.core.config import settings
from app.core.logger import get_logger
from app.services.database import DatabaseService
from app.services.pixellab import PixelLabService

logger = get_logger(__name__)

TYPES = [
    "Fire",
    "Water",
    "Grass",
    "Electric",
    "Steel",
    "Dark",
    "Psychic",
    "Dragon",
    "Ice",
    "Ground",
    "Flying",
    "Ghost",
    "Fairy",
    "Poison",
    "Rock",
    "Bug",
    "Normal",
    "Fighting",
]

RARITY_STYLING = {
    "Common": {
        "title": "🎲 Gacha: New Companion Discovered!",
        "rarity_formatted": "⚪ **Common**",
        "color": 0x979C9F,  # Grey
    },
    "Rare": {
        "title": "✨ Gacha: Rare Companion Discovered! ✨",
        "rarity_formatted": "💎 ✨ **Rare** ✨ 💎",
        "color": 0x3498DB,  # Blue
    },
    "Legendary": {
        "title": "👑 Gacha: LEGENDARY Companion Discovered! 👑",
        "rarity_formatted": "🔥 🌟 **LEGENDARY** 🌟 🔥",
        "color": 0xF1C40F,  # Gold/Yellow
    },
}


CONCEPTS = {
    "Object": [
        "Book",
        "Pen",
        "Ring",
        "Mirror",
        "Lamp",
        "Candle",
        "Sword",
        "Shield",
        "Crown",
        "Coin",
        "Potion",
        "Map",
        "Letter",
        "Chest",
        "Box",
        "Bottle",
        "Cup",
        "Feather",
        "Mask",
        "Clock",
        "Bell",
        "Flute",
        "Harp",
        "Necklace",
        "Bracelet",
        "Dagger",
        "Bow",
        "Arrow",
        "Staff",
        "Wand",
        "Telescope",
        "Globe",
        "Lantern",
        "Hammer",
        "Anvil",
        "Gear",
        "Dice",
        "Card",
        "Doll",
        "Fan",
        "Umbrella",
        "Pipe",
        "Quill",
        "Scroll",
        "Inkwell",
        "Goblet",
        "Amulet",
        "Keyring",
        "Teapot",
        "Tome",
    ],
    "Animal": [
        "Cat",
        "Dog",
        "Wolf",
        "Fox",
        "Bear",
        "Deer",
        "Rabbit",
        "Owl",
        "Eagle",
        "Hawk",
        "Raven",
        "Crow",
        "Swan",
        "Duck",
        "Frog",
        "Toad",
        "Snake",
        "Lizard",
        "Turtle",
        "Fish",
        "Shark",
        "Whale",
        "Dolphin",
        "Octopus",
        "Crab",
        "Tiger",
        "Lion",
        "Leopard",
        "Cheetah",
        "Elephant",
        "Giraffe",
        "Zebra",
        "Horse",
        "Donkey",
        "Cow",
        "Sheep",
        "Goat",
        "Pig",
        "Monkey",
        "Gorilla",
        "Mouse",
        "Rat",
        "Bat",
        "Otter",
        "Seal",
        "Walrus",
        "Penguin",
        "Koala",
        "Kangaroo",
        "Sloth",
    ],
    "Mythical": [
        "Griffin",
        "Centaur",
        "Minotaur",
        "Mermaid",
        "Merman",
        "Unicorn",
        "Alicorn",
        "Cerberus",
        "Hydra",
        "Gorgon",
        "Medusa",
        "Cyclops",
        "Titan",
        "Nymph",
        "Dryad",
        "Pixie",
        "Sprite",
        "Fairy",
        "Elf",
        "Dwarf",
        "Goblin",
        "Orc",
        "Troll",
        "Ogre",
        "Golem",
        "Gargoyle",
        "Vampire",
        "Werewolf",
        "Zombie",
        "Ghost",
        "Specter",
        "Wraith",
        "Banshee",
        "Siren",
        "Harpy",
        "Manticore",
        "Kraken",
        "Leviathan",
        "Behemoth",
        "Thunderbird",
        "Wyvern",
        "Drake",
        "Basilisk",
        "Cockatrice",
        "Leprechaun",
        "Gnome",
        "Satyr",
        "Faun",
        "Yeti",
        "Bigfoot",
    ],
    "Phenomenon": [
        "Rain",
        "Snow",
        "Hail",
        "Fog",
        "Mist",
        "Wind",
        "Gale",
        "Storm",
        "Lightning",
        "Thunder",
        "Rainbow",
        "Heatwave",
        "Blizzard",
        "Hurricane",
        "Typhoon",
        "Cyclone",
        "Flood",
        "Drought",
        "Earthquake",
        "Tsunami",
        "Avalanche",
        "Landslide",
        "Wildfire",
        "Meteor",
        "Comet",
        "Asteroid",
        "Flare",
        "Supernova",
        "Nebula",
        "Galaxy",
        "Orbit",
        "Gravity",
        "Tide",
        "Current",
        "Frost",
        "Dew",
        "Mirage",
        "Echo",
        "Shadow",
        "Reflection",
        "Rust",
        "Decay",
        "Growth",
        "Erosion",
        "Sedimentation",
        "Evaporation",
        "Condensation",
        "Freezing",
        "Melting",
        "Combustion",
    ],
}


class GachaService:
    def __init__(self, db_service: DatabaseService, pixellab_service: PixelLabService):
        self.db_service = db_service
        self.pixellab_service = pixellab_service
        if not settings.GEMINI_API_KEY:
            logger.warning(
                "GEMINI_API_KEY is not configured in .env. Gemini Gacha LLM may not work."
            )
        self.gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY or None)

    async def check_or_create_user(self, db, discord_id: str) -> Dict[str, Any]:
        """Check if user exists; if not, create them with starting currency (200 FP, 2 Fruits, 100 Coins)."""
        async with db.execute(
            "SELECT * FROM users WHERE discord_id = ?", (discord_id,)
        ) as cursor:
            user = await cursor.fetchone()

        if not user:
            await db.execute(
                "INSERT INTO users (discord_id, focus_points, focus_fruits, attendance_coins, voice_accumulated_minutes) VALUES (?, ?, ?, ?, ?)",
                (discord_id, 200, 2, 100, 0),
            )
            await db.commit()
            logger.info(
                f"Created new user in DB: {discord_id} with 200 FP, 2 Fruits, 100 Coins."
            )
            return {
                "discord_id": discord_id,
                "focus_points": 200,
                "focus_fruits": 2,
                "attendance_coins": 100,
                "active_pet_id": None,
            }

        return {
            "discord_id": user[0],
            "focus_points": user[1],
            "focus_fruits": user[2],
            "active_pet_id": user[3],
        }

    def _roll_attributes(self) -> Dict[str, Any]:
        """Roll random attributes for a new Pokemon."""
        # 1. Roll elements
        num_types = random.choices([1, 2], weights=[70, 30])[0]
        selected_types = random.sample(TYPES, num_types)
        type1 = selected_types[0]
        type2 = selected_types[1] if num_types == 2 else None

        # 2. Roll rarity
        rarity = random.choices(["Common", "Rare", "Legendary"], weights=[70, 20, 10])[
            0
        ]

        # 3. Roll concept
        concept_category = random.choice(list(CONCEPTS.keys()))
        concept = random.choice(CONCEPTS[concept_category])

        # 4. Roll Mega Capability (20% chance)
        mega_capable = random.choices([0, 1], weights=[80, 20])[0]

        return {
            "rarity": rarity,
            "type1": type1,
            "type2": type2,
            "concept": concept,
            "mega_capable": mega_capable,
        }

    async def _call_gemini_llm(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        """Call Gemini to design the creature stages using structured output schema."""
        from app.domain.models.gacha import GachaPetDesign

        system_prompt = (
            "You are a world-class pocket monster designer with a deep sense of creativity and narrative. "
            "Your task is to design a fully original fictional monster species with 3 evolution stages (plus an optional Mega stage), "
            "inspired by the provided concept, types, and rarity.\n\n"
            "## Design Philosophy\n"
            "- The creature must feel fresh and original — avoid directly copying existing Pokémon designs.\n"
            "- The concept (e.g. 'Clock', 'Rain', 'Griffin') should be deeply reflected in the creature's biology, silhouette, and aesthetic.\n"
            "- Rarity directly determines complexity and visual impressiveness:\n"
            "  • Common → simple, cute, minimalist design with 1–2 defining features.\n"
            "  • Rare → more elaborate, dual-theme integration, elegant or fierce presence.\n"
            "  • Legendary → jaw-dropping, mythic silhouette, radiates power; complex layered anatomy.\n"
            "- Evolution stages must feel like a coherent progression (same species, growing more powerful and complex).\n"
            "- Each stage should have a distinct, memorable silhouette.\n\n"
            "## Type Integration\n"
            "- Elemental types must influence the color palette and visual motifs:\n"
            "  Fire → warm reds/oranges, ember glow, flame textures\n"
            "  Water → blue-green hues, fluid fins, shimmering scales\n"
            "  Electric → bright yellow/white, jagged shapes, crackling aura\n"
            "  (and so on for other types)\n"
            "- If dual-typed, blend both type aesthetics in a balanced, intentional way.\n\n"
            "## Naming Rules\n"
            "- Species name (base 'name') must be short, punchy, and memorable (1–2 syllables preferred).\n"
            "- Each stage's name should reflect progression (e.g. Ignub → Ignachar → Volcaron).\n"
            "- Mega form names should add 'Mega' prefix or a dramatic suffix.\n\n"
            "## Description Rules\n"
            "- Descriptions should be flavourful, lore-rich, and ~2 sentences long.\n"
            "- Evoke a sense of personality and world-building.\n\n"
            "## Visual Prompt Rules (CRITICAL)\n"
            "- In 'visual_prompt', describe ONLY the creature itself — body shape, limb count, proportions, textures, colors, eyes, markings, and any elemental effects on its body.\n"
            "- DO NOT mention any background, environment, ground, sky, weather, shadow, or surrounding objects.\n"
            "- Be highly specific: avoid vague words like 'glowing' or 'colorful'. Specify which part glows, what color, how intensely.\n"
            "- Describe from head to body to limbs/tail in logical order.\n"
            "- Length: 3–5 detailed sentences per stage."
        )

        user_input = {
            "rarity": attrs["rarity"],
            "types": [attrs["type1"]] + ([attrs["type2"]] if attrs["type2"] else []),
            "concept": attrs["concept"],
            "mega_capable": bool(attrs["mega_capable"]),
        }

        try:
            logger.info(f"Sending Gacha design request to Gemini: {user_input}")
            response = await self.gemini_client.aio.models.generate_content(
                model=settings.GEMINI_PRIMARY_MODEL,
                contents=json.dumps(user_input),
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=GachaPetDesign,
                    temperature=0.7,
                ),
            )

            parsed_data = json.loads(response.text)
            return parsed_data
        except Exception as e:
            logger.error(f"Gemini Gacha LLM generation failed: {e}", exc_info=True)
            raise e

    async def generate_evolution_image(
        self, prompt: str, prev_img_url: Optional[str]
    ) -> bytes:
        """
        Generate an evolved stage image using PixelLab.
        Uses the previous stage's image URL as init_image reference if provided.
        """
        init_image_bytes = None
        if prev_img_url:
            try:
                async with httpx.AsyncClient(timeout=10.0) as http_client:
                    resp = await http_client.get(prev_img_url)
                    if resp.status_code == 200:
                        init_image_bytes = resp.content
                        logger.info(
                            f"Successfully downloaded previous stage image for evolution: {len(init_image_bytes)} bytes"
                        )
            except Exception as e:
                logger.error(f"Failed to fetch previous stage image: {e}")

        # Call PixelLab Service to generate image
        pixel_bytes = await self.pixellab_service.generate_pixel_art(
            prompt=prompt,
            model="pixflux",
            width=128,
            height=128,
            transparent=True,
            init_image=init_image_bytes,
            init_image_strength=300,
        )
        return pixel_bytes

    async def roll_gacha(
        self, discord_id: str
    ) -> Tuple[int, Dict[str, Any], bytes, bytes]:
        """
        Deduct FP, roll attributes, call LLM to generate descriptions,
        call Image Gen for Stage 1, resize to pixel art, and save pet in DB.
        Returns: (pet_id, pet_dict, stage1_hd_bytes, stage1_pixel_bytes)
        """
        db = await self.db_service.get_db()
        try:
            # 1. User check and Coins verification
            user = await self.check_or_create_user(db, discord_id)
            async with db.execute(
                "SELECT attendance_coins FROM users WHERE discord_id = ?", (discord_id,)
            ) as cursor:
                coins_row = await cursor.fetchone()
            coins = coins_row[0] if coins_row else 100

            if coins < 100:
                raise ValueError(
                    f"Not enough Coins! (You have: {coins} Coins, need 100 Coins for Gacha)"
                )

            # Deduct Coins
            await db.execute(
                "UPDATE users SET attendance_coins = attendance_coins - 100 WHERE discord_id = ?",
                (discord_id,),
            )

            # 2. Roll random attributes
            attrs = self._roll_attributes()

            # 3. Call LLM to generate description JSON
            design = await self._call_gemini_llm(attrs)

            # 4. Generate Stage 1 Image
            stage1_prompt = design["stage1"]["visual_prompt"]
            pixel_bytes = await self.pixellab_service.generate_pixel_art(
                prompt=stage1_prompt,
                model="pixflux",
                width=128,
                height=128,
                transparent=True,
            )
            hd_bytes = pixel_bytes

            # 6. Save pet to database
            stage1_name = design["stage1"]["name"]
            stage1_desc = design["stage1"]["description"]

            stage2_name = design["stage2"]["name"]
            stage2_desc = design["stage2"]["description"]
            stage2_prompt = design["stage2"]["visual_prompt"]

            stage3_name = design["stage3"]["name"]
            stage3_desc = design["stage3"]["description"]
            stage3_prompt = design["stage3"]["visual_prompt"]

            mega = design.get("mega") or {}
            mega_name = mega.get("name")
            mega_desc = mega.get("description")
            mega_prompt = mega.get("visual_prompt")

            cursor = await db.execute(
                """
                INSERT INTO pets (
                    user_id, name, rarity, type1, type2, level, exp, hp, stage, concept, mega_capable,
                    stage1_name, stage1_desc, stage1_prompt,
                    stage2_name, stage2_desc, stage2_prompt,
                    stage3_name, stage3_desc, stage3_prompt,
                    mega_name, mega_desc, mega_prompt
                ) VALUES (?, ?, ?, ?, ?, 1, 0, 100, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    discord_id,
                    design["name"],
                    attrs["rarity"],
                    attrs["type1"],
                    attrs["type2"],
                    attrs["concept"],
                    attrs["mega_capable"],
                    stage1_name,
                    stage1_desc,
                    stage1_prompt,
                    stage2_name,
                    stage2_desc,
                    stage2_prompt,
                    stage3_name,
                    stage3_desc,
                    stage3_prompt,
                    mega_name,
                    mega_desc,
                    mega_prompt,
                ),
            )

            pet_id = cursor.lastrowid

            # Automatically set active pet if the user does not have one
            if user["active_pet_id"] is None:
                await db.execute(
                    "UPDATE users SET active_pet_id = ? WHERE discord_id = ?",
                    (pet_id, discord_id),
                )

            await db.commit()

            # Retrieve final stored details
            pet_dict = {
                "id": pet_id,
                "name": design["name"],
                "rarity": attrs["rarity"],
                "type1": attrs["type1"],
                "type2": attrs["type2"],
                "level": 1,
                "exp": 0,
                "hp": 100,
                "stage": 1,
                "concept": attrs["concept"],
                "mega_capable": bool(attrs["mega_capable"]),
                "stage1_name": stage1_name,
                "stage1_desc": stage1_desc,
                "active": (
                    user["active_pet_id"] is None or user["active_pet_id"] == pet_id
                ),
            }

            logger.info(
                f"User {discord_id} rolled new pet: {design['name']} (ID: {pet_id})"
            )
            return pet_id, pet_dict, hd_bytes, pixel_bytes

        except Exception as e:
            await db.rollback()
            logger.error(f"Gacha roll failed: {e}", exc_info=True)
            raise e

    async def update_pet_image(
        self, pet_id: int, stage: int, hd_url: str, pixel_url: str
    ) -> None:
        """Update database with generated image URLs for a specific evolution stage."""
        db = await self.db_service.get_db()
        if stage == 1:
            await db.execute(
                "UPDATE pets SET stage1_img = ? WHERE id = ?", (pixel_url, pet_id)
            )  # We use the pixel URL as default, can keep HD in stage description
        elif stage == 2:
            await db.execute(
                "UPDATE pets SET stage2_img = ? WHERE id = ?", (pixel_url, pet_id)
            )
        elif stage == 3:
            await db.execute(
                "UPDATE pets SET stage3_img = ? WHERE id = ?", (pixel_url, pet_id)
            )
        elif stage == 4:
            await db.execute(
                "UPDATE pets SET mega_img = ? WHERE id = ?", (pixel_url, pet_id)
            )

        # Store HD image in an extra lookup or logging channel if needed, or we just store pixel URL in standard. Let's store both in separate metadata fields if we want, but keeping it simple: stageX_img stores the pixelated image to display in Discord chat.
        await db.commit()

    async def get_active_pet(self, discord_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve active pet details for a user."""
        db = await self.db_service.get_db()
        async with db.execute(
            """
            SELECT u.active_pet_id, p.* 
            FROM users u 
            JOIN pets p ON u.active_pet_id = p.id 
            WHERE u.discord_id = ?
        """,
            (discord_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return None

        # row[0] is active_pet_id, row[1] is id, row[2] is user_id, row[3] is name, ...
        return self._row_to_pet_dict(row[1:])

    async def get_user_pets(self, discord_id: str) -> list[Dict[str, Any]]:
        """Retrieve all pets owned by a user."""
        db = await self.db_service.get_db()
        async with db.execute(
            "SELECT * FROM pets WHERE user_id = ?", (discord_id,)
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_pet_dict(r) for r in rows]

    async def set_active_pet(self, discord_id: str, pet_id: int) -> bool:
        """Set a user's active pet."""
        db = await self.db_service.get_db()
        async with db.execute(
            "SELECT id FROM pets WHERE id = ? AND user_id = ?", (pet_id, discord_id)
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return False

        await db.execute(
            "UPDATE users SET active_pet_id = ? WHERE discord_id = ?",
            (pet_id, discord_id),
        )
        await db.commit()
        return True

    async def feed_active_pet(
        self, discord_id: str
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Feed a fruit to the active pet. Restores HP or gains XP. Triggers evolution if level/XP milestones met."""
        db = await self.db_service.get_db()
        # Check user coins (feeding costs 20 Coins)
        async with db.execute(
            "SELECT attendance_coins FROM users WHERE discord_id = ?", (discord_id,)
        ) as cursor:
            coins_row = await cursor.fetchone()
        coins = coins_row[0] if coins_row else 100

        if coins < 20:
            return (
                False,
                f"You don't have enough Coins! (You have: {coins} Coins, need 20 Coins to feed).",
                None,
            )

        pet = await self.get_active_pet(discord_id)
        if not pet:
            return False, "You don't have an active pet to feed! Roll one first.", None

        # Check if pet needs healing or XP
        hp_gained = 0
        xp_gained = 0
        message = ""

        new_hp = min(100, pet["hp"] + 20)
        if pet["hp"] < 100:
            hp_gained = new_hp - pet["hp"]
            message += f"Healed {hp_gained} HP. "

        xp_gained = random.randint(15, 30)
        new_exp = pet["exp"] + xp_gained
        new_level = pet["level"]
        message += f"Gained {xp_gained} XP. "

        # Simple leveling logic (e.g. 100 XP per level)
        level_up = False
        while new_exp >= 100:
            new_exp -= 100
            new_level += 1
            level_up = True

        if level_up:
            message += f"🎉 Level up! {pet['name']} is now Level {new_level}! "

        # Evolution checkpoints
        new_stage = pet["stage"]
        evolution_triggered = False
        evolution_text = ""

        if new_stage == 1 and new_level >= 15:
            new_stage = 2
            evolution_triggered = True
            evolution_text = f"✨ Evolutionary energy is surging! {pet['name']} is evolving into Stage 2: **{pet['stage2_name']}**!"
        elif new_stage == 2 and new_level >= 36:
            new_stage = 3
            evolution_triggered = True
            evolution_text = f"✨ Evolution! {pet['name']} is evolving into its ultimate form, Stage 3: **{pet['stage3_name']}**!"
        elif new_stage == 3 and pet["mega_capable"] and new_level >= 50:
            # Let's say user needs to feed the pet and it reaches Level 50 to Mega Evolve
            new_stage = 4
            evolution_triggered = True
            evolution_text = f"🌟 MYTHICAL MEGA EVOLUTION! {pet['name']} has transcended into **{pet['mega_name']}**!"

        # Deduct coins and update pet
        await db.execute(
            "UPDATE users SET attendance_coins = attendance_coins - 20 WHERE discord_id = ?",
            (discord_id,),
        )
        await db.execute(
            """
            UPDATE pets 
            SET hp = ?, level = ?, exp = ?, stage = ? 
            WHERE id = ?
        """,
            (new_hp, new_level, new_exp, new_stage, pet["id"]),
        )
        await db.commit()

        updated_pet = await self.get_active_pet(discord_id)

        full_message = f"You fed a Focus Fruit to {pet['name']}. {message}"
        if evolution_triggered:
            full_message += f"\n\n{evolution_text}"

        return True, full_message, updated_pet

    def _row_to_pet_dict(self, row: tuple) -> Dict[str, Any]:
        """Convert a database row into a structured dictionary."""
        return {
            "id": row[0],
            "user_id": row[1],
            "name": row[2],
            "rarity": row[3],
            "type1": row[4],
            "type2": row[5],
            "level": row[6],
            "exp": row[7],
            "hp": row[8],
            "stage": row[9],
            "concept": row[10],
            "mega_capable": bool(row[11]),
            "stage1_name": row[12],
            "stage1_desc": row[13],
            "stage1_prompt": row[14],
            "stage1_img": row[15],
            "stage2_name": row[16],
            "stage2_desc": row[17],
            "stage2_prompt": row[18],
            "stage2_img": row[19],
            "stage3_name": row[20],
            "stage3_desc": row[21],
            "stage3_prompt": row[22],
            "stage3_img": row[23],
            "mega_name": row[24],
            "mega_desc": row[25],
            "mega_prompt": row[26],
            "mega_img": row[27],
        }
