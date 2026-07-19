import json
import random
from typing import Dict, Any, Tuple, Optional
from google import genai
from google.genai import types
from app.core.config import settings
from app.core.logger import get_logger
from app.services.database import DatabaseService
from app.services.pixellab import PixelLabService
from .constants import TYPES, TYPE_EMOJIS, CONCEPTS, SYSTEM_PROMPT_TEMPLATE

logger = get_logger(__name__)


def format_types(type1: str, type2: Optional[str] = None) -> str:
    t1 = TYPE_EMOJIS.get(type1, type1)
    if type2:
        t2 = TYPE_EMOJIS.get(type2, type2)
        return f"{t1} / {t2}"
    return t1


class GachaService:
    def __init__(self, db_service: DatabaseService, pixellab_service: PixelLabService):
        self.db_service = db_service
        self.pixellab_service = pixellab_service
        if not settings.GEMINI_API_KEY:
            logger.warning(
                "GEMINI_API_KEY is not configured in .env. Gemini Gacha LLM may not work."
            )
        self.gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY or None)

    def _normalize_pets(self, pets: Any) -> Dict[str, Any]:
        """Normalize pets to a dict if it was retrieved as a list from Firebase."""
        if isinstance(pets, list):
            pets_dict = {}
            for idx, p in enumerate(pets):
                if p is not None:
                    pets_dict[str(idx)] = p
            return pets_dict
        elif isinstance(pets, dict):
            return pets
        return {}

    async def check_or_create_user(self, db, discord_id: str) -> Dict[str, Any]:
        """Check if user exists; if not, create them with starting currency (200 FP, 2 Fruits, 100 Coins)."""
        path = f"users/{discord_id}"
        user = await self.db_service.get_data(path)

        if not user:
            user = {
                "discord_id": discord_id,
                "focus_points": 200,
                "focus_fruits": 2,
                "active_pet_id": None,
                "attendance_coins": 100,
                "voice_accumulated_minutes": 0,
                "next_pet_id": 1,
                "pets": {},
            }
            await self.db_service.set_data(path, user)
            logger.info(
                f"Created new user in Firebase DB: {discord_id} with 200 FP, 2 Fruits, 100 Coins."
            )
            return {
                "discord_id": discord_id,
                "focus_points": 200,
                "focus_fruits": 2,
                "attendance_coins": 100,
                "active_pet_id": None,
            }

        return {
            "discord_id": user.get("discord_id", discord_id),
            "focus_points": user.get("focus_points", 200),
            "focus_fruits": user.get("focus_fruits", 2),
            "active_pet_id": user.get("active_pet_id"),
        }

    def _roll_attributes(self) -> Dict[str, Any]:
        """Roll random attributes for a new Pokemon."""
        num_types = random.choices([1, 2], weights=[50, 50])[0]
        selected_types = random.sample(TYPES, num_types)
        type1 = selected_types[0]
        type2 = selected_types[1] if num_types == 2 else None

        rarity = random.choices(
            ["Common", "Epic", "Legendary", "God"], weights=[50, 20, 10, 5]
        )[0]

        concept_category = random.choice(list(CONCEPTS.keys()))
        concept = random.choice(CONCEPTS[concept_category])

        if rarity in ["Legendary", "God"]:
            mega_capable = 0
        else:
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

        is_single_stage = attrs["rarity"] in ["Legendary", "God"]

        if is_single_stage:
            evolution_rules = f"• Since this is a {attrs['rarity']} creature, it does NOT evolve. It only has one single stage. Therefore, you MUST set stage2, stage3, and mega to null / None. Do NOT fill in stage2, stage3, or mega."
            length_rule = (
                "5-6 detailed, complex, epic sentences describing a legendary/god form."
            )
        else:
            evolution_rules = (
                "• For Common and Epic creatures, you must design all 3 stages. Evolution stages must feel like a coherent progression.\n"
                "• CRITICAL: You MUST maintain strict design, color, and visual consistency across all stages (stage1, stage2, stage3, mega).\n"
                "• All stages MUST share the exact same core color palette, base materials, body textures, style, and facial/species characteristics.\n"
                "• Evolution must represent growth, aging, and power enhancement (e.g. growing larger, getting thicker armor plates, developing horns/wings, more intense elemental effects, transitioning from cute to fierce), NOT transforming into a completely different species or changing colors completely."
            )
            length_rule = "3–5 detailed sentences."

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            evolution_rules=evolution_rules, length_rule=length_rule
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
        self, prompt: str, prev_img_url: Optional[str] = None
    ) -> bytes:
        """
        Generate an evolved stage image using PixelLab.
        Note: init_image has been disabled for evolved stages to allow distinct visual
        and structural changes (e.g. growing horns, tails, limbs) while prompt alignment
        ensures color and style consistency.
        """
        # Call PixelLab Service to generate image without init_image constraint
        pixel_bytes = await self.pixellab_service.generate_pixel_art(
            prompt=prompt,
            model="pixflux",
            width=128,
            height=128,
            transparent=True,
        )
        return pixel_bytes

    async def roll_gacha(
        self, discord_id: str, pre_rolled_attrs: Optional[Dict[str, Any]] = None
    ) -> Tuple[int, Dict[str, Any], bytes, bytes]:
        """
        Deduct coins, roll attributes, call LLM to generate descriptions,
        call Image Gen for Stage 1, resize to pixel art, and save pet in DB.
        Returns: (pet_id, pet_dict, stage1_hd_bytes, stage1_pixel_bytes)
        """
        # 1. Check if there is a pending gacha roll saved from a previous failure
        pending_path = f"users/{discord_id}/pending_gacha"
        pending_gacha = await self.db_service.get_data(pending_path)

        if pending_gacha:
            logger.info(
                f"Re-using pending gacha design for user {discord_id} from previous timeout/failure."
            )
            attrs = pending_gacha["attrs"]
            design = pending_gacha["design"]
        else:
            # Check coins (must have at least 100)
            user = await self.check_or_create_user(None, discord_id)
            coins = user.get("attendance_coins", 100)
            if coins < 100:
                raise ValueError(
                    f"Not enough Coins! (You have: {coins} Coins, need 100 Coins for Gacha)"
                )

            # Roll attributes and call Gemini
            attrs = pre_rolled_attrs or self._roll_attributes()
            design = await self._call_gemini_llm(attrs)

            # Save to pending_gacha first before attempting PixelLab
            await self.db_service.set_data(
                pending_path, {"attrs": attrs, "design": design}
            )
            logger.info(
                f"Saved pending gacha design for user {discord_id} to Firebase."
            )

        # 2. Generate Stage 1 Image via PixelLab (this might fail/timeout)
        stage1 = design.get("stage1") or {}
        stage1_prompt = stage1.get("visual_prompt", "")

        try:
            pixel_bytes = await self.pixellab_service.generate_pixel_art(
                prompt=stage1_prompt,
                model="pixflux",
                width=128,
                height=128,
                transparent=True,
            )
            hd_bytes = pixel_bytes
        except Exception as e:
            # Do NOT delete the pending_gacha node so it remains saved for the next try
            logger.warning(
                f"Image generation failed for user {discord_id}. Pending gacha remains saved: {e}"
            )
            raise e

        # 3. Save pet details (once image gen succeeds)
        stage1_name = stage1.get("name", "")
        stage1_desc = stage1.get("description", "")

        stage2 = design.get("stage2") or {}
        stage2_name = stage2.get("name", "")
        stage2_desc = stage2.get("description", "")
        stage2_prompt = stage2.get("visual_prompt", "")

        stage3 = design.get("stage3") or {}
        stage3_name = stage3.get("name", "")
        stage3_desc = stage3.get("description", "")
        stage3_prompt = stage3.get("visual_prompt", "")

        mega = design.get("mega") or {}
        mega_name = mega.get("name", "")
        mega_desc = mega.get("description", "")
        mega_prompt = mega.get("visual_prompt", "")

        pet_data = {
            "user_id": discord_id,
            "name": design["name"],
            "rarity": attrs["rarity"],
            "type1": attrs["type1"],
            "type2": attrs["type2"] or "",
            "level": 1,
            "exp": 0,
            "hp": 100,
            "stage": 1,
            "concept": attrs["concept"],
            "mega_capable": int(attrs["mega_capable"]),
            "stage1_name": stage1_name,
            "stage1_desc": stage1_desc,
            "stage1_prompt": stage1_prompt,
            "stage1_img": "",
            "stage2_name": stage2_name,
            "stage2_desc": stage2_desc,
            "stage2_prompt": stage2_prompt,
            "stage2_img": "",
            "stage3_name": stage3_name,
            "stage3_desc": stage3_desc,
            "stage3_prompt": stage3_prompt,
            "stage3_img": "",
            "mega_name": mega_name,
            "mega_desc": mega_desc,
            "mega_prompt": mega_prompt,
            "mega_img": "",
        }

        user_path = f"users/{discord_id}"

        # Run transaction atomically to deduct coins, insert pet, and clear pending roll
        def update_user_txn(current_data):
            if not current_data:
                current_data = {
                    "discord_id": discord_id,
                    "focus_points": 200,
                    "focus_fruits": 2,
                    "active_pet_id": None,
                    "attendance_coins": 100,
                    "voice_accumulated_minutes": 0,
                    "next_pet_id": 1,
                    "pets": {},
                }

            current_coins = current_data.get("attendance_coins", 100)
            if current_coins < 100:
                raise ValueError("Insufficient coins")

            current_data["attendance_coins"] = current_coins - 100

            pet_id = current_data.get("next_pet_id", 1)
            current_data["next_pet_id"] = pet_id + 1

            pets = current_data.get("pets", {})
            if pets is None:
                pets = {}
            pets = self._normalize_pets(pets)
            pets[str(pet_id)] = pet_data
            current_data["pets"] = pets

            if current_data.get("active_pet_id") is None:
                current_data["active_pet_id"] = pet_id

            # Remove pending_gacha node inside transaction context
            if "pending_gacha" in current_data:
                del current_data["pending_gacha"]

            return current_data

        updated_user = await self.db_service.run_transaction(user_path, update_user_txn)
        pet_id = updated_user["next_pet_id"] - 1

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
            "active": (updated_user["active_pet_id"] == pet_id),
        }

        # Clear pending path explicitly to be safe
        await self.db_service.delete_data(pending_path)

        logger.info(
            f"User {discord_id} rolled new pet: {design['name']} (ID: {pet_id})"
        )
        return pet_id, pet_dict, hd_bytes, pixel_bytes

    async def update_pet_image(
        self, user_id: str, pet_id: int, stage: int, hd_url: str, pixel_url: str
    ) -> None:
        """Update database with generated image URLs for a specific evolution stage."""
        pet_path = f"users/{user_id}/pets/{pet_id}"

        field_map = {1: "stage1_img", 2: "stage2_img", 3: "stage3_img", 4: "mega_img"}
        img_field = field_map.get(stage)
        if img_field:
            await self.db_service.update_data(pet_path, {img_field: pixel_url})
            logger.info(
                f"Updated pet {pet_id} of user {user_id} with image for stage {stage}."
            )

    async def get_active_pet(
        self, discord_id: str, db: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """Retrieve active pet details for a user."""
        user = await self.db_service.get_data(f"users/{discord_id}")
        if not user:
            return None
        active_id = user.get("active_pet_id")
        if active_id is None:
            return None
        pets = user.get("pets", {})
        pets = self._normalize_pets(pets)
        pet = pets.get(str(active_id))
        if not pet:
            return None
        pet["id"] = int(active_id)
        return pet

    async def get_user_pets(self, discord_id: str) -> list[Dict[str, Any]]:
        """Retrieve all pets owned by a user."""
        user = await self.db_service.get_data(f"users/{discord_id}")
        if not user:
            return []
        pets = user.get("pets", {})
        pets = self._normalize_pets(pets)
        pet_list = []
        for pid, pdata in pets.items():
            if pdata is not None:
                pdata["id"] = int(pid)
                pet_list.append(pdata)
        # Sort ascending by pet ID
        pet_list.sort(key=lambda x: x["id"])
        return pet_list

    async def set_active_pet(self, discord_id: str, pet_id: int) -> bool:
        """Set a user's active pet."""
        user_path = f"users/{discord_id}"
        user = await self.db_service.get_data(user_path)
        if not user:
            return False
        pets = user.get("pets", {})
        pets = self._normalize_pets(pets)
        if str(pet_id) not in pets:
            return False

        await self.db_service.update_data(user_path, {"active_pet_id": pet_id})
        return True

    async def feed_active_pet(
        self, discord_id: str, amount: int = 1
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Feed a fruit to the active pet. Restores HP or gains XP. Triggers evolution if level/XP milestones met."""
        user_path = f"users/{discord_id}"
        xp_gained = sum(random.randint(15, 30) for _ in range(amount))

        # Result container to pass values back from transaction
        txn_result = {}

        def feed_txn(current_data):
            if not current_data:
                raise ValueError("User profile not found.")

            coins = current_data.get("attendance_coins", 100)
            cost = 20 * amount
            if coins < cost:
                raise ValueError(
                    f"You don't have enough Coins! (You have: {coins} Coins, need {cost} Coins to feed {amount} time(s))."
                )

            active_id = current_data.get("active_pet_id")
            if active_id is None:
                raise ValueError(
                    "You don't have an active pet to feed! Roll one first."
                )

            pets = current_data.get("pets", {})
            pets = self._normalize_pets(pets)
            pet = pets.get(str(active_id))
            if not pet:
                raise ValueError("Active pet not found.")

            # Deduct coins
            current_data["attendance_coins"] = coins - cost

            # Calculate healing
            old_hp = pet.get("hp", 100)
            new_hp = min(100, old_hp + (20 * amount))
            hp_gained = new_hp - old_hp
            pet["hp"] = new_hp

            # Calculate XP and Level
            old_exp = pet.get("exp", 0)
            old_level = pet.get("level", 1)
            new_exp = old_exp + xp_gained
            new_level = old_level

            level_up = False
            while new_exp >= 100:
                new_exp -= 100
                new_level += 1
                level_up = True

            pet["exp"] = new_exp
            pet["level"] = new_level

            # Evolution checkpoints
            new_stage = pet.get("stage", 1)
            evolution_triggered = False
            evolution_text = ""

            if pet.get("rarity") not in ["Legendary", "God", "Sub-Legendary"]:
                if new_stage == 1 and new_level >= 5:
                    new_stage = 2
                    evolution_triggered = True
                    evolution_text = f"✨ Evolutionary energy is surging! {pet['name']} is evolving into Stage 2: **{pet['stage2_name']}**!"
                elif new_stage == 2 and new_level >= 15:
                    new_stage = 3
                    evolution_triggered = True
                    evolution_text = f"✨ Evolution! {pet['name']} is evolving into its ultimate form, Stage 3: **{pet['stage3_name']}**!"
                elif new_stage == 3 and pet.get("mega_capable") and new_level >= 30:
                    new_stage = 4
                    evolution_triggered = True
                    evolution_text = f"🌟 MYTHICAL MEGA EVOLUTION! {pet['name']} has transcended into **{pet['mega_name']}**!"

            pet["stage"] = new_stage
            pets[str(active_id)] = pet
            current_data["pets"] = pets

            # Save outputs
            nonlocal txn_result
            txn_result.update(
                {
                    "hp_gained": hp_gained,
                    "xp_gained": xp_gained,
                    "level_up": level_up,
                    "evolution_triggered": evolution_triggered,
                    "evolution_text": evolution_text,
                    "new_level": new_level,
                    "pet_id": active_id,
                    "pet_name": pet["name"],
                }
            )
            return current_data

        try:
            updated_user = await self.db_service.run_transaction(user_path, feed_txn)
        except ValueError as ve:
            return False, str(ve), None
        except Exception as e:
            logger.error(f"Feed transaction failed: {e}")
            return False, f"Feeding failed due to database error: {e}", None

        # Build notification message
        res = txn_result
        message = ""
        if res["hp_gained"] > 0:
            message += f"Healed {res['hp_gained']} HP. "
        message += f"Gained {res['xp_gained']} XP. "
        if res["level_up"]:
            message += (
                f"🎉 Level up! {res['pet_name']} is now Level {res['new_level']}! "
            )

        full_message = (
            f"You fed {amount} Focus Fruit(s) to {res['pet_name']}. {message}"
        )
        if res["evolution_triggered"]:
            full_message += f"\n\n{res['evolution_text']}"

        # Fetch the updated pet
        updated_pets = self._normalize_pets(updated_user.get("pets", {}))
        updated_pet = updated_pets[str(res["pet_id"])]
        updated_pet["id"] = int(res["pet_id"])

        return True, full_message, updated_pet

    async def align_existing_pet_prompts(
        self, pet_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Use Gemini to align/correct Stage 2, Stage 3, and Mega visual prompts of an existing pet
        to ensure they strictly share the same color palette, design theme, style, and features of Stage 1.
        """
        from app.domain.models.gacha import AlignedPrompts

        # If it's legendary or god, they do not evolve, no need to align
        if pet_data.get("rarity") in ["Legendary", "God"]:
            return pet_data

        system_prompt = (
            "You are a world-class pocket monster designer. "
            "Your task is to fix mismatched evolution prompts. We have a pocket monster whose Stage 1 "
            "has a specific visual design, color palette, and material composition. "
            "However, its evolved stages (Stage 2, Stage 3, and/or Mega) are currently described with completely different "
            "colors, materials, or species attributes, which makes them feel like a different evolutionary line.\n\n"
            "## Rules:\n"
            "1. You MUST align the names, descriptions, and visual prompts of Stage 2, Stage 3, and Mega with Stage 1.\n"
            "2. Keep the exact same core color palette, base materials, body textures, style, and facial characteristics of Stage 1.\n"
            "3. Make sure the visual prompt describes a larger, older, and more powerful progression of the Stage 1 creature "
            "(e.g., growing larger, getting thicker armor plates of the same material/color, developing horns/wings, more intense elemental effects, transitioning from cute to fierce), "
            "not transforming into a completely different species or changing colors.\n"
            "4. Only describe the creature itself in visual_prompt. Do not include any background or environment."
        )

        user_input = {
            "name": pet_data.get("name"),
            "rarity": pet_data.get("rarity"),
            "concept": pet_data.get("concept"),
            "type1": pet_data.get("type1"),
            "type2": pet_data.get("type2"),
            "stage1": {
                "name": pet_data.get("stage1_name"),
                "description": pet_data.get("stage1_desc"),
                "visual_prompt": pet_data.get("stage1_prompt"),
            },
            "stage2": {
                "name": pet_data.get("stage2_name"),
                "description": pet_data.get("stage2_desc"),
                "visual_prompt": pet_data.get("stage2_prompt"),
            },
            "stage3": {
                "name": pet_data.get("stage3_name"),
                "description": pet_data.get("stage3_desc"),
                "visual_prompt": pet_data.get("stage3_prompt"),
            },
            "mega": {
                "name": pet_data.get("mega_name"),
                "description": pet_data.get("mega_desc"),
                "visual_prompt": pet_data.get("mega_prompt"),
            },
        }

        try:
            logger.info(
                f"Aligning existing pet prompts for {pet_data.get('name')} (ID: {pet_data.get('id')})"
            )
            response = await self.gemini_client.aio.models.generate_content(
                model=settings.GEMINI_PRIMARY_MODEL,
                contents=json.dumps(user_input),
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=AlignedPrompts,
                    temperature=0.3,
                ),
            )

            parsed_data = json.loads(response.text)

            # Update prompts in pet_data dict
            if parsed_data.get("stage2"):
                s2 = parsed_data["stage2"]
                pet_data["stage2_name"] = s2.get("name") or pet_data["stage2_name"]
                pet_data["stage2_desc"] = (
                    s2.get("description") or pet_data["stage2_desc"]
                )
                pet_data["stage2_prompt"] = (
                    s2.get("visual_prompt") or pet_data["stage2_prompt"]
                )

            if parsed_data.get("stage3"):
                s3 = parsed_data["stage3"]
                pet_data["stage3_name"] = s3.get("name") or pet_data["stage3_name"]
                pet_data["stage3_desc"] = (
                    s3.get("description") or pet_data["stage3_desc"]
                )
                pet_data["stage3_prompt"] = (
                    s3.get("visual_prompt") or pet_data["stage3_prompt"]
                )

            if parsed_data.get("mega"):
                m = parsed_data["mega"]
                pet_data["mega_name"] = m.get("name") or pet_data["mega_name"]
                pet_data["mega_desc"] = m.get("description") or pet_data["mega_desc"]
                pet_data["mega_prompt"] = (
                    m.get("visual_prompt") or pet_data["mega_prompt"]
                )

            return pet_data
        except Exception as e:
            logger.error(f"Failed to align pet prompts: {e}", exc_info=True)
            return pet_data

    async def generate_charging_gif(self, current_img_url: str, pet_id: int) -> bytes:
        """Download current stage image and generate a charging GIF."""
        from app.services.gacha.evolution_animator import (
            download_image_bytes,
            generate_charging_gif,
        )

        current_png_bytes = await download_image_bytes(current_img_url)
        return generate_charging_gif(current_png_bytes, pet_id)

    async def generate_complete_evolution_gif(
        self, current_img_url: str, new_png_bytes: bytes, pet_id: int
    ) -> bytes:
        """Download current stage image and generate a complete evolution reveal GIF."""
        from app.services.gacha.evolution_animator import (
            download_image_bytes,
            generate_complete_evolution_gif,
        )

        current_png_bytes = await download_image_bytes(current_img_url)
        return generate_complete_evolution_gif(current_png_bytes, new_png_bytes, pet_id)
