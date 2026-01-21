import os
import discord
from discord.ext import commands
import json

# Load environment variables from .env file (for local testing)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, skip (will work fine on Railway)

# ======================
# INTENTS
# ======================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

PREFIX_FILE = "prefixes.json"

# ======================
# STORAGE
# ======================

def load_prefixes():
    # Try to load from environment variable first (for cloud hosting)
    env_prefixes = os.getenv("ROLE_PREFIXES")
    if env_prefixes:
        try:
            return json.loads(env_prefixes)
        except:
            pass
    
    # Fallback to file storage
    if not os.path.exists(PREFIX_FILE):
        return {}
    with open(PREFIX_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_prefixes(data):
    # Save to file (will persist on Railway)
    with open(PREFIX_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

role_prefixes = load_prefixes()

# ======================
# HELPERS
# ======================

def get_display_roles(member):
    """Get all roles that have a configured prefix"""
    return [r for r in member.roles if str(r.id) in role_prefixes]

def get_highest_display_role(member):
    """Get the highest positioned role with a prefix"""
    roles = get_display_roles(member)
    if not roles:
        return None
    return max(roles, key=lambda r: r.position)

async def apply_prefix(member, role):
    """Apply a role's prefix to a member's nickname"""
    prefix = role_prefixes.get(str(role.id))
    if not prefix:
        return

    # Use current nickname if exists, otherwise use username
    base_name = member.display_name
    
    # Remove old prefix if it exists (to avoid stacking prefixes)
    if " | " in base_name:
        base_name = base_name.split(" | ", 1)[1]
    
    nickname = f"{prefix} | {base_name}"

    try:
        await member.edit(nick=nickname)
    except discord.Forbidden:
        print(f"Cannot change nickname for {member.name} - insufficient permissions")
    except discord.HTTPException as e:
        print(f"Failed to change nickname for {member.name}: {e}")

# ======================
# ADMIN COMMANDS
# ======================

@bot.command()
@commands.has_permissions(administrator=True)
async def setprefix(ctx, role: discord.Role, *, prefix: str):
    """Set a prefix for a role"""
    role_prefixes[str(role.id)] = prefix
    save_prefixes(role_prefixes)
    await ctx.send(f"✅ Prefix set for **{role.name}** → `{prefix}`")

@bot.command()
@commands.has_permissions(administrator=True)
async def removeprefix(ctx, role: discord.Role):
    """Remove a prefix from a role"""
    if str(role.id) in role_prefixes:
        role_prefixes.pop(str(role.id))
        save_prefixes(role_prefixes)
        await ctx.send(f"❌ Prefix removed for **{role.name}**")
    else:
        await ctx.send("❌ This role has no prefix.")

@bot.command()
@commands.has_permissions(administrator=True)
async def listprefixes(ctx):
    """List all configured prefixes"""
    if not role_prefixes:
        await ctx.send("No prefixes configured.")
        return
    
    lines = []
    for role_id, prefix in role_prefixes.items():
        role = ctx.guild.get_role(int(role_id))
        role_name = role.name if role else f"Unknown Role ({role_id})"
        lines.append(f"**{role_name}**: `{prefix}`")
    
    await ctx.send("**Configured Prefixes:**\n" + "\n".join(lines))

@bot.command()
@commands.has_permissions(administrator=True)
async def updateall(ctx):
    """Update all members' prefixes based on current settings"""
    count = 0
    for member in ctx.guild.members:
        role = get_highest_display_role(member)
        if role:
            await apply_prefix(member, role)
            count += 1
    
    await ctx.send(f"✅ Updated {count} member(s) with new prefixes!")

@bot.command()
@commands.has_permissions(administrator=True)
async def updateuser(ctx, member: discord.Member):
    """Update a specific user's prefix"""
    role = get_highest_display_role(member)
    if role:
        await apply_prefix(member, role)
        await ctx.send(f"✅ Updated prefix for {member.mention}")
    else:
        await ctx.send(f"❌ {member.mention} has no roles with prefixes.")

# ======================
# AUTO ROLE UPDATE
# ======================

@bot.event
async def on_member_update(before, after):
    """Automatically update nickname when roles change"""
    if before.roles == after.roles:
        return

    role = get_highest_display_role(after)
    if role:
        await apply_prefix(after, role)

# ======================
# MANUAL PREFIX SELECT
# ======================

class TagSelect(discord.ui.Select):
    def __init__(self, member):
        options = []

        # Add option to remove prefix
        options.append(
            discord.SelectOption(
                label="Remove Prefix",
                description="Clear your nickname",
                value="clear",
                emoji="🚫"
            )
        )

        # Add all available role prefixes
        for role in sorted(get_display_roles(member), key=lambda r: r.position, reverse=True):
            options.append(
                discord.SelectOption(
                    label=role_prefixes[str(role.id)],
                    description=role.name,
                    value=str(role.id)  # Store role ID, not prefix text
                )
            )

        # If no prefixes available, show placeholder
        if len(options) == 1:  # Only the "clear" option
            options = [
                discord.SelectOption(label="No prefixes available", value="none")
            ]

        super().__init__(
            placeholder="Choose your prefix",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]

        # Ensure we're in a guild
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command only works in servers.",
                ephemeral=True
            )
            return

        # Handle "no prefixes" case
        if choice == "none":
            await interaction.response.send_message(
                "❌ You have no prefixes available.",
                ephemeral=True
            )
            return

        # Handle clearing nickname
        if choice == "clear":
            try:
                await interaction.user.edit(nick=None)
                await interaction.response.send_message(
                    "✅ Prefix removed. Your nickname has been cleared.",
                    ephemeral=True
                )
            except discord.Forbidden:
                await interaction.response.send_message(
                    "❌ I don't have permission to change your nickname.",
                    ephemeral=True
                )
            except discord.HTTPException:
                await interaction.response.send_message(
                    "❌ Failed to change your nickname.",
                    ephemeral=True
                )
            return

        # Apply selected prefix
        role = interaction.guild.get_role(int(choice))
        
        # Verify user still has this role
        if not role or role not in interaction.user.roles:
            await interaction.response.send_message(
                "❌ You no longer have access to this prefix.",
                ephemeral=True
            )
            return

        prefix = role_prefixes.get(str(role.id))
        if not prefix:
            await interaction.response.send_message(
                "❌ This prefix is no longer configured.",
                ephemeral=True
            )
            return

        # Use current display name, remove old prefix if exists
        base_name = interaction.user.display_name
        if " | " in base_name:
            base_name = base_name.split(" | ", 1)[1]
        
        nickname = f"{prefix} | {base_name}"

        try:
            await interaction.user.edit(nick=nickname)
            await interaction.response.send_message(
                f"✅ Prefix changed to **{nickname}**",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to change your nickname.",
                ephemeral=True
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                "❌ Failed to change your nickname.",
                ephemeral=True
            )

class TagView(discord.ui.View):
    def __init__(self, member):
        super().__init__(timeout=60)
        self.add_item(TagSelect(member))

@bot.command()
async def tag(ctx):
    """Open the prefix selection menu"""
    await ctx.send(
        "Select which prefix you want to show:",
        view=TagView(ctx.author),
        delete_after=60
    )

@bot.command()
async def help(ctx):
    """Show all available commands"""
    
    # Check if user is admin
    is_admin = ctx.author.guild_permissions.administrator
    
    user_commands = """
**🎯 User Commands:**
`!tag` - Open a menu to select your prefix from available roles
`!help` - Show this help message
    """
    
    admin_commands = """
**⚙️ Admin Commands:**
`!setprefix @role prefix` - Set a prefix for a role
  Example: `!setprefix @VIP 💎`

`!removeprefix @role` - Remove a role's prefix
  Example: `!removeprefix @VIP`

`!listprefixes` - Show all configured role prefixes

`!updateall` - Update all members' nicknames with current prefix settings
  Use this after changing prefixes to apply changes

`!updateuser @member` - Update a specific member's nickname
  Example: `!updateuser @JohnDoe`
    """
    
    if is_admin:
        embed = discord.Embed(
            title="🤖 Prefix Bot - Help",
            description=user_commands + "\n" + admin_commands,
            color=discord.Color.blue()
        )
        embed.set_footer(text="Bot by Anthropic Claude | Prefix management made easy")
    else:
        embed = discord.Embed(
            title="🤖 Prefix Bot - Help",
            description=user_commands,
            color=discord.Color.green()
        )
        embed.set_footer(text="Contact an admin to set up role prefixes")
    
    await ctx.send(embed=embed)

# ======================
# BOT EVENTS
# ======================

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    print(f"✅ Serving {len(bot.guilds)} guild(s)")

# ======================
# RUN
# ======================

bot.run(os.getenv("BOT_TOKEN"))