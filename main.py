import discord
import requests
import os
import ast
import sys
import asyncio
import time
import threading
import traceback
import json
import random
import datetime
from pydactyl import PterodactylClient
from datetime import timedelta
from dotenv import load_dotenv

from discord.ext import commands
from discord import app_commands, Embed, Interaction, ButtonStyle, SelectOption
from discord.ui import View, Button, Select

# simple variables
load_dotenv()
api_key = os.getenv("kb_key")
authorized_user = [int(uid) for uid in os.getenv("authorized_user", "").split(",") if uid.strip().isdigit()]
debug_channel = int(os.getenv("debug_channel"))
server_id = os.getenv("server_id")

kb_api = PterodactylClient('https://control.katabump.com/', api_key=api_key)
bot = commands.Bot(command_prefix='~', intents=discord.Intents.all())
bot.remove_command("help")




#############################################
#-------------------------------------------#
#          Verification System              #
#-------------------------------------------#
#############################################

# ------------------------------
# Data stores
# ------------------------------
active_challenges = {}   # keyed by discord_id
verified_users = {}
recent_sentences = []

# Load sentences (expects sentences.json to contain {"sentences": [...]})
with open("sentences.json", "r") as f:
    SENTENCES = json.load(f)["sentences"]

# ------------------------------
# Helper functions
# ------------------------------
def get_user_about_me(username_or_id: str) -> str:
    """
    Fetch the "About Me" section of a Roblox user by username or user ID.
    took me fking 2 hours to work this out
    """

    username_or_id = str(username_or_id).strip()

    if username_or_id.isdigit():
        user_id = int(username_or_id)
    else:
        user_info_url = "https://users.roblox.com/v1/usernames/users"
        try:
            response = requests.post(user_info_url, json={"usernames": [username_or_id]}, timeout=8)
        except Exception as e:
            return f"Error fetching user ID: {e}"
        if response.status_code != 200:
            return f"Error fetching user ID (status {response.status_code})"
        user_data = response.json()
        if not user_data.get("data") or len(user_data["data"]) == 0:
            return "User not found."
        user_id = user_data["data"][0]["id"]

    about_me_url = f"https://users.roblox.com/v1/users/{user_id}"
    try:
        about_response = requests.get(about_me_url, timeout=8)
    except Exception as e:
        return f"Error fetching about me: {e}"

    if about_response.status_code != 200:
        return f"Error fetching about me (status {about_response.status_code})"
    about_data = about_response.json()
    return about_data.get("description", "No 'About Me' found.")

def save_verified():
    with open("verified.json", "w") as f:
        json.dump(verified_users, f, indent=4)

def pick_sentence() -> str:
    """Pick a random sentence not used in last 3 minutes"""
    global recent_sentences
    while True:
        sentence = random.choice(SENTENCES)
        now = time.time()
        recent_sentences = [s for s in recent_sentences if now - s[1] < 180]
        if all(sentence != s[0] for s in recent_sentences):
            recent_sentences.append((sentence, now))
            return sentence

# ------------------------------
# UI View
# ------------------------------

class VerifyView(discord.ui.View):
    def __init__(self, roblox_username: str, user: discord.User):
        super().__init__(timeout=600)
        self.roblox_username = roblox_username.strip()
        self.user = user

    @discord.ui.button(label="Renew", style=discord.ButtonStyle.secondary)
    async def renew(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("back off, aint yours.", ephemeral=True)

        sentence = pick_sentence()
        active_challenges[self.user.id] = {"sentence": sentence, "roblox_username": self.roblox_username}
        await interaction.response.edit_message(
            content=f"✍️ New challenge:\n```{sentence}```\n\nPut this in your Roblox About Me, then press Verify.",
            view=self
        )

    @discord.ui.button(label="Verify", style=discord.ButtonStyle.success)
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("back off, aint yours", ephemeral=True)

        challenge = active_challenges.get(interaction.user.id)
        if not challenge:
            return await interaction.response.send_message("Hmm i didnt get that, try renewing.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        about_me = await asyncio.to_thread(get_user_about_me, self.roblox_username)

        if about_me and challenge["sentence"] in about_me:
            # use followup because we already deferred
            await interaction.followup.send("✅ Verified!", ephemeral=True)

            verified_users[self.roblox_username] = {
                "time_verified": int(time.time()),
                "discord_id": interaction.user.id,
                "discord_name": str(interaction.user),
                "sentence_used": challenge["sentence"]
            }
            save_verified()
            del active_challenges[interaction.user.id]
        else:
            await interaction.followup.send(
                f"I didnt get that, did you enter it properly?",
                ephemeral=True
            )




class HelpView(View):
    def __init__(self, pages):
        super().__init__(timeout=60)
        self.pages = pages
        self.index = 0
        self.message = None

        self.prev_button = Button(label="Prev", style=ButtonStyle.secondary)
        self.next_button = Button(label="Next", style=ButtonStyle.secondary)

        self.prev_button.callback = self.go_previous
        self.next_button.callback = self.go_next

        self.add_item(self.prev_button)
        self.add_item(self.next_button)

    async def go_previous(self, interaction: Interaction):
        self.index = (self.index - 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.index])

    async def go_next(self, interaction: Interaction):
        self.index = (self.index + 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.index])




# if mention bot
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if bot.user in message.mentions:
        ctx = await bot.get_context(message)
        await ctx.send("leave me alone bro")

    await bot.process_commands(message)
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    role = 1418843923014619197
    if any(role.id == role for role in message.author.roles):
        try:
            # Timeout user for 2 seconds
            await message.author.timeout_for(datetime.timedelta(seconds=2), reason="Auto timeout")
            await message.channel.send(f"A bonehead... silence")
        except Exception as e:
            await debug_log("Could not mute bonehead user...", "warn")

    await bot.process_commands(message)

@bot.command(name="help", description="Show available commands")
async def help(ctx):
    pages = []

    page1 = Embed(title="Moderation Commands", color=discord.Color.blurple())
    page1.add_field(name="~help", value="Show this help message.", inline=False)
    page1.add_field(name="~ban [reason]", value="Ban a user.", inline=False)
    page1.add_field(name="~kick [reason]", value="Kick a user.", inline=False)
    page1.add_field(name="~timeout <duration>", value="Timeout a user.", inline=False)
    page1.add_field(name="~untimeout", value="Untimeout a user", inline=False)
    page1.add_field(name="~unban", value="Unban a user. reply, mention, or use userID", inline=False)

    page2 = Embed(title="Utility Commands", color=discord.Color.green())
    page2.add_field(name="~purge <amount>", value="Clear messages. Default 10, max 100.", inline=False)
    page2.add_field(name="~gw_create <title> <winner_count> <time_end>", value="Start a giveaway.\nEx: ~gw 'Prize' 1 10m", inline=False)
    page2.add_field(name="~gw_reroll <gw_id>", value="Reroll a giveaway by ID.", inline=False)
    page2.add_field(name="~gw_end <gw_id>", value="End a giveaway early by ID.", inline=False)
    page2.add_field(name="~gw_reset", value="Reset all giveaway data.", inline=False)

    page3 = Embed(title="Role Commands", color=discord.Color.purple())
    page3.add_field(name="~add_role <user:optional> <role>", value="Add a role. Reply or mention", inline=False)
    page3.add_field(name="~remove_role <user:optional> <role>", value="Remove a role. Reply or mention", inline=False)
    page3.add_field(name="~role_info", value="Get info on a role.", inline=False)
    page3.add_field(name="~list_roles", value="List all roles in the server", inline=False)
    page3.add_field(name="~create_role <role_name>", value="Create a new role with the given name", inline=False)

    
    page1.set_footer(text="Page 1/3")
    page2.set_footer(text="Page 2/3")
    page3.set_footer(text="Page 3/3")
    pages.extend([page1, page2, page3])
    view = HelpView(pages)

    await ctx.send(embed=pages[0], view=view)



################################################
#----------------------------------------------#
#             dependency commands              #
#----------------------------------------------#
#################################################


# Role creation view for creating roles
with open("colors.json", "r") as f:
    COLOR_MAP = json.load(f)

class RoleCreateView(View):
    def __init__(self, role_name, message=None):
        super().__init__(timeout=180)
        self.role_name = role_name
        self.selected_perms = set()
        self.selected_color = discord.Color.default()
        self.page_perm = 0
        self.page_color = 0
        self.perms_per_page = 25
        self.colors_per_page = 25
        self.perm_items = list(dict(discord.Permissions.all()).keys())
        self.color_items = list(COLOR_MAP.keys())
        self.message = message

        self.update_view()

    def update_view(self):
        self.clear_items()

        # Permissions Page
        start = self.page_perm * self.perms_per_page
        end = start + self.perms_per_page
        perm_options = [
            discord.SelectOption(label=p.replace("_", " ").title(), value=p)
            for p in self.perm_items[start:end]
        ]
        perm_select = Select(
            placeholder=f"Select permissions ({start+1}-{min(end,len(self.perm_items))})",
            options=perm_options,
            min_values=0,
            max_values=len(perm_options)
        )

        async def perm_callback(interaction: discord.Interaction):
            self.selected_perms.update(perm_select.values)
            await interaction.response.defer()

        perm_select.callback = perm_callback
        self.add_item(perm_select)

        if self.page_perm > 0:
            prev_perm_btn = Button(label="Prev Perms", style=discord.ButtonStyle.primary)
            prev_perm_btn.callback = self.prev_perm_page
            self.add_item(prev_perm_btn)
        if end < len(self.perm_items):
            next_perm_btn = Button(label="Next Perms", style=discord.ButtonStyle.primary)
            next_perm_btn.callback = self.next_perm_page
            self.add_item(next_perm_btn)

        # Color page
        start_c = self.page_color * self.colors_per_page
        end_c = start_c + self.colors_per_page
        color_options = [
            discord.SelectOption(label=c, value=c)
            for c in self.color_items[start_c:end_c]
        ]
        color_select = Select(
            placeholder=f"Select role color ({start_c+1}-{min(end_c,len(self.color_items))})",
            options=color_options
        )

        async def color_callback(interaction: discord.Interaction):
            hex_val = COLOR_MAP[color_select.values[0]]
            self.selected_color = discord.Color(int(hex_val, 16))
            await interaction.response.defer()

        color_select.callback = color_callback
        self.add_item(color_select)

        if self.page_color > 0:
            prev_color_btn = Button(label="Prev Colors", style=discord.ButtonStyle.secondary)
            prev_color_btn.callback = self.prev_color_page
            self.add_item(prev_color_btn)
        if end_c < len(self.color_items):
            next_color_btn = Button(label="Next Colors", style=discord.ButtonStyle.secondary)
            next_color_btn.callback = self.next_color_page
            self.add_item(next_color_btn)

        # Confirm button
        confirm_btn = Button(label="Create Role", style=discord.ButtonStyle.success)
        confirm_btn.callback = self.confirm
        self.add_item(confirm_btn)

    async def prev_perm_page(self, interaction: discord.Interaction):
        self.page_perm -= 1
        self.update_view()
        await interaction.response.edit_message(view=self)

    async def next_perm_page(self, interaction: discord.Interaction):
        self.page_perm += 1
        self.update_view()
        await interaction.response.edit_message(view=self)

    async def prev_color_page(self, interaction: discord.Interaction):
        self.page_color -= 1
        self.update_view()
        await interaction.response.edit_message(view=self)

    async def next_color_page(self, interaction: discord.Interaction):
        self.page_color += 1
        self.update_view()
        await interaction.response.edit_message(view=self)

    async def confirm(self, interaction: discord.Interaction):
        perms = discord.Permissions.none()
        for p in self.selected_perms:
            setattr(perms, p, True)
        role = await interaction.guild.create_role(
            name=self.role_name,
            permissions=perms,
            color=self.selected_color
        )
        await interaction.response.edit_message(
            content=f"✅ Created role `{role.name}` with {len(self.selected_perms)} perms and color `{self.selected_color}`",
            view=None
        )
        self.stop()


# Role selection view for role info
class RoleSelectView(View):
    def __init__(self, roles):
        super().__init__(timeout=60)
        self.roles, self.page, self.page_size = roles, 0, 25
        self.update_view()

    def update_view(self):
        self.clear_items()
        start, end = self.page * self.page_size, (self.page + 1) * self.page_size
        opts = [
            discord.SelectOption(label=r.name, value=str(r.id))
            for r in self.roles[start:end] if not r.is_default()
        ]


        select = Select(
            placeholder=f"Role to view: ({start+1}-{min(end, len(self.roles))})",
            options=opts
        )
        select.callback = self.select_callback
        self.add_item(select)

        if self.page > 0:
            prev_btn = Button(label="Previous", style=discord.ButtonStyle.primary)
            prev_btn.callback = self.prev_page
            self.add_item(prev_btn)
        if end < len(self.roles):
            next_btn = Button(label="Next", style=discord.ButtonStyle.primary)
            next_btn.callback = self.next_page
            self.add_item(next_btn)

    async def select_callback(self, interaction: discord.Interaction):
        rid = int(interaction.data["values"][0])
        role = discord.utils.get(self.roles, id=rid)
        if not role:
            return await interaction.response.edit_message(content="Role not found.", view=self)

        perms = ", ".join(p[0] for p in role.permissions if p[1]) or "None"
        embed = discord.Embed(
            title=f"Role Info: {role.name}",
            color=role.color,
            description=(
                f"**ID:** {role.id}\n"
                f"**Position:** {role.position}\n"
                f"**Mentionable:** {role.mentionable}\n"
                f"**Hoisted:** {role.hoist}\n"
                f"**Color:** {role.color}\n"
                f"**Permissions:** {perms}"
            )
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        self.update_view()
        await interaction.response.edit_message(view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        self.update_view()
        await interaction.response.edit_message(view=self)

    async def on_timeout(self):
        self.stop()


# Simpler ctx send embed
async def send_embed(ctx, title, description, color=discord.Color.blue(), delete_after=None):
    embed = discord.Embed(title=title, description=description, color=color)
    await ctx.send(embed=embed, delete_after=delete_after)

# Giveaway command dependency
GW_TRACK_FILE = "giveaway_ids.json"
GW_FOLDER = "giveaways"
if not os.path.exists(GW_FOLDER):
    os.makedirs(GW_FOLDER)

def get_next_gw_id():
    if not os.path.exists(GW_TRACK_FILE):
        with open(GW_TRACK_FILE, "w") as f:
            json.dump([], f)
    with open(GW_TRACK_FILE, "r") as f:
        ids = json.load(f)
    next_id = (max(ids) + 1) if ids else 1
    ids.append(next_id)
    with open(GW_TRACK_FILE, "w") as f:
        json.dump(ids, f)
    return next_id




# Debug Functions
async def debug_log(message, level="info"):
    colors = {
        "info": discord.Color.blue(),
        "success": discord.Color.green(),
        "warn": discord.Color.yellow(),
        "error": discord.Color.red()
    }

    embed = discord.Embed(
        title=f"📋 Debug - {level.capitalize()}",
        description=f"```{message}```",
        color=colors.get(level, discord.Color.blue())
    )

    if debug_channel == 0:
        embed = discord.Embed(
            title="Debug Channel Not Set",
            description="Debug channel is not set. Please configure the debug_channel environment variable.",
            color=discord.Color.red()
        )
        print("[ERROR] Debug channel not set.")
        return

    channel = bot.get_channel(debug_channel) if isinstance(debug_channel, int) else debug_channel
    if channel:
        await channel.send(embed=embed)

    print(f"[{level.upper()}] {message}")


def global_exception_hook(exc_type, exc_value, exc_traceback):
    error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    asyncio.create_task(debug_log(f"Global Error:\n{error_msg}", level="error"))
    print(error_msg)

sys.excepthook = global_exception_hook

@bot.event
async def on_error(event, *args, **kwargs):
    error_msg = traceback.format_exc()
    await debug_log(f"Unhandled Discord Event Error in `{event}`:\n{error_msg}", level="error")

@bot.event
async def on_command_error(ctx, error):
    await debug_log(f"Command Error in `{ctx.command}` by {ctx.author}: {error}", level="error")

loop = asyncio.get_event_loop()

def handle_asyncio_error(loop, context):
    error = context.get("", context["message"])
    asyncio.create_task(debug_log(f"Asyncio Error:\n{error}", level="error"))

loop.set_exception_handler(handle_asyncio_error)




# Moderation Level Dependencies
def parse_time(time_str):
    units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
    try: return int(time_str[:-1]) * units.get(time_str[-1], 0)
    except: return None

def format_reason(msg):
    if not msg: return 'No reason provided.'
    files = ', '.join(a.filename for a in msg.attachments)
    return f"{msg.content}\nAttachments: {files}" if msg.attachments else msg.content

async def notify_user(user, title, desc, color):
    try:
        embed = discord.Embed(title=title, description=desc, color=color)
        await user.send(embed=embed)
    except: await debug_log(f"Failed to DM {user}.", level="warn")

async def resolve_member(ctx):
    # If replying to a message, get the author of the replied message
    if ctx.message.reference and ctx.message.reference.message_id:
        try:
            msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            if msg and msg.author:
                return ctx.guild.get_member(msg.author.id), msg
        except Exception:
            pass
    # If mentioning a user, get the first mentioned user
    if ctx.message.mentions:
        return ctx.message.mentions[0], None
    return None, None


###############################################
#---------------------------------------------#
#          Moderation Level Commands          #
#---------------------------------------------#
###############################################

@bot.command(name='backup')
async def backup(ctx):
    if ctx.author.id not in authorized_user:
        await ctx.send("Developer level only! ask <@844921681449058326>")
        return

    guild = ctx.guild
    backup_data = {
        "guild_id": guild.id,
        "guild_name": guild.name,
        "roles": [],
        "categories": [],
        "channels": []
    }

    for role in guild.roles:
        backup_data['roles'].append({
            "id": role.id,
            "name": role.name,
            "permissions": role.permissions.value,
            "color": role.color.value,
            "hoist": role.hoist,
            "mentionable": role.mentionable,
            "position": role.position,
            "managed": role.managed
        })

    for category in guild.categories:
        backup_data['categories'].append({
            "id": category.id,
            "name": category.name,
            "position": category.position
        })

    for channel in guild.channels:
        parent_id = channel.category.id if channel.category else None
        channel_data = {
            "id": channel.id,
            "name": channel.name,
            "type": str(channel.type),
            "position": channel.position,
            "parent_id": parent_id
        }


        if isinstance(channel, discord.TextChannel):
            channel_data.update({
                "topic": channel.topic,
                "nsfw": channel.nsfw,
                "slowmode_delay": channel.slowmode_delay
            })
        elif isinstance(channel, discord.VoiceChannel):
            channel_data.update({
                "bitrate": channel.bitrate,
                "user_limit": channel.user_limit
            })

        backup_data['channels'].append(channel_data)

    filename = f'backup_{guild.id}.json'
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(backup_data, f, indent=4)

    await ctx.send(f"Backup complete. Saved as `{filename}`.")

@bot.command(name='restore')
async def restore(ctx, backup_filename: str):
    if ctx.author.id not in authorized_user:
        await ctx.send("Developer level only! ask <@844921681449058326>")
        return

    guild = ctx.guild

    try:
        with open(backup_filename, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)
    except FileNotFoundError:
        await ctx.send("Backup file not found.")
        return

    await ctx.send(f"Restoring server structure from `{backup_filename}`...")

    # Restore roles
    created_roles = {}
    for role_data in sorted(backup_data['roles'], key=lambda r: r['position']):
        existing_role = discord.utils.get(guild.roles, id=role_data['id']) \
            or discord.utils.get(guild.roles, name=role_data['name'])

        if existing_role:
            print(f"Role '{role_data['name']}' already exists (ID: {existing_role.id}). Skipping.")
            created_roles[role_data['id']] = existing_role
            continue

        role = await guild.create_role(
            name=role_data['name'],
            permissions=discord.Permissions(role_data['permissions']),
            color=discord.Color(role_data['color']),
            hoist=role_data['hoist'],
            mentionable=role_data['mentionable']
        )
        created_roles[role_data['id']] = role

    # Restore categories
    created_categories = {}
    for category_data in sorted(backup_data['categories'], key=lambda c: c['position']):
        existing_category = discord.utils.get(guild.categories, id=category_data['id']) \
            or discord.utils.get(guild.categories, name=category_data['name'])

        if existing_category:
            print(f"Category '{category_data['name']}' already exists (ID: {existing_category.id}). Skipping.")
            created_categories[category_data['id']] = existing_category
            continue

        category = await guild.create_category(
            name=category_data['name'],
            position=category_data['position']
        )
        created_categories[category_data['id']] = category

    # Restore channels
    for channel_data in sorted(backup_data['channels'], key=lambda ch: ch['position']):
        parent = None
        parent_id = channel_data.get('parent_id')
        if parent_id:
            parent = created_categories.get(parent_id) or discord.utils.get(guild.categories, id=parent_id)

        existing_channel = discord.utils.get(guild.channels, id=channel_data['id']) \
            or discord.utils.get(guild.channels, name=channel_data['name'])

        if existing_channel:
            print(f"Channel '{channel_data['name']}' already exists (ID: {existing_channel.id}). Skipping.")
            continue

        if channel_data['type'] == 'text':
            await guild.create_text_channel(
                name=channel_data['name'],
                position=channel_data['position'],
                topic=channel_data.get('topic'),
                nsfw=channel_data.get('nsfw', False),
                slowmode_delay=channel_data.get('slowmode_delay', 0),
                category=parent
            )
        elif channel_data['type'] == 'voice':
            await guild.create_voice_channel(
                name=channel_data['name'],
                position=channel_data['position'],
                bitrate=channel_data.get('bitrate', 64000),
                user_limit=channel_data.get('user_limit', 0),
                category=parent
            )

    await ctx.send("Server restore complete (skipped existing items).")





@bot.command()
async def ban(ctx, *, args: str = None):
    if not ctx.author.guild_permissions.ban_members:
        await ctx.send("womp womp")
        return
    target = None
    reason = None
    reply = None

    if ctx.message.reference and ctx.message.reference.message_id:
        try:
            msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            if msg and msg.author:
                target = ctx.guild.get_member(msg.author.id)
                reply = msg
        except Exception:
            pass

    # If not replying, check for mentions and reason in args
    if not target:
        if ctx.message.mentions:
            target = ctx.message.mentions[0]
            # Remove all mention strings from args to get reason
            reason_args = args
            for user in ctx.message.mentions:
                mention_str = f"<@{user.id}>"
                reason_args = reason_args.replace(mention_str, "")
                mention_str_nick = f"<@!{user.id}>"
                reason_args = reason_args.replace(mention_str_nick, "")
            reason = reason_args.strip() if reason_args else None
        elif args:
            reason = args.strip()
    else:
        # If reply, reason is everything in args
        if args:
            reason = args.strip()

    reason_text = reason or format_reason(reply)
    if not target:
        embed = discord.Embed(
            title="Ban Failed",
            description="Reply to a message or mention a user to ban.",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
        await debug_log("Reply to a message or mention a user to ban.", level="info")
        return

    try:
        await ctx.guild.ban(target, reason=reason_text)
        await notify_user(target, "You have been banned", f"Reason: {reason_text}", discord.Color.red())
        embed = discord.Embed(
            title="Ban Success",
            description=f"Banned {target}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        await debug_log(f"Banned {target}", level="success")
    except discord.Forbidden:
        embed = discord.Embed(
            title="Ban Failed",
            description="Missing permission or target has higher permissions.",
            color=discord.Color.yellow()
        )
        await ctx.send(embed=embed)
    except Exception as e:
        embed = discord.Embed(
            title="Ban Error",
            description=f"Failed to ban {target}: {e}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        await debug_log(f"Failed to ban {target}: {e}", level="error")

@bot.command()
async def kick(ctx, *, args: str = None):
    if not ctx.author.guild_permissions.kick_members:
        await ctx.send("cry about it")
        return
    target = None
    reason = None
    reply = None

    if ctx.message.reference and ctx.message.reference.message_id:
        try:
            msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            if msg and msg.author:
                target = ctx.guild.get_member(msg.author.id)
                reply = msg
        except Exception:
            pass

    # If not replying, check for mentions and reason in args
    if not target:
        if ctx.message.mentions:
            target = ctx.message.mentions[0]
            reason_args = args
            for user in ctx.message.mentions:
                mention_str = f"<@{user.id}>"
                reason_args = reason_args.replace(mention_str, "")
                mention_str_nick = f"<@!{user.id}>"
                reason_args = reason_args.replace(mention_str_nick, "")
            reason = reason_args.strip() if reason_args else None
        elif args:
            reason = args.strip()
    else:
        if args:
            reason = args.strip()

    reason_text = reason or format_reason(reply)
    if not target:
        embed = discord.Embed(
            title="Kick Failed",
            description="Reply to a message or mention a user to kick.",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
        await debug_log("Reply to a message or mention a user to kick.", level="info")
        return

    try:
        await ctx.guild.kick(target, reason=reason_text)
        await notify_user(target, "You have been kicked", f"Reason: {reason_text}", discord.Color.orange())
        embed = discord.Embed(
            title="Kick Success",
            description=f"Kicked {target}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        await debug_log(f"Kicked {target}", level="success")
    except discord.Forbidden:
        embed = discord.Embed(
            title="Kick Failed",
            description="Missing permission or target has higher permissions.",
            color=discord.Color.yellow()
        )
        await ctx.send(embed=embed)
    except Exception as e:
        embed = discord.Embed(
            title="Kick Error",
            description=f"Failed to kick {target}: {e}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        await debug_log(f"Failed to kick {target}: {e}", level="error")

@bot.command()
async def timeout(ctx, *, args: str = None):
    if not ctx.author.guild_permissions.moderate_members:
        await ctx.send("no thanks")
        return
    target = None
    time = None
    reply = None

    if ctx.message.reference and ctx.message.reference.message_id:
        try:
            msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            if msg and msg.author:
                target = ctx.guild.get_member(msg.author.id)
                reply = msg
        except Exception:
            pass

    # If not replying, check for mentions and time in args
    if not target:
        if ctx.message.mentions:
            target = ctx.message.mentions[0]
            time_args = args
            for user in ctx.message.mentions:
                mention_str = f"<@{user.id}>"
                time_args = time_args.replace(mention_str, "")
                mention_str_nick = f"<@!{user.id}>"
                time_args = time_args.replace(mention_str_nick, "")
            time = time_args.strip().split()[0] if time_args else None
        elif args:
            time = args.strip().split()[0]
    else:
        if args:
            time = args.strip().split()[0]

    if not target or not time:
        embed = discord.Embed(
            title="Timeout Failed",
            description="Usage: reply to a user or mention with `!timeout <duration>`. Example: 5s, 10m",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
        await debug_log("Usage: reply to a user or mention with `!timeout <duration>`. Example: 5s, 10m", level="info")
        return

    seconds = parse_time(time)
    if not seconds:
        embed = discord.Embed(
            title="Timeout Failed",
            description="Invalid time format. Use s, m, h, d (e.g., 5s, 10m, 2h, 1d)",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
        await debug_log("Invalid time format. Use s, m, h, d (e.g., 5s, 10m, 2h, 1d)", level="info")
        return

    until = discord.utils.utcnow() + timedelta(seconds=seconds)
    reason_text = format_reason(reply)

    try:
        await target.timeout(until, reason=reason_text)
        await notify_user(target, "You have been timed out", f"Duration: {time}\nReason: {reason_text}", discord.Color.yellow())
        embed = discord.Embed(
            title="Timeout Success",
            description=f"Timed out {target} for {time}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        await debug_log(f"Timed out {target} for {time}", level="success")
    except discord.Forbidden:
        embed = discord.Embed(
            title="Timeout Failed",
            description="Missing permission or target has higher permissions.",
            color=discord.Color.yellow()
        )
        await ctx.send(embed=embed)
    except Exception as e:
        embed = discord.Embed(
            title="Timeout Error",
            description=f"Failed to timeout {target}: {e}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        await debug_log(f"Failed to timeout {target}: {e}", level="error")

@bot.command()
async def untimeout(ctx, *, args: str = None):
    if not ctx.author.guild_permissions.moderate_members:
        await ctx.send("i think not")
        return
    target = None
    reason = None
    reply = None

    if ctx.message.reference and ctx.message.reference.message_id:
        try:
            msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            if msg and msg.author:
                target = ctx.guild.get_member(msg.author.id)
                reply = msg
        except Exception:
            pass

    # If not replying, check for mentions and reason in args
    if not target:
        if ctx.message.mentions:
            target = ctx.message.mentions[0]
            reason_args = args
            for user in ctx.message.mentions:
                mention_str = f"<@{user.id}>"
                reason_args = reason_args.replace(mention_str, "")
                mention_str_nick = f"<@!{user.id}>"
                reason_args = reason_args.replace(mention_str_nick, "")
            reason = reason_args.strip() if reason_args else None
        elif args:
            reason = args.strip()
    else:
        if args:
            reason = args.strip()

    reason_text = reason or format_reason(reply)
    if not target:
        embed = discord.Embed(
            title="Untimeout Failed",
            description="Reply to a message or mention a user to untimeout.",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
        await debug_log("Reply to a message or mention a user to untimeout.", level="info")
        return

    try:
        await target.timeout(None, reason=reason_text)
        embed = discord.Embed(
            title="Untimeout Success",
            description=f"Untimed out {target}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        await debug_log(f"Untimed out {target}", level="success")
    except discord.Forbidden:
        embed = discord.Embed(
            title="Untimeout Failed",
            description="Missing permission or target has higher permissions.",
            color=discord.Color.yellow()
        )
        await ctx.send(embed=embed)
    except Exception as e:
        embed = discord.Embed(
            title="Untimeout Error",
            description=f"Failed to untimeout {target}: {e}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        await debug_log(f"Failed to untimeout {target}: {e}", level="error")



@bot.command()
async def unban(ctx, *, args: str = None):
    if not ctx.author.guild_permissions.ban_members:
        await ctx.send("Back off lil kid")
        return
    
    target = None
    reply = None
    user_id = None
    reason = None

    # if replying
    if ctx.message.reference and ctx.message.reference.message_id:
        try:
            msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            if msg and msg.author:
                user_id = msg.author.id
                reply = msg
        except Exception:
            pass

    
    #check user ID and mention
    if not user_id:
        if ctx.message.mentions:
            user_id = ctx.message.mentions[0].id
        elif args:
            parts = args.strip().split()
            # Try to find a user ID in the arguments
            for part in parts:
                if part.isdigit():
                    user_id = int(part)
                    break
            # Reason is everything after user ID
            reason = " ".join([p for p in parts if not p.isdigit()]).strip()
    else:
        if args:
            reason = args.strip()

    reason_text = reason or format_reason(reply)
    if not user_id:
        embed = discord.Embed(
            title="Unban Failed",
            description="Reply to a message, mention a user, or provide a user ID to unban.",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
        await debug_log("Reply, mention, or user ID required for unban.", level="info")
        return

    try:
        bans = await ctx.guild.bans()
        user = discord.utils.find(lambda ban: ban.user.id == user_id, bans)
        if not user:
            embed = discord.Embed(
                title="Unban Failed",
                description=f"User with ID `{user_id}` is not banned.",
                color=discord.Color.yellow()
            )
            await ctx.send(embed=embed)
            return

        await ctx.guild.unban(user.user, reason=reason_text)
        embed = discord.Embed(
            title="Unban Success",
            description=f"Unbanned {user.user} ({user.user.id})",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        await debug_log(f"Unbanned {user.user} ({user.user.id})", level="success")
    except discord.Forbidden:
        embed = discord.Embed(
            title="Unban Failed",
            description="Missing permission to unban.",
            color=discord.Color.yellow()
        )
        await ctx.send(embed=embed)
    except Exception as e:
        embed = discord.Embed(
            title="Unban Error",
            description=f"Failed to unban user: {e}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        await debug_log(f"Failed to unban user: {e}", level="error")

@bot.command()
async def purge(ctx, amount: int = 10):
    if not ctx.author.guild_permissions.manage_messages:
        await ctx.send("your not a mod")
        return

    if amount < 1 or amount > 100:
        await ctx.send("ok.. how many? 1-100")
        return

    try:
        deleted = await ctx.channel.purge(limit=amount)
        embed = discord.Embed(
            title="Purge Success",
            description=f"Deleted {len(deleted)} messages.",
            color=discord.Color.green()
            )
        await ctx.send(embed=embed, delete_after=5)
        await debug_log(f"Purged {len(deleted)} messages in {ctx.channel}", level="success")
    except discord.Forbidden:
        await ctx.send("Missing permission to delete messages.")
    except Exception as e:
        await ctx.send(f"Error purging messages: {e}")
        await debug_log(f"Error purging messages: {e}", level="error")



#########################################
#---------------------------------------#
#         Utility Level Commands        #
#---------------------------------------#
#########################################

#########################
#  Verification System  #
#########################
@bot.command()
async def verify(ctx, roblox_username: str):
    """Start Roblox verification (username or numeric id allowed)"""
    roblox_username = roblox_username.strip()

    sentence = pick_sentence()
    active_challenges[ctx.author.id] = {"sentence": sentence, "roblox_username": roblox_username}
    view = VerifyView(roblox_username, ctx.author)

    await ctx.send(
        f"👤 Verification for Roblox `{roblox_username}`\n\n"
        f"✍️ Challenge:\n```{sentence}```\n\n"
        "Put this in your Roblox About Me, then click Verify below.",
        view=view
    )


######################
# Giveaway Utilities #
######################

@bot.command(name='gw_reset')
async def gw_reset(ctx):
    if not ctx.author.guild_permissions.manage_events:
        await ctx.send("no no no nigga")
        return

    if os.path.exists(GW_TRACK_FILE):
        os.remove(GW_TRACK_FILE)
    for filename in os.listdir(GW_FOLDER):
        if filename.startswith("giveaway") and filename.endswith(".json"):
            os.remove(os.path.join(GW_FOLDER, filename))
    await send_embed(ctx, "Giveaway Reset", "All giveaway data has been reset.", discord.Color.green())
    user = ctx.author
    await debug_log(f"Giveaway data reset by {user.mention}", level="info")



@bot.command(name='gw_create')
async def giveaway(ctx, title: str, winner_count: int, time_end: str):
    if not ctx.author.guild_permissions.manage_events:
        await ctx.send("You need the Manage Events permission to start a giveaway.")
        return

    units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
    try:
        seconds = int(time_end[:-1]) * units.get(time_end[-1], 0)
    except:
        return await ctx.send("Invalid time format. Use s, m, h, d (e.g., 10m, 1h)")
    if seconds <= 0:
        return await ctx.send("Time must be greater than 0.")

    gw_id = get_next_gw_id()
    json_file = os.path.join(GW_FOLDER, f"giveaway{gw_id}.json")
    end_timestamp = int((discord.utils.utcnow() + timedelta(seconds=seconds)).timestamp())
    embed = discord.Embed(
        title=f"🎉 Giveaway: {title}",
        description=f"GW ID: {gw_id}\nReact with 🎉 to enter!\nWinners: {winner_count}\nEnds: <t:{end_timestamp}:R>",
        color=discord.Color.gold()
    )
    msg = await ctx.send(embed=embed)
    await msg.add_reaction("🎉")

    with open(json_file, "w") as f:
        json.dump({"participants": [], "message_id": msg.id, "channel_id": ctx.channel.id, "gw_id": gw_id, "winner_count": winner_count, "title": title, "end_time": end_timestamp}, f)

    def end_giveaway():
        time.sleep(seconds)
        # Fetch message and reactions
        coro = ctx.channel.fetch_message(msg.id)
        fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
        try:
            message = fut.result(timeout=10)
            reaction = discord.utils.get(message.reactions, emoji="🎉")
            users = []
            if reaction:
                async def get_users():
                    return [user.id async for user in reaction.users() if not user.bot]
                users_fut = asyncio.run_coroutine_threadsafe(get_users(), bot.loop)
                users = users_fut.result(timeout=10)
            # Save participants
            with open(json_file, "w") as f:
                json.dump({"participants": users, "message_id": msg.id, "channel_id": ctx.channel.id, "gw_id": gw_id, "winner_count": winner_count, "title": title}, f)
            # Pick winners
            if len(users) < winner_count:
                winners = users
            else:
                winners = random.sample(users, winner_count)
            winner_mentions = [f"<@{uid}>" for uid in winners]
            result_embed = discord.Embed(
                title=f"🎉 Giveaway Ended: {title}",
                description=f"GW ID: {gw_id}\nWinners: {', '.join(winner_mentions) if winners else 'No participants!'}\nEnded: <t:{int(discord.utils.utcnow().timestamp())}:R>",
                color=discord.Color.green()
            )
            asyncio.run_coroutine_threadsafe(ctx.send(embed=result_embed), bot.loop)
            asyncio.run_coroutine_threadsafe(msg.delete(), bot.loop)
        except Exception as e:
            asyncio.run_coroutine_threadsafe(ctx.send(f"Giveaway error: {e}"), bot.loop)

    threading.Thread(target=end_giveaway, daemon=True).start()

@bot.command(name="gw_reroll")
async def gw_reroll(ctx, gw_id: int):
    if not ctx.author.guild_permissions.manage_events:
        await ctx.send("You need the Manage Events permission to reroll a giveaway.")
        return

    json_file = os.path.join(GW_FOLDER, f"giveaway{gw_id}.json")
    if not os.path.exists(json_file):
        return await ctx.send(f"Giveaway with ID {gw_id} does not exist.")

    with open(json_file, "r") as f:
        data = json.load(f)

    if not data["participants"]:
        return await ctx.send("No participants in this giveaway.")

    winner_count = data["winner_count"]
    if len(data["participants"]) < winner_count:
        winners = data["participants"]
    else:
        winners = random.sample(data["participants"], winner_count)

    winner_mentions = [f"<@{uid}>" for uid in winners]
    result_embed = discord.Embed(title=f"🎉 Giveaway Rerolled: {data['title']}", description=f"GW ID: {gw_id}\nNew Winners: {', '.join(winner_mentions) if winners else 'No participants!'}", color=discord.Color.green())
    await ctx.send(embed=result_embed)


#############################
# Role Management Utilities #
#############################

@bot.command(name="add_role")
async def add_role(ctx, *, args=None):
    if not ctx.author.guild_permissions.manage_roles:
        await ctx.send("i think not")
        return

    target = None
    role_to_add = None
    reply = None

    # If replying to a message, extract target
    if ctx.message.reference and ctx.message.reference.message_id:
        try:
            msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            if msg and msg.author:
                target = ctx.guild.get_member(msg.author.id)
                reply = msg
        except Exception:
            pass

    # If not reply, check for mentioned user
    if not target and ctx.message.mentions:
        for user in ctx.message.mentions:
            if isinstance(user, discord.Member):
                target = user
                break  # First member mention only

    if not target:
        await ctx.send("Mention or reply to a member to give role.")
        return

    # Get role from role mentions
    if ctx.message.role_mentions:
        role_to_add = ctx.message.role_mentions[0]
    else:
        await ctx.send("Mention a role to add.")
        return

    # Prevent managing roles above bot's or user's top role
    if role_to_add >= ctx.guild.me.top_role:
        await ctx.send("I can't give a role higher than or equal to my top role.")
        return
    if ctx.author.top_role <= role_to_add and ctx.author != ctx.guild.owner:
        await ctx.send("You can't give a role higher than or equal to your top role.")
        return

    try:
        await target.add_roles(role_to_add, reason=f"Added by {ctx.author}")
        await ctx.send(f"{role_to_add.mention} given to {target.mention}")
    except Exception as e:
        await ctx.send(f"Failed to add role: `{e}`")



@bot.command(name="remove_role")
async def remove_role(ctx, *, args=None):
    if not ctx.author.guild_permissions.manage_roles:
        await ctx.send("nope")
        return

    target = None
    role_to_remove = None
    reply = None

    # If replying to a message
    if ctx.message.reference and ctx.message.reference.message_id:
        try:
            msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            if msg and msg.author:
                target = ctx.guild.get_member(msg.author.id)
                reply = msg
        except Exception:
            pass

    # If not reply, check for mentioned user
    if not target and ctx.message.mentions:
        for user in ctx.message.mentions:
            if isinstance(user, discord.Member):
                target = user
                break
    
    if not target:
        await ctx.send("Mention or reply to a member to remove role.")
        return

    if ctx.message.role_mentions:
        role_to_remove = ctx.message.role_mentions[0]
    else:
        await ctx.send("Mention a role to remove.")
        return

    if role_to_remove >= ctx.guild.me.top_role:
        await ctx.send("I can't remove a role higher than or equal to my top role.")
        return
    if ctx.author.top_role <= role_to_remove and ctx.author != ctx.guild.owner:
        await ctx.send("You can't remove a role higher than or equal to your top role.")
        return
    try:
        await target.remove_roles(role_to_remove, reason=f"Removed by {ctx.author}")
        await ctx.send(f"{role_to_remove.mention} removed from {target.mention}")
    except Exception as e:
        await ctx.send(f"Failed to remove role: `{e}`")


@bot.command(name="list_roles")
async def list_roles(ctx):
    if not ctx.author.guild_permissions.manage_roles:
        await ctx.send("no")
        return

    roles = sorted(ctx.guild.roles, key=lambda r: r.position, reverse=True)
    role_lines = [f"{role.name} (ID: {role.id})" for role in roles if role != ctx.guild.default_role]

    if not role_lines:
        await ctx.send("No roles found.")
        return

    chunk_size = 20
    for i in range(0, len(role_lines), chunk_size):
        chunk = role_lines[i:i + chunk_size]
        embed = discord.Embed(title="Server Roles", description="\n".join(chunk), color=discord.Color.blue())
        await ctx.send(embed=embed)



@bot.command()
async def role_info(ctx):
    if not ctx.author.guild_permissions.manage_roles:
        return await ctx.send("no")
    roles = sorted(ctx.guild.roles, key=lambda r: r.position, reverse=True)
    if len(roles) <= 1:
        return await ctx.send("No roles found.")
    await ctx.send("Select a role to view info:", view=RoleSelectView(roles))


@bot.command()
async def create_role(ctx, *, role_name: str):
    if not ctx.author.guild_permissions.manage_roles:
        return await ctx.send("no")
    """Create a role with dropdowns for perms and color"""
    view = RoleCreateView(role_name)
    msg = await ctx.send(f"⚙️ Configuring new role: **{role_name}**", view=view)
    view.message = msg

###################################
#---------------------------------#
#    Developer Level Commands     #
#---------------------------------#
###################################

@bot.event
async def on_ready():
    if os.path.exists("restart.json"):
        with open("restart.json", "r") as f:
            data = json.load(f)
        channel = bot.get_channel(data["channel_id"])
        if channel:
            try:
                msg = await channel.fetch_message(data["message_id"])
                embed = discord.Embed(
                    title="Power Option: Restarted",
                    description="Bot has successfully restarted.",
                    color=discord.Color.green()
                )
                await msg.edit(embed=embed)
            except Exception as e:
                print(f"Failed to edit restart message: {e}")

        os.remove("restart.json")
    
    print(f"Logged in as {bot.user}")



@bot.command()
async def check_var(ctx, var: str = None):
    if ctx.author.id not in authorized_user:
        return await ctx.send("unauthorized")
    if var == "all":
        items = list(globals().items())
        chunks = [items[i:i+25] for i in range(0, len(items), 25)]
        for chunk in chunks:
            embed = discord.Embed(title="📦 Global Variables", color=discord.Color.blue())
            for name, val in chunk:
                embed.add_field(name=name, value=f"```{repr(val)}```", inline=False)
            await ctx.send(embed=embed)
    elif var:
        embed = discord.Embed(title="📦 Global Variables", color=discord.Color.blue())
        value = globals().get(var, None)
        if value is not None:
            embed.add_field(name=var, value=f"```{repr(value)}```", inline=False)
        else:
            return await ctx.send(f"Variable `{var}` not found.")
        await ctx.send(embed=embed)
    else:
        return await ctx.send("Please specify a variable name or `all`.")




@bot.command()
async def set_var(ctx, var: str, *, value: str):
    if ctx.author.id not in authorized_user:
        return await ctx.send("unauthorized")
    try:
        if var == "authorized_user":
            evaluated_value = [int(uid.strip()) for uid in value.split(",") if uid.strip().isdigit()]
        else:
            try:
                evaluated_value = ast.literal_eval(value)
            except:
                evaluated_value = value

        globals()[var] = evaluated_value
        await ctx.send(f"Global variable `{var}` set to:\n```{evaluated_value}```")
    except Exception as e:
        await ctx.send(f"Error setting variable `{var}`:\n```{e}```")

@bot.command()
async def run(ctx, *, code: str):
    if ctx.author.id not in authorized_user:
        return await ctx.send("unauthorized")

    scope = globals()
    scope.update({
        "ctx": ctx,
        "bot": bot,
        "discord": discord
    })

    function_code = "async def __ex():\n"
    for line in code.split('\n'):
        function_code += f"    {line}\n"

    exec(function_code, scope, scope)
    await scope['__ex']()

@bot.command()
async def shutdown(ctx):
    if ctx.author.id not in authorized_user:
        return  # Silent ignore

    embed = discord.Embed(
        title="Power Option: Shutdown",
        description="Cleaned up and shutdown. Goodbye!",
        color=discord.Color.red()
    )
    await ctx.send(embed=embed)
    try:
        kb_api.client.servers.send_power_action(server_id, "stop")
    except Exception:
        await bot.close()

@bot.command()
async def restart(ctx):
    if ctx.author.id not in authorized_user:
        return  # Silent ignore

    embed = discord.Embed(
        title="Power Option: Restart",
        description="Bot is restarting...",
        color=discord.Color.orange()
    )
    msg = await ctx.send(embed=embed)


    with open("restart.json", "w") as f:
        json.dump({
            "channel_id": msg.channel.id,
            "message_id": msg.id
        }, f)

    
    serverstats = kb_api.client.servers.get_server_utilization(server_id)
    action = serverstats.get("current_state", "").lower()
    if action == "offline":
        os.execv(sys.executable, ['python'] + sys.argv)
    elif action == "running":
        kb_api.client.servers.send_power_action(server_id, "restart")



if __name__ == "__main__":
    bot.run(os.getenv("bot_token"))