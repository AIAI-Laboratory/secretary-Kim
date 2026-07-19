import io
import asyncio
from typing import Optional
import discord
from discord.ext import commands
from discord import app_commands
from app.core.config import settings
from app.core.logger import get_logger
from app.services.gacha import GachaService, RARITY_STYLING, format_types
from app.services.pomodoro import PomodoroService

logger = get_logger(__name__)


class GachaHDView(discord.ui.View):
    """View containing a button to view the original HD image."""

    def __init__(self, hd_url: str):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="🖼️ View HD Image", url=hd_url, style=discord.ButtonStyle.link
            )
        )


class PetListSelect(discord.ui.Select):
    """Select dropdown to set active pet."""

    def __init__(self, pets, cog):
        self.cog = cog
        options = []
        for p in pets[:25]:  # Discord select allows max 25 options
            type_str = format_types(p["type1"], p["type2"])
            label = f"ID {p['id']}: {p['name']} (Lv.{p['level']} {p['rarity']})"
            desc = f"Stage {p['stage']} | Type: {type_str} | HP: {p['hp']}/100"
            options.append(
                discord.SelectOption(label=label, description=desc, value=str(p["id"]))
            )

        super().__init__(
            placeholder="Choose a pet to set as Active...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        pet_id = int(self.values[0])
        success = await self.cog.gacha_service.set_active_pet(
            str(interaction.user.id), pet_id
        )
        if success:
            await interaction.response.send_message(
                f"✅ Set pet ID **{pet_id}** as your Active companion!", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Failed to set active pet. Make sure you own this pet.",
                ephemeral=True,
            )


class PetListView(discord.ui.View):
    """View for listing pets with a dropdown selector."""

    def __init__(self, pets, cog):
        super().__init__(timeout=180)
        self.add_item(PetListSelect(pets, cog))


class GachaCog(commands.Cog):
    """Cog containing Pomodoro focus tracker and Pokemon Gacha commands."""

    def __init__(self, bot):
        self.bot = bot
        self.gacha_service: GachaService = bot.gacha_service
        self.pomodoro_service: PomodoroService = bot.pomodoro_service

    @app_commands.command(
        name="pomodoro-start",
        description="Start a 25-minute Pomodoro focus session in your current voice channel",
    )
    @app_commands.describe(duration="Focus duration in minutes (default 25)")
    async def pomodoro_start(
        self, interaction: discord.Interaction, duration: Optional[int] = 25
    ):
        if not interaction.user.voice or not interaction.user.voice.channel:
            embed = discord.Embed(
                description="❌ You must join a voice channel before starting a Pomodoro session!",
                color=0xED4245,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        user_id = str(interaction.user.id)
        voice_channel = interaction.user.voice.channel
        text_channel = interaction.channel

        # Start the session in database
        success, msg = await self.pomodoro_service.start_session(
            user_id, str(voice_channel.id), str(text_channel.id), duration
        )

        if not success:
            embed = discord.Embed(description=f"❌ {msg}", color=0xED4245)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="⏱️ Pomodoro Session Started!",
            description=(
                f"**User**: {interaction.user.mention}\n"
                f"**Focus Channel**: {voice_channel.mention}\n"
                f"**Duration**: {duration} minutes\n\n"
                "Stay in the voice channel to complete your session. Disconnecting or switching channels will cancel the session and hurt your active pet's HP!"
            ),
            color=0x5865F2,  # Discord Blurple
        )
        await interaction.response.send_message(embed=embed)

        # Launch background tracker task
        self.bot.loop.create_task(
            self.pomodoro_tracker(user_id, duration, text_channel.id)
        )

    @app_commands.command(
        name="pomodoro-cancel", description="Cancel your active Pomodoro focus session"
    )
    async def pomodoro_cancel(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        success, msg = await self.pomodoro_service.cancel_session(
            user_id, penalize=True
        )

        if not success:
            embed = discord.Embed(description=f"❌ {msg}", color=0xED4245)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="❌ Pomodoro Focus Cancelled", description=msg, color=0xED4245
        )
        await interaction.response.send_message(embed=embed)

    async def pomodoro_tracker(
        self, user_id: str, duration_mins: int, text_channel_id: int
    ):
        """Asynchronous tracker that waits for the duration and awards points if user is still focused."""
        await asyncio.sleep(duration_mins * 60)

        session = await self.pomodoro_service.get_active_session(user_id)
        if not session:
            return  # Already cancelled/handled by state changes

        # Check if user is still in the voice channel
        member = None
        for guild in self.bot.guilds:
            member = guild.get_member(int(user_id))
            if member:
                break

        if (
            not member
            or not member.voice
            or not member.voice.channel
            or str(member.voice.channel.id) != session["channel_id"]
        ):
            # User left voice channel, cancel session
            await self.pomodoro_service.cancel_session(user_id, penalize=True)
            channel = self.bot.get_channel(text_channel_id)
            if channel:
                embed = discord.Embed(
                    title="❌ Focus Interrupted!",
                    description=f"<@{user_id}> left their voice channel before completion. Pomodoro cancelled!",
                    color=0xED4245,
                )
                await channel.send(embed=embed)
            return

        # Success!
        success, msg, data = await self.pomodoro_service.complete_session(user_id)
        if success:
            channel = self.bot.get_channel(text_channel_id)
            if channel:
                embed = discord.Embed(
                    title="🏆 Focus Session Completed!",
                    description=msg,
                    color=0x57F287,  # Emerald Green
                )
                embed.set_footer(text="Focus Session Completed successfully!")
                await channel.send(content=f"<@{user_id}>", embed=embed)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """Real-time voice activity listener to detect early disconnection."""
        if member.bot:
            return

        user_id = str(member.id)
        session = await self.pomodoro_service.get_active_session(user_id)
        if not session:
            return

        # Check if the user left their voice channel
        target_voice_id = session["channel_id"]
        left_voice = before.channel is not None and after.channel is None
        switched_voice = (
            before.channel is not None
            and after.channel is not None
            and str(before.channel.id) == target_voice_id
            and str(after.channel.id) != target_voice_id
        )

        if left_voice or switched_voice:
            # Cancel session and apply HP penalty
            success, msg = await self.pomodoro_service.cancel_session(
                user_id, penalize=True
            )
            if success:
                text_channel_id = int(session["text_channel_id"])
                channel = self.bot.get_channel(text_channel_id)
                if channel:
                    embed = discord.Embed(
                        title="❌ Focus Interrupted!",
                        description=f"{member.mention} left the voice channel. {msg}",
                        color=0xED4245,
                    )
                    await channel.send(content=member.mention, embed=embed)

    @app_commands.command(
        name="gacha",
        description="Roll a procedural Pokemon companion (Costs 100 Coins)",
    )
    async def gacha(self, interaction: discord.Interaction):
        # Acknowledge immediately WITHOUT showing "is thinking..." loading state
        await interaction.response.defer(thinking=False)

        user_id = str(interaction.user.id)

        # 1. Roll attributes immediately (quick)
        attrs = self.gacha_service._roll_attributes()
        rarity = attrs["rarity"]

        # Map rarity to GIF loader
        gif_map = {
            "Common": "common.gif",
            "Epic": "epic.gif",
            "Legendary": "legendary.gif",
            "God": "god.gif",
            "Sub-Legendary": "legendary.gif",
        }
        gif_filename = gif_map.get(rarity, "common.gif")
        gif_path = f"app/services/resources/{gif_filename}"

        # Send loading GIF as followup
        loading_file = discord.File(gif_path, filename=gif_filename)
        loading_embed = discord.Embed(
            title=f"🔮 Summoning {rarity} Companion...",
            description="Designing and drawing your new pet... Please wait! ⌛",
            color=0x5865F2,
        )
        loading_embed.set_image(url=f"attachment://{gif_filename}")
        loading_msg = await interaction.followup.send(
            embed=loading_embed, file=loading_file, wait=True
        )

        try:
            # 2. Verify currency (safe now that we've responded)
            coins_data = await self.bot.attendance_service.get_user_coins(user_id)
            coins = coins_data["attendance_coins"]

            if coins < 100:
                embed = discord.Embed(
                    description=f"❌ You do not have enough Coins! (You have: {coins} Coins, need: 100 Coins). Join voice rooms to earn more!",
                    color=0xED4245,
                )
                await loading_msg.edit(embed=embed, attachments=[])
                return

            # 3. Roll Gacha (pass pre-rolled attributes)
            (
                pet_id,
                pet_dict,
                hd_bytes,
                pixel_bytes,
            ) = await self.gacha_service.roll_gacha(user_id, pre_rolled_attrs=attrs)

            # 3. Upload images to Discord channel to host them
            image_channel = self.bot.get_channel(settings.GACHA_IMAGE_CHANNEL_ID)
            if not image_channel:
                image_channel = await self.bot.fetch_channel(
                    settings.GACHA_IMAGE_CHANNEL_ID
                )

            pixel_file = discord.File(
                io.BytesIO(pixel_bytes), filename=f"pet_{pet_id}_pixel.png"
            )

            msg = await image_channel.send(
                content=f"Assets for Pet ID {pet_id} owned by User {user_id}",
                file=pixel_file,
            )

            # Retrieve URLs
            pixel_url = msg.attachments[0].url
            hd_url = pixel_url

            # 4. Update DB
            await self.gacha_service.update_pet_image(
                user_id, pet_id, stage=1, hd_url=hd_url, pixel_url=pixel_url
            )

            # 5. Show output
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

            view = GachaHDView(hd_url)
            await loading_msg.edit(embed=embed, attachments=[], view=view)

        except Exception as e:
            logger.error(f"Gacha slash command failed: {e}", exc_info=True)

            # Check for PixelLab timeout or other PixelLab issues
            if "PixelLabError" in type(e).__name__ or "timeout" in str(e).lower():
                err_msg = "❌ Cửa hàng triệu hồi thú cưng đang tạm thời đóng cửa do họa sĩ vẽ pet bị ngất xỉu (API Timeout/Error). Vui lòng thử lại sau nhé! 😴"
            else:
                err_msg = "❌ Failed to roll gacha. AI encountered an error. Please try again."

            error_embed = discord.Embed(
                description=err_msg,
                color=0xED4245,
            )
            try:
                await loading_msg.edit(embed=error_embed, attachments=[])
            except Exception:
                pass

    @app_commands.command(
        name="pet-active",
        description="Show stats and image of your active Pokemon companion",
    )
    async def pet_active(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        pet = await self.gacha_service.get_active_pet(user_id)
        if not pet:
            embed = discord.Embed(
                description="❌ You do not have an active pet. Use `/gacha` to roll a new companion!",
                color=0xED4245,
            )
            await interaction.response.send_message(embed=embed)
            return

        # Determine current stage details
        stage = pet["stage"]
        stage_name = pet[f"stage{stage}_name"] if stage <= 3 else pet["mega_name"]
        stage_desc = pet[f"stage{stage}_desc"] if stage <= 3 else pet["mega_desc"]
        stage_img = pet[f"stage{stage}_img"] if stage <= 3 else pet["mega_img"]

        # If the image URL is not uploaded yet, we try to fall back or show description
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
            color=0x57F287,  # Emerald Green
        )
        if stage_img:
            embed.set_image(url=stage_img)

        embed.set_footer(text=f"Pet ID: {pet['id']} | Concept: {pet['concept']}")

        # Look for HD URL to set view button
        # HD is the attachment of the message, but if we don't have it directly stored in DB, we can default or retrieve. Let's build a nice button if we have URLs.
        # Note: we stored pixelated image in stageX_img, HD image can be viewed via Discord attachments if needed, but since we didn't add extra columns for HD urls, we can use pixelated directly or log it. Let's make sure it operates neatly.
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="pet-list", description="List all Pokemon companions in your collection"
    )
    async def pet_list(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        pets = await self.gacha_service.get_user_pets(user_id)
        if not pets:
            embed = discord.Embed(
                description="❌ Your inventory is empty. Join voice rooms to earn Coins, then use `/gacha`!",
                color=0xED4245,
            )
            await interaction.response.send_message(embed=embed)
            return

        user_profile = await self.gacha_service.check_or_create_user(None, user_id)
        active_id = user_profile["active_pet_id"]

        coins_data = await self.bot.attendance_service.get_user_coins(user_id)
        coins = coins_data["attendance_coins"]

        embed = discord.Embed(
            title=f"🎒 collection: {interaction.user.display_name}'s Companions",
            color=0x5865F2,
        )

        lines = []
        for p in pets:
            active_marker = "⭐ [Active] " if p["id"] == active_id else ""
            type_str = format_types(p["type1"], p["type2"])
            lines.append(
                f"- {active_marker}**ID {p['id']}**: {p['name']} (Lv.{p['level']} - Stage {p['stage']} - {p['rarity']} - {type_str}) - HP: {p['hp']}/100"
            )

        embed.description = "\n".join(lines)

        embed.set_footer(text=f"Total: {len(pets)} pets | Coins: {coins}")

        # Display dropdown selector to set active companion
        view = PetListView(pets, self)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(
        name="feed",
        description="Feed Fruits to your active companion (+XP, +HP, trigger evolutions)",
    )
    @app_commands.describe(
        amount="Number of times / fruits to feed (default 1, must be positive)"
    )
    async def feed(self, interaction: discord.Interaction, amount: Optional[int] = 1):
        # Defer immediately to avoid timeout (3-second window)
        await interaction.response.defer()

        if amount is None:
            amount = 1

        if amount <= 0:
            embed = discord.Embed(
                description="❌ Feeding amount must be a positive integer!",
                color=0xED4245,
            )
            await interaction.followup.send(embed=embed)
            return

        user_id = str(interaction.user.id)

        # Verify coins first
        coins_data = await self.bot.attendance_service.get_user_coins(user_id)
        coins = coins_data["attendance_coins"]

        cost = 20 * amount
        if coins < cost:
            embed = discord.Embed(
                description=f"❌ You do not have enough Coins! (You have: {coins} Coins, need: {cost} Coins to feed {amount} time(s)). Join voice rooms to earn more!",
                color=0xED4245,
            )
            await interaction.followup.send(embed=embed)
            return

        # Fetch current pet and state before feeding
        pet_before = await self.gacha_service.get_active_pet(user_id)
        if not pet_before:
            embed = discord.Embed(
                description="❌ You do not have an active pet. Use `/gacha` to roll a new companion!",
                color=0xED4245,
            )
            await interaction.followup.send(embed=embed)
            return

        # Call feed active pet
        success, msg, updated_pet = await self.gacha_service.feed_active_pet(
            user_id, amount
        )
        if not success:
            embed = discord.Embed(description=f"❌ {msg}", color=0xED4245)
            await interaction.followup.send(embed=embed)
            return

        # Check for evolution
        if updated_pet["stage"] > pet_before["stage"]:
            new_stage = updated_pet["stage"]
            stage_name = (
                updated_pet[f"stage{new_stage}_name"]
                if new_stage <= 3
                else updated_pet["mega_name"]
            )

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
                    charging_gif_bytes = await self.gacha_service.generate_charging_gif(
                        current_img_url, updated_pet["id"]
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
                    f"Failed to send evolution charging status: {e}", exc_info=True
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

                # Call PixelLab service to generate PNG
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
                        final_gif_bytes = (
                            await self.gacha_service.generate_complete_evolution_gif(
                                current_img_url, pixel_bytes, updated_pet["id"]
                            )
                        )
                    except Exception as ge:
                        logger.error(
                            f"Failed to generate complete evolution GIF: {ge}",
                            exc_info=True,
                        )

                # Upload static pixel PNG to Discord Image channel
                image_channel = self.bot.get_channel(settings.GACHA_IMAGE_CHANNEL_ID)
                if not image_channel:
                    image_channel = await self.bot.fetch_channel(
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
                    user_id,
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
                updated_pet = await self.gacha_service.get_active_pet(user_id)

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

                # Show the animated GIF if available, otherwise fallback to static
                display_img_url = evolution_gif_url or pixel_url
                embed_final.set_image(url=display_img_url)

                if evolution_msg_obj:
                    await evolution_msg_obj.edit(embed=embed_final, attachments=[])
                else:
                    await interaction.followup.send(embed=embed_final)

            except Exception as e:
                logger.error(f"Image generation/evolution failed: {e}", exc_info=True)
                err_msg = f"\n⚠️ Image generation failed for this evolution stage: {e}"

                # Rollback pet stage in DB so the user can attempt evolution again later
                try:
                    await self.gacha_service.rollback_pet_stage(
                        user_id, updated_pet["id"], pet_before["stage"]
                    )
                except Exception as re:
                    logger.error(f"Failed to rollback pet stage: {re}", exc_info=True)

                if evolution_msg_obj:
                    embed_err = discord.Embed(
                        title="❌ Evolution Interrupted",
                        description=(
                            f"{msg}\n\nFailed to finalize evolution graphic: {e}\n\n"
                            f"*Note: Your pet's level and XP have been saved, but the evolution was rolled back so you can try again later.*"
                        ),
                        color=0xED4245,
                    )
                    await evolution_msg_obj.edit(embed=embed_err, attachments=[])
                else:
                    await interaction.followup.send(content=err_msg)

            return

        # Display final standard response if NO evolution occurred
        format_types(updated_pet["type1"], updated_pet["type2"])
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

        await interaction.followup.send(embed=embed)
