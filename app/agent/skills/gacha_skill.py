import io
import discord
from typing import Any, Dict, List
from google.genai import types
from app.agent.skills.base import BaseSkill
from app.agent.models import SkillContext, SkillResult
from app.services.gacha import GachaService, RARITY_STYLING, format_types
from app.services.pomodoro import PomodoroService
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class GachaSkill(BaseSkill):
    """
    Agent skill for Pokemon Gacha and Pomodoro focus tracking.
    """

    def __init__(self, gacha_service: GachaService, pomodoro_service: PomodoroService):
        self.gacha_service = gacha_service
        self.pomodoro_service = pomodoro_service

    @property
    def name(self) -> str:
        return "gacha_pomodoro"

    @property
    def description(self) -> str:
        return (
            "Handles Pokemon Gacha rolls, collection view, feeding pets coins to evolve them, "
            "and active Pokemon selection and Pomodoro focus sessions to earn currency (FP and Fruits)."
        )

    def get_function_declarations(self) -> List[types.FunctionDeclaration]:
        return [
            types.FunctionDeclaration(
                name="start_pomodoro",
                description="Start a Pomodoro focus session. The user must be in a voice channel.",
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "duration_mins": {
                            "type": "INTEGER",
                            "description": "Duration of focus session in minutes (default 25)",
                        }
                    },
                },
            ),
            types.FunctionDeclaration(
                name="cancel_pomodoro",
                description="Cancel the user's active Pomodoro focus session.",
                parameters={"type": "OBJECT", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="roll_gacha",
                description="Roll a new procedural Pokemon companion. Costs 100 Focus Points (FP).",
                parameters={"type": "OBJECT", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="view_active_pet",
                description="Show the user's currently active Pokemon companion stats, HP, level, and image.",
                parameters={"type": "OBJECT", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="feed_pet",
                description="Feed a specified number of Fruits (each costing 20 Coins) to the active Pokemon companion to restore HP and gain XP/levels.",
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "amount": {
                            "type": "INTEGER",
                            "description": "The number of fruits to feed (must be a positive integer, defaults to 1)",
                        }
                    },
                },
            ),
        ]

    async def execute(
        self, function_name: str, args: Dict[str, Any], context: SkillContext
    ) -> SkillResult:
        client = (
            context.discord_interaction.client if context.discord_interaction else None
        )
        if not client:
            return SkillResult(
                success=False, message="Discord client not available in context."
            )

        if function_name == "start_pomodoro":
            # 1. Voice channel check
            if (
                not context.discord_member
                or not context.discord_member.voice
                or not context.discord_member.voice.channel
            ):
                return SkillResult(
                    success=False,
                    message="❌ You must join a voice channel before starting a Pomodoro session!",
                )

            duration = args.get("duration_mins") or 25
            voice_channel = context.discord_member.voice.channel

            # 2. Call service to set DB state
            success, msg = await self.pomodoro_service.start_session(
                context.user_id, str(voice_channel.id), context.channel_id, duration
            )

            if not success:
                return SkillResult(success=False, message=msg)

            # 3. Retrieve GachaCog from client to launch tracker task
            cog = client.get_cog("GachaCog")
            if cog:
                client.loop.create_task(
                    cog.pomodoro_tracker(
                        context.user_id, duration, int(context.channel_id)
                    )
                )
            else:
                logger.warning(
                    "GachaCog not found in bot. Pomodoro tracker background task NOT launched."
                )

            embed = discord.Embed(
                title="⏱️ Pomodoro Session Started via AI!",
                description=(
                    f"**User**: {context.discord_member.mention}\n"
                    f"**Focus Channel**: {voice_channel.mention}\n"
                    f"**Duration**: {duration} minutes\n\n"
                    "Stay in the voice channel to earn 100 FP and 1 Focus Fruit!"
                ),
                color=0x5865F2,
            )
            return SkillResult(
                success=True, message="Focus session successfully started.", embed=embed
            )

        elif function_name == "cancel_pomodoro":
            success, msg = await self.pomodoro_service.cancel_session(
                context.user_id, penalize=True
            )
            if not success:
                return SkillResult(success=False, message=msg)

            embed = discord.Embed(
                title="❌ Pomodoro Focus Cancelled", description=msg, color=0xED4245
            )
            return SkillResult(
                success=True, message="Focus session cancelled.", embed=embed
            )

        elif function_name == "roll_gacha":
            await self.gacha_service.check_or_create_user(None, context.user_id)
            coins_data = await client.attendance_service.get_user_coins(context.user_id)
            coins = coins_data["attendance_coins"]

            if coins < 100:
                return SkillResult(
                    success=False,
                    message=f"❌ You do not have enough Coins! (You have: {coins} Coins, need: 100 Coins). Join voice rooms to earn more!",
                )

            try:
                # Roll attributes first to ensure compatibility with weights and single-stage pets
                attrs = self.gacha_service._roll_attributes()
                # Roll and process
                (
                    pet_id,
                    pet_dict,
                    hd_bytes,
                    pixel_bytes,
                ) = await self.gacha_service.roll_gacha(
                    context.user_id, pre_rolled_attrs=attrs
                )

                # Upload to hosting channel
                image_channel = client.get_channel(settings.GACHA_IMAGE_CHANNEL_ID)
                if not image_channel:
                    image_channel = await client.fetch_channel(
                        settings.GACHA_IMAGE_CHANNEL_ID
                    )

                pixel_file = discord.File(
                    io.BytesIO(pixel_bytes), filename=f"pet_{pet_id}_pixel.png"
                )

                msg = await image_channel.send(
                    content=f"Assets for Pet ID {pet_id} rolled by AI User {context.user_id}",
                    file=pixel_file,
                )

                pixel_url = msg.attachments[0].url
                hd_url = pixel_url

                await self.gacha_service.update_pet_image(
                    context.user_id, pet_id, stage=1, hd_url=hd_url, pixel_url=pixel_url
                )

                type_str = format_types(pet_dict["type1"], pet_dict["type2"])
                rarity_name = pet_dict.get("rarity", "Common")
                style = RARITY_STYLING.get(rarity_name, RARITY_STYLING["Common"])

                embed = discord.Embed(
                    title=style["title"],
                    description=(
                        f"**Name**: {pet_dict['name']}\n"
                        f"**Rarity**: {style['rarity_formatted']}\n"
                        f"**Types**: {type_str}\n\n"
                        f"**Description**:\n{pet_dict['stage1_desc']}"
                    ),
                    color=style["color"],
                )
                embed.set_image(url=pixel_url)
                embed.set_footer(
                    text=f"Pet ID: {pet_id} | Level 1 | HP: 100/100"
                    + (" (Active Companion)" if pet_dict["active"] else "")
                )

                # Lazy import GachaHDView to avoid circular imports
                from app.presentation.gacha_cog import GachaHDView

                view = GachaHDView(hd_url)

                return SkillResult(
                    success=True,
                    message="Successfully rolled a new pet companion!",
                    embed=embed,
                    view=view,
                )

            except Exception as e:
                logger.error(f"Gacha skill execution failed: {e}", exc_info=True)
                if "PixelLabError" in type(e).__name__ or "timeout" in str(e).lower():
                    err_msg = "❌ Cửa hàng triệu hồi thú cưng đang tạm thời đóng cửa do họa sĩ vẽ pet bị ngất xỉu (API Timeout/Error). Vui lòng thử lại sau nhé! 😴"
                else:
                    err_msg = f"Cloudflare AI failed to process this roll: {e}"
                return SkillResult(
                    success=False,
                    message=err_msg,
                )

        elif function_name == "view_active_pet":
            pet = await self.gacha_service.get_active_pet(context.user_id)
            if not pet:
                return SkillResult(
                    success=False,
                    message="❌ You do not have an active pet. Ask me to roll gacha for you!",
                )

            stage = pet["stage"]
            stage_name = pet[f"stage{stage}_name"] if stage <= 3 else pet["mega_name"]
            stage_desc = pet[f"stage{stage}_desc"] if stage <= 3 else pet["mega_desc"]
            stage_img = pet[f"stage{stage}_img"] if stage <= 3 else pet["mega_img"]
            type_str = format_types(pet["type1"], pet["type2"])

            embed = discord.Embed(
                title=f"🐾 Active Companion: {pet['name']}",
                description=(
                    f"**Level**: {pet['level']} (XP: {pet['exp']}/100)\n"
                    f"**HP**: {pet['hp']}/100\n"
                    f"**Types**: {type_str}\n"
                    f"**Evolution**: Stage {stage} - **{stage_name}**\n\n"
                    f"**Description**:\n{stage_desc}"
                ),
                color=0x57F287,
            )
            if stage_img:
                embed.set_image(url=stage_img)
            embed.set_footer(text=f"Pet ID: {pet['id']} | Concept: {pet['concept']}")

            return SkillResult(
                success=True,
                message=f"Here is your active companion: {pet['name']}",
                embed=embed,
            )

        elif function_name == "feed_pet":
            pet_before = await self.gacha_service.get_active_pet(context.user_id)
            if not pet_before:
                return SkillResult(
                    success=False,
                    message="❌ You do not have an active pet. Ask me to roll gacha for you!",
                )

            amount = args.get("amount") or 1
            if not isinstance(amount, int) or amount <= 0:
                return SkillResult(
                    success=False,
                    message="❌ Feeding amount must be a positive integer!",
                )

            success, msg, updated_pet = await self.gacha_service.feed_active_pet(
                context.user_id, amount
            )
            if not success:
                return SkillResult(success=False, message=msg)

            # Check evolution
            if updated_pet["stage"] > pet_before["stage"]:
                new_stage = updated_pet["stage"]
                stage_name = (
                    updated_pet[f"stage{new_stage}_name"]
                    if new_stage <= 3
                    else updated_pet["mega_name"]
                )

                interaction = context.discord_interaction
                if interaction:
                    # 1. Immediately send charging GIF notification
                    evolution_msg_obj = None
                    try:
                        prev_stage = pet_before["stage"]
                        current_img_url = (
                            pet_before[f"stage{prev_stage}_img"]
                            if prev_stage <= 3
                            else pet_before["mega_img"]
                        )

                        if current_img_url:
                            charging_gif_bytes = (
                                await self.gacha_service.generate_charging_gif(
                                    current_img_url, updated_pet["id"]
                                )
                            )

                            charging_file = discord.File(
                                io.BytesIO(charging_gif_bytes), filename="evolving.gif"
                            )

                            embed_evolving = discord.Embed(
                                title=f"✨ Evolutionary energy is surging! {pet_before['name']} is evolving...",
                                description=(
                                    f"{msg}\n\n"
                                    f"**Current Form**: Stage {prev_stage}\n"
                                    f"**Evolving Into**: Stage {new_stage} - **{stage_name}**\n\n"
                                    f"🎨 Charging energy and synthesizing power... Please wait! ⌛"
                                ),
                                color=0x5865F2,
                            )
                            embed_evolving.set_image(url="attachment://evolving.gif")
                            evolution_msg_obj = await interaction.followup.send(
                                embed=embed_evolving, file=charging_file, wait=True
                            )
                        else:
                            evolution_msg_obj = await interaction.followup.send(
                                content=f"✨ {msg}\n\n{pet_before['name']} is evolving to Stage {new_stage}! Designing new form..."
                            )
                    except Exception as e:
                        logger.error(
                            f"Failed to send evolution charging status in skill: {e}",
                            exc_info=True,
                        )
                        evolution_msg_obj = await interaction.followup.send(
                            content=f"✨ {msg}\n\n{pet_before['name']} is evolving to Stage {new_stage}! Designing new form..."
                        )

                    # 2. Asynchronously call image generator & build complete evolution GIF
                    try:
                        # Fetch prompt for this stage
                        if new_stage == 2:
                            prompt = updated_pet["stage2_prompt"]
                        elif new_stage == 3:
                            prompt = updated_pet["stage3_prompt"]
                        else:
                            prompt = updated_pet["mega_prompt"]

                        prev_img_url = (
                            updated_pet[f"stage{new_stage - 1}_img"]
                            if new_stage <= 3
                            else updated_pet["stage3_img"]
                        )

                        pixel_bytes = await self.gacha_service.generate_evolution_image(
                            prompt, prev_img_url
                        )

                        # Build final complete evolution GIF bytes
                        current_img_url = (
                            pet_before[f"stage{prev_stage}_img"]
                            if prev_stage <= 3
                            else pet_before["mega_img"]
                        )

                        final_gif_bytes = None
                        if current_img_url:
                            try:
                                final_gif_bytes = await self.gacha_service.generate_complete_evolution_gif(
                                    current_img_url, pixel_bytes, updated_pet["id"]
                                )
                            except Exception as ge:
                                logger.error(
                                    f"Failed to generate complete evolution GIF in skill: {ge}",
                                    exc_info=True,
                                )

                        # Upload static pixel PNG to Discord Image channel
                        image_channel = client.get_channel(
                            settings.GACHA_IMAGE_CHANNEL_ID
                        )
                        if not image_channel:
                            image_channel = await client.fetch_channel(
                                settings.GACHA_IMAGE_CHANNEL_ID
                            )

                        pixel_file = discord.File(
                            io.BytesIO(pixel_bytes),
                            filename=f"pet_{updated_pet['id']}_s{new_stage}_pixel.png",
                        )

                        upload_msg = await image_channel.send(
                            content=f"Evolved Asset for Pet ID {updated_pet['id']} Stage {new_stage}",
                            file=pixel_file,
                        )

                        pixel_url = upload_msg.attachments[0].url
                        hd_url = pixel_url

                        # Save static URL in DB
                        await self.gacha_service.update_pet_image(
                            context.user_id,
                            updated_pet["id"],
                            stage=new_stage,
                            hd_url=hd_url,
                            pixel_url=pixel_url,
                        )

                        # Upload final GIF to channel if compiled successfully
                        evolution_gif_url = None
                        if final_gif_bytes:
                            gif_file = discord.File(
                                io.BytesIO(final_gif_bytes),
                                filename=f"pet_{updated_pet['id']}_s{new_stage}_evolution.gif",
                            )
                            gif_upload_msg = await image_channel.send(
                                content=f"Evolution Anim for Pet ID {updated_pet['id']} Stage {new_stage}",
                                file=gif_file,
                            )
                            evolution_gif_url = gif_upload_msg.attachments[0].url

                        # Refresh updated pet dictionary
                        updated_pet = await self.gacha_service.get_active_pet(
                            context.user_id
                        )

                        # Edit the charging message to show completed evolution with the final animation GIF
                        embed_final = discord.Embed(
                            title=f"🎉 EVOLUTION COMPLETE: {updated_pet['name']} has evolved!",
                            description=(
                                f"**New Form**: Stage {new_stage} - **{stage_name}**\n"
                                f"**Level**: {updated_pet['level']} (XP: {updated_pet['exp']}/100)\n"
                                f"**HP**: {updated_pet['hp']}/100\n\n"
                                f"**New Description**:\n{updated_pet[f'stage{new_stage}_desc' if new_stage <= 3 else 'mega_desc']}"
                            ),
                            color=0x57F287,
                        )

                        display_img_url = evolution_gif_url or pixel_url
                        embed_final.set_image(url=display_img_url)

                        if evolution_msg_obj:
                            await evolution_msg_obj.edit(
                                embed=embed_final, attachments=[]
                            )
                        else:
                            await interaction.followup.send(embed=embed_final)

                    except Exception as e:
                        logger.error(
                            f"Image generation/evolution failed in skill: {e}",
                            exc_info=True,
                        )
                        err_msg = (
                            f"\n⚠️ Image generation failed for this evolution stage: {e}"
                        )
                        if evolution_msg_obj:
                            embed_err = discord.Embed(
                                title="❌ Evolution Interrupted",
                                description=f"{msg}\n\nFailed to finalize evolution graphic: {e}",
                                color=0xED4245,
                            )
                            await evolution_msg_obj.edit(
                                embed=embed_err, attachments=[]
                            )
                        else:
                            await interaction.followup.send(content=err_msg)

                    # Return success but empty response since we edited/sent the message directly
                    return SkillResult(
                        success=True,
                        message=None,
                        embed=None,
                    )
                else:
                    # Blocking fallback if no interaction context available
                    try:
                        prompt = (
                            updated_pet[f"stage{new_stage}_prompt"]
                            if new_stage <= 3
                            else updated_pet["mega_prompt"]
                        )
                        prev_img_url = (
                            updated_pet[f"stage{new_stage - 1}_img"]
                            if new_stage <= 3
                            else updated_pet["stage3_img"]
                        )
                        pixel_bytes = await self.gacha_service.generate_evolution_image(
                            prompt, prev_img_url
                        )
                        # We won't do full GIF here, just update image
                        image_channel = client.get_channel(
                            settings.GACHA_IMAGE_CHANNEL_ID
                        )
                        if not image_channel:
                            image_channel = await client.fetch_channel(
                                settings.GACHA_IMAGE_CHANNEL_ID
                            )
                        pixel_file = discord.File(
                            io.BytesIO(pixel_bytes),
                            filename=f"pet_{updated_pet['id']}_s{new_stage}_pixel.png",
                        )
                        upload_msg = await image_channel.send(
                            content=f"Evolved Asset for Pet ID {updated_pet['id']} Stage {new_stage}",
                            file=pixel_file,
                        )
                        pixel_url = upload_msg.attachments[0].url
                        await self.gacha_service.update_pet_image(
                            context.user_id,
                            updated_pet["id"],
                            stage=new_stage,
                            hd_url=pixel_url,
                            pixel_url=pixel_url,
                        )
                        updated_pet = await self.gacha_service.get_active_pet(
                            context.user_id
                        )
                    except Exception as e:
                        logger.error(
                            f"Fallback evolution image generation failed: {e}",
                            exc_info=True,
                        )
                        msg += f"\n⚠️ Image generation failed for evolution: {e}"

            stage_name = (
                updated_pet[f"stage{updated_pet['stage']}_name"]
                if updated_pet["stage"] <= 3
                else updated_pet["mega_name"]
            )
            embed = discord.Embed(
                title=f"🍎 Feeding Time: {updated_pet['name']}",
                description=(
                    f"{msg}\n\n"
                    f"**Level**: {updated_pet['level']} (XP: {updated_pet['exp']}/100)\n"
                    f"**HP**: {updated_pet['hp']}/100\n"
                    f"**Form**: Stage {updated_pet['stage']} - **{stage_name}**"
                ),
                color=0x57F287,
            )
            img_url = (
                updated_pet[f"stage{updated_pet['stage']}_img"]
                if updated_pet["stage"] <= 3
                else updated_pet["mega_img"]
            )
            if img_url:
                embed.set_image(url=img_url)

            return SkillResult(
                success=True,
                message=f"Successfully fed {updated_pet['name']}.",
                embed=embed,
            )

        return SkillResult(
            success=False,
            message=f"Action '{function_name}' is not supported by GachaSkill.",
        )
