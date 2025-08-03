import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from datetime import datetime
import json
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
CONFIG_FILE = "like_channels.json"

class LikeCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_host = "https://likexthug.vercel.app/like?uid={uid}&region={region}&key=GREAT"
        self.config_data = self.load_config()
        self.cooldowns = {}
        self.session = aiohttp.ClientSession()

        self.headers = {}
        if RAPIDAPI_KEY:
            self.headers = {
                'x-rapidapi-key': RAPIDAPI_KEY,
                'x-rapidapi-host': "free-fire-like1.p.rapidapi.com"
            }

    def load_config(self):
        default_config = {
            "servers": {}
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    loaded_config = json.load(f)
                    loaded_config.setdefault("servers", {})
                    return loaded_config
            except json.JSONDecodeError:
                print(f"WARNING: The configuration file '{CONFIG_FILE}' is corrupt or empty. Resetting to default configuration.")
        self.save_config(default_config)
        return default_config

    def save_config(self, config_to_save=None):
        data_to_save = config_to_save if config_to_save is not None else self.config_data
        temp_file = CONFIG_FILE + ".tmp"
        with open(temp_file, 'w') as f:
            json.dump(data_to_save, f, indent=4)
        os.replace(temp_file, CONFIG_FILE)

    async def check_channel(self, ctx):
        if ctx.guild is None:
            return True
        guild_id = str(ctx.guild.id)
        like_channels = self.config_data["servers"].get(guild_id, {}).get("like_channels", [])
        return not like_channels or str(ctx.channel.id) in like_channels

    async def cog_load(self):
        pass

    @commands.hybrid_command(name="setlikechannel", description="Sets the channels where the /like command is allowed.")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(channel="The channel to allow/disallow the /like command in.")
    async def like_command(self, ctx: commands.Context, region: str = None, uid: str = None):
        user_id = str(ctx.author.id)
        is_slash = hasattr(ctx, "interaction") and ctx.interaction is not None
        if ctx.prefix and not await self.is_channel_allowed(ctx.channel):

            await ctx.send(f"❌ This command can only be used in designated channels. Please use one of the allowed channels.", ephemeral=True)
            return

        effective_limit_info = self.get_effective_limit_for_user(ctx.author)
        if not effective_limit_info["unlimited"]:
            if not self.check_request_limit_for_user(ctx.author):
                daily_limit_for_message = effective_limit_info["limit"]
                return await self._daily_limit(ctx, daily_limit_for_message)

        if uid is None and region and region.isdigit():
            uid, region = region, None

        if not region or not uid:
            await self._not_region(ctx)
            # No need to delete ctx.message here if _not_region handles it.
            return

        region_map = {
            "ind": "ind",
            "br": "nx", "us": "nx", "sac": "nx", "na": "nx", "nx": "nx"
        }
        region_server = region_map.get(region.lower(), "ag")

        try:
            async with ctx.typing():
                async with self.session.get(f"https://likexthug.vercel.app/like?uid={uid}&region={region_server}&key=GREAT") as response:
                    if response.status != 200:
                        return await self._send_api_error(ctx)

                    data = await response.json()
                    status_code = data.get("status")

                    embed = discord.Embed(
                        title="```FREE FIRE LIKE```",
                        color=0x2ECC71 if status_code == 1 else 0xE74C3C,
                        timestamp=datetime.now()
                    )
                    embed.set_thumbnail(url=ctx.author.display_avatar.url)

                    if effective_limit_info["unlimited"]:
                        limit_info = "Unlimited usage "
                    else:
                        self.check_and_reset_user_daily_limit(user_id)
                        used = self.get_user_daily_usage(user_id).get("count", 0)
                        remaining = effective_limit_info['limit'] - used
                        limit_info = f" Requests remaining: {remaining}/{effective_limit_info['limit']}"

                    if status_code == 1:
                        player = data.get("player", {})
                        likes = data.get("likes", {})

                        embed.description = (
                            f"```\n"
                            f"┌  ACCOUNT\n"
                            f"├─ NICKNAME:{player.get('nickname', 'Unknown')}\n"
                            f"├─ UID:{player.get('uid', 'Unknown')}\n"
                            f"├─ REGION:{player.get('region', region.upper())}\n"
                            f"└─ RESULT:\n"
                            f"    ├─ ADDED:+{likes.get('added_by_api', 0)}\n"
                            f"    ├─ BEFORE:{likes.get('before', 'N/A')}\n"
                            f"    └─ AFTER:{likes.get('after', 'N/A')}\n"
                            f"┌  DAILY LIMIT\n"
                            f"└─ {limit_info}\n"
                            f"```"
                        )
                    else:
                        embed.description = "```MAX LIKES\nThis UID has already received the maximum likes today.```"

                    embed.set_footer(text="DEVELOPED BY THUG")

                    msg = await ctx.reply(embed=embed, ephemeral=is_slash)

                    if status_code == 2 or data.get("error") == "Failder":
                        await asyncio.sleep(10) # 10 seconds instead of 60 minutes for quicker testing
                        await msg.delete()
                        if ctx.prefix: # Only try to delete prefix command message
                            try:
                                await ctx.message.delete()
                            except discord.Forbidden:
                                print(f"Error: Bot does not have permissions to delete command message in channel {ctx.channel.name}.")
                            except discord.HTTPException as e:
                                print(f"A Discord HTTP error occurred during command message deletion: {e}")

                    elif status_code != 1:
                        await asyncio.sleep(10) # 10 seconds instead of 60 seconds
                        await msg.delete()
                        if ctx.prefix: # Only try to delete prefix command message
                            try:
                                await ctx.message.delete()
                            except discord.Forbidden:
                                print(f"Error: Bot does not have permissions to delete command message in channel {ctx.channel.name}.")
                            except discord.HTTPException as e:
                                print(f"A Discord HTTP error occurred during command message deletion: {e}")

        except Exception as e:
            await self._send_error_embed(ctx, "Critical Error", str(e))
