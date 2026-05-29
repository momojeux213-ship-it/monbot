import discord
from discord.ext import commands, tasks
import json, random, asyncio, datetime, os, urllib.request
from collections import defaultdict

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

def load_data(file):
    try:
        with open(file) as f: return json.load(f)
    except: return {}

def save_data(file, data):
    with open(file, "w") as f: json.dump(data, f, indent=2)

xp_data = load_data("xp.json")
warns_data = load_data("warns.json")
birthdays = load_data("birthdays.json")

XP_ROLES = {20: "Niveau 20+", 50: "Niveau 50+"}
LOG_CHANNEL = "logs-moderation"
TICKET_CATEGORY = "Tickets & Support"
WELCOME_CHANNEL = "presentation"
MOTS_INTERDITS = ["insulte1", "insulte2", "insulte3"]

xp_cooldowns = defaultdict(lambda: 0)
message_counts = defaultdict(list)

# XP
@bot.event
async def on_message(message):
    if message.author.bot: return
    await bot.process_commands(message)
    uid = str(message.author.id)
    now = datetime.datetime.now().timestamp()
    if now - xp_cooldowns[uid] < 60: return
    xp_cooldowns[uid] = now
    if uid not in xp_data:
        xp_data[uid] = {"xp": 0, "level": 0, "messages": 0}
    xp_data[uid]["xp"] += random.randint(15, 25)
    xp_data[uid]["messages"] += 1
    lvl = int(xp_data[uid]["xp"] ** 0.5 // 10)
    if lvl > xp_data[uid]["level"]:
        xp_data[uid]["level"] = lvl
        await message.channel.send(f"Felicitations {message.author.mention} niveau **{lvl}** !", delete_after=10)
        for req, role_name in XP_ROLES.items():
            role = discord.utils.get(message.guild.roles, name=role_name)
            if role and lvl >= req and role not in message.author.roles:
                await message.author.add_roles(role)
    save_data("xp.json", xp_data)

@bot.command()
async def rank(ctx, member: discord.Member = None):
    member = member or ctx.author
    uid = str(member.id)
    d = xp_data.get(uid, {"xp": 0, "level": 0, "messages": 0})
    sorted_users = sorted(xp_data.items(), key=lambda x: x[1]["xp"], reverse=True)
    rang = next((i+1 for i, (k,_) in enumerate(sorted_users) if k==uid), "?")
    em = discord.Embed(title=f"Rang de {member.display_name}", color=0x5865F2)
    em.add_field(name="XP", value=d["xp"])
    em.add_field(name="Niveau", value=d["level"])
    em.add_field(name="Classement", value=f"#{rang}")
    em.add_field(name="Messages", value=d["messages"])
    await ctx.send(embed=em)

@bot.command()
async def leaderboard(ctx):
    top = sorted(xp_data.items(), key=lambda x: x[1]["xp"], reverse=True)[:10]
    em = discord.Embed(title="Top 10 XP", color=0xFFD700)
    for i, (uid, d) in enumerate(top, 1):
        user = bot.get_user(int(uid))
        name = user.display_name if user else f"ID:{uid}"
        em.add_field(name=f"#{i} {name}", value=f"Nv.{d['level']} - {d['xp']} XP", inline=False)
    await ctx.send(embed=em)

# MODERATION
async def log_action(guild, embed):
    ch = discord.utils.get(guild.text_channels, name=LOG_CHANNEL)
    if ch: await ch.send(embed=embed)

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="Aucune raison"):
    await member.kick(reason=reason)
    em = discord.Embed(title="Kick", color=0xE67E22, description=f"{member} expulse par {ctx.author} - {reason}")
    await ctx.send(embed=em)
    await log_action(ctx.guild, em)

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="Aucune raison"):
    await member.ban(reason=reason)
    em = discord.Embed(title="Ban", color=0xE74C3C, description=f"{member} banni par {ctx.author} - {reason}")
    await ctx.send(embed=em)
    await log_action(ctx.guild, em)

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    user = await bot.fetch_user(user_id)
    await ctx.guild.unban(user)
    await ctx.send(f"{user} debanni.")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, minutes: int=10, *, reason="Aucune raison"):
    await member.timeout(datetime.timedelta(minutes=minutes), reason=reason)
    em = discord.Embed(title="Mute", color=0xF1C40F, description=f"{member} mute {minutes}min par {ctx.author} - {reason}")
    await ctx.send(embed=em)
    await log_action(ctx.guild, em)

@bot.command()
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member):
    await member.timeout(None)
    em = discord.Embed(title="Unmute", color=0x2ECC71, description=f"{member} demute par {ctx.author}")
    await ctx.send(embed=em)
    await log_action(ctx.guild, em)

@bot.command()
@commands.has_permissions(moderate_members=True)
async def warn(ctx, member: discord.Member, *, reason="Aucune raison"):
    uid = str(member.id)
    if uid not in warns_data: warns_data[uid] = []
    warns_data[uid].append({"reason": reason, "by": str(ctx.author), "date": str(datetime.date.today())})
    save_data("warns.json", warns_data)
    count = len(warns_data[uid])
    await ctx.send(f"{member.mention} averti ({count} fois). Raison: {reason}")
    if count >= 3:
        await member.timeout(datetime.timedelta(hours=1), reason="3 avertissements")
        await ctx.send(f"{member.mention} mute automatiquement (3 warns).")

@bot.command()
async def warns(ctx, member: discord.Member = None):
    member = member or ctx.author
    uid = str(member.id)
    w = warns_data.get(uid, [])
    em = discord.Embed(title=f"Avertissements de {member.display_name}", color=0xF39C12)
    for i, w2 in enumerate(w, 1):
        em.add_field(name=f"#{i}", value=f"{w2['reason']} par {w2['by']} ({w2['date']})", inline=False)
    if not w: em.description = "Aucun avertissement"
    await ctx.send(embed=em)

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int=10):
    deleted = await ctx.channel.purge(limit=amount+1)
    await ctx.send(f"{len(deleted)-1} messages supprimes.", delete_after=5)

# TICKETS
class TicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Ouvrir un ticket", style=discord.ButtonStyle.blurple, emoji="ticket", custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        cat = discord.utils.get(guild.categories, name=TICKET_CATEGORY)
        existing = discord.utils.get(guild.text_channels, name=f"ticket-{interaction.user.name.lower()}")
        if existing:
            await interaction.response.send_message("Tu as deja un ticket ouvert!", ephemeral=True)
            return
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        ch = await guild.create_text_channel(f"ticket-{interaction.user.name}", category=cat, overwrites=overwrites)
        view = CloseTicketView()
        await ch.send(f"{interaction.user.mention} decris ton probleme. Le staff va t'aider!", view=view)
        await interaction.response.send_message(f"Ticket cree: {ch.mention}", ephemeral=True)

class CloseTicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Fermer le ticket", style=discord.ButtonStyle.red, emoji="lock", custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Fermeture dans 5s...")
        await asyncio.sleep(5)
        await interaction.channel.delete()

@bot.command()
async def setup_ticket(ctx):
    em = discord.Embed(title="Support", description="Clique ci-dessous pour ouvrir un ticket.", color=0x5865F2)
    await ctx.send(embed=em, view=TicketView())

# CONFESSIONS
class ConfessionModal(discord.ui.Modal, title="Confession anonyme"):
    confession = discord.ui.TextInput(
        label="Ta confession",
        style=discord.TextStyle.long,
        placeholder="Ecris ta confession ici...",
        required=True,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        ch = None
        for channel in interaction.guild.text_channels:
            if "confession" in channel.name.lower():
                ch = channel
                break
        if not ch:
            await interaction.response.send_message("Salon confessions introuvable!", ephemeral=True)
            return
        em = discord.Embed(title="Confession anonyme", description=self.confession.value, color=0x9B59B6)
        em.set_footer(text="Confession anonyme")
        await ch.send(embed=em)
        await interaction.response.send_message("Ta confession a ete envoyee anonymement!", ephemeral=True)

class ConfessionView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Ecrire une confession", style=discord.ButtonStyle.blurple, emoji="💬", custom_id="confession_btn_v2")
    async def confession_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ConfessionModal())

@bot.command()
@commands.has_permissions(administrator=True)
async def setupconfession(ctx):
    em = discord.Embed(title="Confessions anonymes", description="Clique ci-dessous pour ecrire une confession anonyme!", color=0x9B59B6)
    await ctx.send(embed=em, view=ConfessionView())

# GIVEAWAYS
@bot.command()
@commands.has_permissions(manage_guild=True)
async def giveaway(ctx, duration_min: int, winners: int, *, prize: str):
    end_time = datetime.datetime.now() + datetime.timedelta(minutes=duration_min)
    em = discord.Embed(title=f"GIVEAWAY: {prize}", color=0xFFD700,
        description=f"Reagis avec pour participer!\n\nGagnants: {winners}\nFin: {end_time.strftime('%H:%M')}")
    msg = await ctx.send(embed=em)
    await msg.add_reaction("🎉")
    await asyncio.sleep(duration_min * 60)
    msg = await ctx.channel.fetch_message(msg.id)
    reaction = discord.utils.get(msg.reactions, emoji="🎉")
    users = [u async for u in reaction.users() if not u.bot]
    if not users:
        await ctx.send("Personne n'a participe")
        return
    chosen = random.sample(users, min(winners, len(users)))
    mentions = ", ".join(u.mention for u in chosen)
    await ctx.send(f"Felicitations {mentions}! Vous remportez **{prize}**!")

# BIENVENUE
@bot.event
async def on_member_join(member):
    role = discord.utils.get(member.guild.roles, name="Nouveau")
    if role: await member.add_roles(role)
    ch = discord.utils.get(member.guild.text_channels, name=WELCOME_CHANNEL)
    if ch:
        em = discord.Embed(title=f"Bienvenue {member.display_name}!",
            description=f"Tu es le membre #{member.guild.member_count}! Lis les regles et presente-toi!",
            color=0x2ECC71)
        em.set_thumbnail(url=member.display_avatar.url)
        await ch.send(embed=em)

@bot.event
async def on_member_remove(member):
    ch = discord.utils.get(member.guild.text_channels, name="general")
    if ch: await ch.send(f"{member.display_name} a quitte le serveur.")

# UTILITAIRES
@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! {round(bot.latency*1000)}ms")

@bot.command()
async def serverinfo(ctx):
    g = ctx.guild
    em = discord.Embed(title=g.name, color=0x5865F2)
    em.add_field(name="Membres", value=g.member_count)
    em.add_field(name="Salons", value=len(g.channels))
    em.add_field(name="Roles", value=len(g.roles))
    em.add_field(name="Boosts", value=g.premium_subscription_count)
    await ctx.send(embed=em)

@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    em = discord.Embed(title=member.display_name, color=member.color)
    em.add_field(name="ID", value=member.id)
    em.add_field(name="Roles", value=len(member.roles))
    em.add_field(name="Rejoint le", value=member.joined_at.strftime("%d/%m/%Y"))
    em.set_thumbnail(url=member.display_avatar.url)
    await ctx.send(embed=em)

@bot.command()
async def poll(ctx, question: str, *options):
    if len(options) > 9:
        await ctx.send("Max 9 options!")
        return
    emojis = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣"]
    desc = "\n".join(f"{emojis[i]} {opt}" for i, opt in enumerate(options))
    em = discord.Embed(title=question, description=desc, color=0x3498DB)
    msg = await ctx.send(embed=em)
    for i in range(len(options)): await msg.add_reaction(emojis[i])

@bot.command()
async def help_bot(ctx):
    em = discord.Embed(title="Commandes du Bot", color=0x5865F2)
    em.add_field(name="XP", value="rank / leaderboard", inline=False)
    em.add_field(name="Moderation", value="kick / ban / unban / mute / unmute / warn / warns / clear", inline=False)
    em.add_field(name="Utilitaires", value="ping / serverinfo / userinfo / poll / stats / serverstats", inline=False)
    em.add_field(name="Fun", value="blague / 8ball / pileouface / des / choisir / compatibilite", inline=False)
    em.add_field(name="Communaute", value="anniversaire / meteo", inline=False)
    em.add_field(name="Events", value="giveaway <min> <gagnants> <prix>", inline=False)
    em.add_field(name="Admin", value="setup_ticket / setupconfession", inline=False)
    await ctx.send(embed=em)

# FUN
@bot.command()
async def blague(ctx):
    blagues = [
        "Pourquoi les plongeurs plongent toujours en arriere ? Parce que sinon ils tomberaient dans le bateau !",
        "Qu'est-ce qu'un canif ? Un petit fien !",
        "Pourquoi les informaticiens confondent Halloween et Noel ? Parce que OCT 31 = DEC 25 !",
        "Un escargot se fait ecraser par une tortue. Il repond : je sais pas, ca allait trop vite !",
        "Qu'est-ce qu'un crocodile qui surveille la cour d'ecole ? Un sac a dents !",
        "Comment appelle-t-on un chat tombe dans un pot de peinture le jour de Noel ? Un chat-peint de Noel !",
    ]
    await ctx.send(random.choice(blagues))

@bot.command(name="8ball")
async def eight_ball(ctx, *, question: str):
    reponses = ["Oui absolument!", "C'est certain!", "Sans aucun doute!", "Tres probablement!",
        "Les signes pointent vers oui...", "Je ne peux pas le dire maintenant.", "Reconsidere la question.",
        "Ne compte pas la-dessus.", "Ma reponse est non.", "Tres peu probable."]
    em = discord.Embed(title="Magic 8-Ball", color=0x000080)
    em.add_field(name="Question", value=question, inline=False)
    em.add_field(name="Reponse", value=random.choice(reponses), inline=False)
    await ctx.send(embed=em)

@bot.command()
async def pileouface(ctx):
    await ctx.send(f"{ctx.author.mention} - {random.choice(['PILE!', 'FACE!'])}")

@bot.command()
async def des(ctx, faces: int = 6):
    await ctx.send(f"{ctx.author.mention} a lance un de a {faces} faces : **{random.randint(1, faces)}** !")

@bot.command()
async def choisir(ctx, *options):
    if len(options) < 2:
        await ctx.send("Donne au moins 2 options ! Ex: !choisir pizza burger")
        return
    await ctx.send(f"J'ai choisi : **{random.choice(options)}** !")

@bot.command()
async def compatibilite(ctx, membre: discord.Member):
    score = random.randint(1, 100)
    bar = "=" * (score // 10) + "-" * (10 - score // 10)
    em = discord.Embed(title="Compatibilite amoureuse", color=0xFF69B4)
    em.description = f"{ctx.author.mention} + {membre.mention} = **{score}%**\n`{bar}`"
    await ctx.send(embed=em)

# ANNIVERSAIRES
@bot.command()
async def anniversaire(ctx, date: str):
    try:
        jour, mois = date.split("/")
        int(jour); int(mois)
        uid = str(ctx.author.id)
        birthdays[uid] = {"date": date, "name": ctx.author.display_name}
        save_data("birthdays.json", birthdays)
        await ctx.send(f"Anniversaire enregistre le **{date}** pour {ctx.author.mention}!")
    except:
        await ctx.send("Format invalide ! Utilise !anniversaire JJ/MM ex: !anniversaire 25/12")

@tasks.loop(hours=24)
async def check_anniversaires():
    today = datetime.datetime.now().strftime("%d/%m")
    for guild in bot.guilds:
        ch = discord.utils.get(guild.text_channels, name="general")
        if not ch: continue
        for uid, data in birthdays.items():
            if data["date"] == today:
                member = guild.get_member(int(uid))
                if member:
                    em = discord.Embed(title="Joyeux Anniversaire!", color=0xFFD700,
                        description=f"Toute la communaute souhaite un joyeux anniversaire a {member.mention}!")
                    await ch.send(embed=em)

# ANTI-SPAM
@bot.listen("on_message")
async def anti_spam_insultes(message):
    if message.author.bot: return
    if message.author.guild_permissions.manage_messages: return
    contenu = message.content.lower()
    for mot in MOTS_INTERDITS:
        if mot in contenu:
            await message.delete()
            await message.channel.send(f"{message.author.mention} ce mot est interdit!", delete_after=5)
            return
    uid = str(message.author.id)
    now = datetime.datetime.now().timestamp()
    message_counts[uid] = [t for t in message_counts[uid] if now - t < 5]
    message_counts[uid].append(now)
    if len(message_counts[uid]) >= 5:
        await message.author.timeout(datetime.timedelta(minutes=2), reason="Spam")
        await message.channel.send(f"{message.author.mention} mute 2 minutes pour spam!", delete_after=10)
        message_counts[uid] = []

# METEO
@bot.command()
async def meteo(ctx, *, ville: str):
    try:
        url = f"https://wttr.in/{ville.replace(' ', '+')}?format=j1"
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read().decode())
        c = data["current_condition"][0]
        em = discord.Embed(title=f"Meteo a {ville.title()}", color=0x3498DB)
        em.add_field(name="Temperature", value=f"{c['temp_C']}C (ressenti {c['FeelsLikeC']}C)")
        em.add_field(name="Conditions", value=c["weatherDesc"][0]["value"])
        em.add_field(name="Humidite", value=f"{c['humidity']}%")
        em.add_field(name="Vent", value=f"{c['windspeedKmph']} km/h")
        await ctx.send(embed=em)
    except:
        await ctx.send(f"Impossible de trouver la meteo pour {ville}.")

# STATS
@bot.command()
async def stats(ctx, membre: discord.Member = None):
    membre = membre or ctx.author
    uid = str(membre.id)
    d = xp_data.get(uid, {"xp": 0, "level": 0, "messages": 0})
    now = datetime.datetime.now(datetime.timezone.utc)
    jours = (now - membre.joined_at).days
    jours_discord = (now - membre.created_at).days
    sorted_users = sorted(xp_data.items(), key=lambda x: x[1]["xp"], reverse=True)
    rang = next((i+1 for i, (k, _) in enumerate(sorted_users) if k == uid), "?")
    niveau = d["level"]
    xp_actuel = d["xp"]
    progression = int(((xp_actuel - (niveau*10)**2) / max(((niveau+1)*10)**2 - (niveau*10)**2, 1)) * 10)
    barre = "=" * progression + "-" * (10 - progression)
    roles = [r for r in membre.roles if r.name != "@everyone"]
    role_top = roles[-1].mention if roles else "Aucun"
    em = discord.Embed(title=f"Profil de {membre.display_name}", color=0x5865F2)
    em.set_thumbnail(url=membre.display_avatar.url)
    em.add_field(name="Messages", value=f"**{d['messages']}**", inline=True)
    em.add_field(name="Niveau", value=f"**{niveau}** ({xp_actuel} XP)", inline=True)
    em.add_field(name="Classement", value=f"**#{rang}**", inline=True)
    em.add_field(name="Progression", value=f"`{barre}` vers niv.{niveau+1}", inline=False)
    em.add_field(name="Sur le serveur", value=f"**{jours} jours**", inline=True)
    em.add_field(name="Compte cree", value=f"Il y a **{jours_discord} jours**", inline=True)
    em.add_field(name="Role principal", value=role_top, inline=True)
    await ctx.send(embed=em)

@bot.command()
async def serverstats(ctx):
    g = ctx.guild
    now = datetime.datetime.now(datetime.timezone.utc)
    age = (now - g.created_at).days
    en_ligne = sum(1 for m in g.members if m.status != discord.Status.offline and not m.bot)
    bots = sum(1 for m in g.members if m.bot)
    em = discord.Embed(title=f"Statistiques de {g.name}", color=0x5865F2)
    em.add_field(name="Membres", value=f"**{g.member_count}**", inline=True)
    em.add_field(name="En ligne", value=f"**{en_ligne}**", inline=True)
    em.add_field(name="Bots", value=f"**{bots}**", inline=True)
    em.add_field(name="Salons texte", value=f"**{len(g.text_channels)}**", inline=True)
    em.add_field(name="Salons vocaux", value=f"**{len(g.voice_channels)}**", inline=True)
    em.add_field(name="Roles", value=f"**{len(g.roles)}**", inline=True)
    em.add_field(name="Boosts", value=f"**{g.premium_subscription_count}**", inline=True)
    em.add_field(name="Age du serveur", value=f"**{age} jours**", inline=True)
    await ctx.send(embed=em)

# ON READY
@bot.event
async def on_ready():
    print(f"Bot connecte: {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="la communaute"))
    bot.add_view(TicketView())
    bot.add_view(CloseTicketView())
    bot.add_view(ConfessionView())
    if not check_anniversaires.is_running():
        check_anniversaires.start()

bot.run(os.getenv("DISCORD_TOKEN"))
