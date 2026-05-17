import discord
from discord.ext import commands, tasks
from discord import app_commands
import json, random, asyncio, datetime, os
from collections import defaultdict

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ─── Base de données JSON simple ───────────────────────────
def load_data(file):
    try:
        with open(file) as f: return json.load(f)
    except: return {}

def save_data(file, data):
    with open(file, "w") as f: json.dump(data, f, indent=2)

xp_data = load_data("xp.json")
warns_data = load_data("warns.json")

# ─── Constantes (à modifier selon ton serveur) ──────────────
XP_ROLES = {
    20: "Niveau 20+",
    50: "Niveau 50+"
}
LOG_CHANNEL = "logs-modération"
TICKET_CATEGORY = "Tickets & Support"
WELCOME_CHANNEL = "présentation"

# ─── XP SYSTEM ─────────────────────────────────────────────
xp_cooldowns = defaultdict(lambda: 0)

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
    xp_gain = random.randint(15, 25)
    xp_data[uid]["xp"] += xp_gain
    xp_data[uid]["messages"] += 1
    lvl = int(xp_data[uid]["xp"] ** 0.5 // 10)
    if lvl > xp_data[uid]["level"]:
        xp_data[uid]["level"] = lvl
        await message.channel.send(
            f"🎉 {message.author.mention} passe au niveau **{lvl}** !", delete_after=10)
        await check_xp_roles(message.guild, message.author, lvl)
    save_data("xp.json", xp_data)

async def check_xp_roles(guild, member, level):
    for req_level, role_name in XP_ROLES.items():
        role = discord.utils.get(guild.roles, name=role_name)
        if role and level >= req_level and role not in member.roles:
            await member.add_roles(role)

@bot.command()
async def rank(ctx, member: discord.Member = None):
    member = member or ctx.author
    uid = str(member.id)
    d = xp_data.get(uid, {"xp": 0, "level": 0, "messages": 0})
    sorted_users = sorted(xp_data.items(), key=lambda x: x[1]["xp"], reverse=True)
    rank = next((i+1 for i, (k,_) in enumerate(sorted_users) if k==uid), "?")
    em = discord.Embed(title=f"📊 Rang de {member.display_name}", color=0x5865F2)
    em.add_field(name="XP", value=d["xp"])
    em.add_field(name="Niveau", value=d["level"])
    em.add_field(name="Classement", value=f"#{rank}")
    em.add_field(name="Messages", value=d["messages"])
    await ctx.send(embed=em)

@bot.command()
async def leaderboard(ctx):
    top = sorted(xp_data.items(), key=lambda x: x[1]["xp"], reverse=True)[:10]
    em = discord.Embed(title="🏆 Top 10 XP", color=0xFFD700)
    for i, (uid, d) in enumerate(top, 1):
        user = bot.get_user(int(uid))
        name = user.display_name if user else f"ID:{uid}"
        em.add_field(name=f"#{i} {name}", value=f"Nv.{d['level']} — {d['xp']} XP", inline=False)
    await ctx.send(embed=em)

# ─── MODÉRATION ─────────────────────────────────────────────
async def log_action(guild, embed):
    ch = discord.utils.get(guild.text_channels, name=LOG_CHANNEL)
    if ch: await ch.send(embed=embed)

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="Aucune raison"):
    await member.kick(reason=reason)
    em = discord.Embed(title="👢 Kick", color=0xE67E22,
        description=f"{member} expulsé par {ctx.author}\nRaison: {reason}")
    await ctx.send(embed=em); await log_action(ctx.guild, em)

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="Aucune raison"):
    await member.ban(reason=reason)
    em = discord.Embed(title="🔨 Ban", color=0xE74C3C,
        description=f"{member} banni par {ctx.author}\nRaison: {reason}")
    await ctx.send(embed=em); await log_action(ctx.guild, em)

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    user = await bot.fetch_user(user_id)
    await ctx.guild.unban(user)
    await ctx.send(f"✅ {user} débanni.")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, minutes: int=10, *, reason="Aucune raison"):
    duration = datetime.timedelta(minutes=minutes)
    await member.timeout(duration, reason=reason)
    em = discord.Embed(title="🔇 Mute", color=0xF1C40F,
        description=f"{member} muté {minutes}min par {ctx.author}\nRaison: {reason}")
    await ctx.send(embed=em); await log_action(ctx.guild, em)

@bot.command()
@commands.has_permissions(moderate_members=True)
async def warn(ctx, member: discord.Member, *, reason="Aucune raison"):
    uid = str(member.id)
    if uid not in warns_data: warns_data[uid] = []
    warns_data[uid].append({"reason": reason, "by": str(ctx.author), "date": str(datetime.date.today())})
    save_data("warns.json", warns_data)
    count = len(warns_data[uid])
    await ctx.send(f"⚠️ {member.mention} averti ({count} avertissement(s)). Raison: {reason}")
    if count >= 3:
        await member.timeout(datetime.timedelta(hours=1), reason="3 avertissements")
        await ctx.send(f"🔇 {member.mention} automatiquement muté (3 warns).")

@bot.command()
async def warns(ctx, member: discord.Member = None):
    member = member or ctx.author
    uid = str(member.id)
    w = warns_data.get(uid, [])
    em = discord.Embed(title=f"⚠️ Avertissements de {member.display_name}", color=0xF39C12)
    for i, warn in enumerate(w, 1):
        em.add_field(name=f"#{i}", value=f"{warn['reason']} — par {warn['by']} ({warn['date']})", inline=False)
    if not w: em.description = "Aucun avertissement ✅"
    await ctx.send(embed=em)

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int=10):
    deleted = await ctx.channel.purge(limit=amount+1)
    await ctx.send(f"🗑️ {len(deleted)-1} messages supprimés.", delete_after=5)

# ─── TICKETS ────────────────────────────────────────────────
class TicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Ouvrir un ticket", style=discord.ButtonStyle.blurple, emoji="🎫", custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        cat = discord.utils.get(guild.categories, name=TICKET_CATEGORY)
        existing = discord.utils.get(guild.text_channels, name=f"ticket-{interaction.user.name.lower()}")
        if existing:
            await interaction.response.send_message("Tu as déjà un ticket ouvert!", ephemeral=True); return
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        ch = await guild.create_text_channel(f"ticket-{interaction.user.name}", category=cat, overwrites=overwrites)
        view = CloseTicketView()
        await ch.send(f"👋 {interaction.user.mention}, décris ton problème. Le staff va t'aider!", view=view)
        await interaction.response.send_message(f"✅ Ticket créé: {ch.mention}", ephemeral=True)

class CloseTicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Fermer le ticket", style=discord.ButtonStyle.red, emoji="🔒", custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Fermeture dans 5s...")
        await asyncio.sleep(5); await interaction.channel.delete()

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_ticket(ctx):
    em = discord.Embed(title="🎫 Support", description="Clique ci-dessous pour ouvrir un ticket.", color=0x5865F2)
    await ctx.send(embed=em, view=TicketView())

# ─── GIVEAWAYS ──────────────────────────────────────────────
active_giveaways = {}

@bot.command()
@commands.has_permissions(manage_guild=True)
async def giveaway(ctx, duration_min: int, winners: int, *, prize: str):
    end_time = datetime.datetime.now() + datetime.timedelta(minutes=duration_min)
    em = discord.Embed(title=f"🎁 GIVEAWAY: {prize}", color=0xFFD700,
        description=f"Réagis avec 🎉 pour participer!\n\n👑 Gagnants: {winners}\n⏰ Fin: {end_time.strftime('%H:%M')}")
    msg = await ctx.send(embed=em)
    await msg.add_reaction("🎉")
    active_giveaways[msg.id] = {"prize": prize, "winners": winners, "end": end_time.timestamp(), "channel": ctx.channel.id}
    await asyncio.sleep(duration_min * 60)
    msg = await ctx.channel.fetch_message(msg.id)
    reaction = discord.utils.get(msg.reactions, emoji="🎉")
    users = [u async for u in reaction.users() if not u.bot]
    if not users: await ctx.send("Personne n'a participé 😢"); return
    chosen = random.sample(users, min(winners, len(users)))
    mentions = ", ".join(u.mention for u in chosen)
    await ctx.send(f"🎉 Félicitations {mentions}! Vous remportez **{prize}**!")

# ─── RÔLES AUTOMATIQUES ─────────────────────────────────────
@bot.event
async def on_member_join(member):
    role = discord.utils.get(member.guild.roles, name="Nouveau")
    if role: await member.add_roles(role)
    ch = discord.utils.get(member.guild.text_channels, name=WELCOME_CHANNEL)
    if ch:
        em = discord.Embed(title=f"👋 Bienvenue {member.display_name}!",
            description=f"Tu es le membre #{member.guild.member_count}!\nLis les règles et présente-toi!",
            color=0x2ECC71)
        em.set_thumbnail(url=member.display_avatar.url)
        await ch.send(embed=em)

@bot.event
async def on_member_remove(member):
    ch = discord.utils.get(member.guild.text_channels, name="général")
    if ch: await ch.send(f"👋 {member.display_name} a quitté le serveur.")

# ─── COMMANDES UTILITAIRES ──────────────────────────────────
@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! `{round(bot.latency*1000)}ms`")

@bot.command()
async def serverinfo(ctx):
    g = ctx.guild
    em = discord.Embed(title=g.name, color=0x5865F2)
    em.add_field(name="Membres", value=g.member_count)
    em.add_field(name="Salons", value=len(g.channels))
    em.add_field(name="Rôles", value=len(g.roles))
    em.add_field(name="Boosts", value=g.premium_subscription_count)
    em.set_thumbnail(url=g.icon.url if g.icon else "")
    await ctx.send(embed=em)

@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    em = discord.Embed(title=member.display_name, color=member.color)
    em.add_field(name="ID", value=member.id)
    em.add_field(name="Rôles", value=len(member.roles))
    em.add_field(name="Rejoint le", value=member.joined_at.strftime("%d/%m/%Y"))
    em.set_thumbnail(url=member.display_avatar.url)
    await ctx.send(embed=em)

@bot.command()
async def poll(ctx, question: str, *options):
    if len(options) > 9: await ctx.send("Max 9 options!"); return
    emojis = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣"]
    desc = "\n".join(f"{emojis[i]} {opt}" for i, opt in enumerate(options))
    em = discord.Embed(title=f"📊 {question}", description=desc, color=0x3498DB)
    msg = await ctx.send(embed=em)
    for i in range(len(options)): await msg.add_reaction(emojis[i])

@bot.command()
async def help_bot(ctx):
    em = discord.Embed(title="📚 Commandes du Bot", color=0x5865F2)
    em.add_field(name="XP", value="`!rank` `!leaderboard`", inline=False)
    em.add_field(name="Modération", value="`!kick` `!ban` `!mute` `!warn` `!clear`", inline=False)
    em.add_field(name="Utilitaires", value="`!ping` `!serverinfo` `!userinfo` `!poll`", inline=False)
    em.add_field(name="Events", value="`!giveaway <min> <gagnants> <prix>`", inline=False)
    em.add_field(name="Admin", value="`!setup_ticket`", inline=False)
    await ctx.send(embed=em)

@bot.event
async def on_ready():
    print(f"✅ {bot.user} connecté!")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, name="la communauté 👀"))
    bot.add_view(TicketView())
    bot.add_view(CloseTicketView())
    check_anniversaires.start()

# ─── COMMANDES FUN ──────────────────────────────────────────
import urllib.request

@bot.command()
async def blague(ctx):
    blagues = [
        "Pourquoi les plongeurs plongent-ils toujours en arrière ? Parce que sinon ils tomberaient dans le bateau !",
        "Un homme entre dans une bibliothèque et demande : 'Vous avez des livres sur la paranoïa ?' La bibliothécaire répond : 'Ils sont juste derrière vous !'",
        "Qu'est-ce qu'un canif ? Un petit fien !",
        "Pourquoi les informaticiens confondent-ils Halloween et Noël ? Parce que OCT 31 = DEC 25 !",
        "Un escargot se fait écraser par une tortue. La police lui demande : 'Que s'est-il passé ?' Il répond : 'Je sais pas, ça allait trop vite !'",
        "Qu'est-ce qu'un crocodile qui surveille la cour d'école ? Un sac à dents !",
        "Pourquoi le scarabée a-t-il gagné la course ? Parce qu'il était dans la bonne scarabée !",
        "Comment appelle-t-on un chat tombé dans un pot de peinture le jour de Noël ? Un chat-peint de Noël !",
    ]
    await ctx.send(f"😂 {random.choice(blagues)}")

@bot.command(name="8ball")
async def eight_ball(ctx, *, question: str):
    reponses = [
        "✅ Oui, absolument !",
        "✅ C'est certain !",
        "✅ Sans aucun doute !",
        "✅ Très probablement !",
        "🤔 Les signes pointent vers oui...",
        "🤔 Je ne peux pas le dire maintenant.",
        "🤔 Reconsidère la question.",
        "❌ Ne compte pas là-dessus.",
        "❌ Ma réponse est non.",
        "❌ Les perspectives ne sont pas bonnes.",
        "❌ Très peu probable.",
    ]
    em = discord.Embed(title="🎱 Magic 8-Ball", color=0x000080)
    em.add_field(name="Question", value=question, inline=False)
    em.add_field(name="Réponse", value=random.choice(reponses), inline=False)
    await ctx.send(embed=em)

@bot.command()
async def pileouface(ctx):
    resultat = random.choice(["🪙 PILE !", "🪙 FACE !"])
    await ctx.send(f"{ctx.author.mention} — {resultat}")

@bot.command()
async def des(ctx, faces: int = 6):
    resultat = random.randint(1, faces)
    await ctx.send(f"🎲 {ctx.author.mention} a lancé un dé à {faces} faces : **{resultat}** !")

@bot.command()
async def choisir(ctx, *options):
    if len(options) < 2:
        await ctx.send("Donne-moi au moins 2 options ! Ex: `!choisir pizza burger sushi`")
        return
    choix = random.choice(options)
    await ctx.send(f"🤔 J'ai choisi : **{choix}** !")

@bot.command()
async def compatibilite(ctx, membre: discord.Member):
    score = random.randint(1, 100)
    emoji = "💘" if score > 80 else "❤️" if score > 60 else "💔" if score < 30 else "🤔"
    em = discord.Embed(title=f"{emoji} Compatibilité amoureuse", color=0xFF69B4)
    em.description = f"{ctx.author.mention} + {membre.mention} = **{score}%** de compatibilité !"
    bar = "█" * (score // 10) + "░" * (10 - score // 10)
    em.add_field(name="Jauge", value=f"`{bar}` {score}%")
    await ctx.send(embed=em)

# ─── ANNIVERSAIRES ──────────────────────────────────────────
birthdays = load_data("birthdays.json")

@bot.command()
async def anniversaire(ctx, date: str):
    """Enregistre ton anniversaire. Format: JJ/MM ex: !anniversaire 25/12"""
    try:
        jour, mois = date.split("/")
        int(jour); int(mois)
        uid = str(ctx.author.id)
        birthdays[uid] = {"date": date, "name": ctx.author.display_name}
        save_data("birthdays.json", birthdays)
        await ctx.send(f"🎂 Anniversaire enregistré le **{date}** pour {ctx.author.mention} !")
    except:
        await ctx.send("Format invalide ! Utilise `!anniversaire JJ/MM` ex: `!anniversaire 25/12`")

@tasks.loop(hours=24)
async def check_anniversaires():
    today = datetime.datetime.now().strftime("%d/%m")
    for guild in bot.guilds:
        ch = discord.utils.get(guild.text_channels, name="général")
        if not ch: continue
        for uid, data in birthdays.items():
            if data["date"] == today:
                member = guild.get_member(int(uid))
                if member:
                    em = discord.Embed(title="🎂 Joyeux Anniversaire !", color=0xFFD700,
                        description=f"Toute la communauté souhaite un joyeux anniversaire à {member.mention} ! 🥳🎉")
                    await ch.send(embed=em)

# ─── ANTI-SPAM & ANTI-INSULTES ──────────────────────────────
message_counts = defaultdict(list)
MOTS_INTERDITS = ["insulte1", "insulte2", "insulte3"]  # Ajoute tes mots interdits ici

@bot.listen("on_message")
async def anti_spam_insultes(message):
    if message.author.bot: return
    if message.author.guild_permissions.manage_messages: return

    # Anti-insultes
    contenu = message.content.lower()
    for mot in MOTS_INTERDITS:
        if mot in contenu:
            await message.delete()
            await message.channel.send(
                f"⚠️ {message.author.mention} ce mot est interdit !", delete_after=5)
            return

    # Anti-spam (5 messages en 5 secondes)
    uid = str(message.author.id)
    now = datetime.datetime.now().timestamp()
    message_counts[uid] = [t for t in message_counts[uid] if now - t < 5]
    message_counts[uid].append(now)
    if len(message_counts[uid]) >= 5:
        await message.author.timeout(datetime.timedelta(minutes=2), reason="Spam détecté")
        await message.channel.send(
            f"🔇 {message.author.mention} a été muté 2 minutes pour spam !", delete_after=10)
        message_counts[uid] = []

# ─── MÉTÉO ──────────────────────────────────────────────────
@bot.command(name="meteo")
async def meteo(ctx, *, ville: str):
    try:
        ville_encoded = ville.replace(" ", "+")
        url = f"https://wttr.in/{ville_encoded}?format=j1"
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode())
        current = data["current_condition"][0]
        temp = current["temp_C"]
        ressenti = current["FeelsLikeC"]
        desc = current["weatherDesc"][0]["value"]
        humidite = current["humidity"]
        vent = current["windspeedKmph"]
        emojis = {"Sunny": "☀️", "Clear": "🌙", "Cloudy": "☁️", "Rain": "🌧️",
                  "Snow": "❄️", "Thunder": "⛈️", "Fog": "🌫️", "Overcast": "☁️",
                  "Partly": "⛅"}
        emoji = next((v for k, v in emojis.items() if k.lower() in desc.lower()), "🌡️")
        em = discord.Embed(title=f"{emoji} Météo à {ville.title()}", color=0x3498DB)
        em.add_field(name="🌡️ Température", value=f"{temp}°C (ressenti {ressenti}°C)")
        em.add_field(name="📋 Conditions", value=desc)
        em.add_field(name="💧 Humidité", value=f"{humidite}%")
        em.add_field(name="💨 Vent", value=f"{vent} km/h")
        await ctx.send(embed=em)
    except:
        await ctx.send(f"❌ Impossible de trouver la météo pour **{ville}**. Vérifie le nom de la ville !")
# ─── STATISTIQUES MEMBRES ───────────────────────────────────

@bot.command()
async def stats(ctx, membre: discord.Member = None):
    membre = membre or ctx.author
    uid = str(membre.id)
    d = xp_data.get(uid, {"xp": 0, "level": 0, "messages": 0})

    # Calcul du temps sur le serveur
    maintenant = datetime.datetime.now(datetime.timezone.utc)
    rejoint_il_y_a = maintenant - membre.joined_at
    jours = rejoint_il_y_a.days
    heures = rejoint_il_y_a.seconds // 3600

    # Calcul du temps sur Discord
    sur_discord = maintenant - membre.created_at
    jours_discord = sur_discord.days

    # Classement XP
    sorted_users = sorted(xp_data.items(), key=lambda x: x[1]["xp"], reverse=True)
    rang = next((i+1 for i, (k, _) in enumerate(sorted_users) if k == uid), "?")

    # Barre de progression XP
    xp_actuel = d["xp"]
    niveau = d["level"]
    xp_prochain = ((niveau + 1) * 10) ** 2
    xp_niveau = (niveau * 10) ** 2
    progression = int(((xp_actuel - xp_niveau) / max(xp_prochain - xp_niveau, 1)) * 10)
    barre = "█" * progression + "░" * (10 - progression)

    # Rôle le plus haut
    roles = [r for r in membre.roles if r.name != "@everyone"]
    role_top = roles[-1].mention if roles else "Aucun"

    em = discord.Embed(
        title=f"📊 Profil de {membre.display_name}",
        color=membre.color if membre.color.value != 0 else 0x5865F2
    )
    em.set_thumbnail(url=membre.display_avatar.url)

    em.add_field(name="💬 Messages envoyés", value=f"**{d['messages']}** messages", inline=True)
    em.add_field(name="⭐ Niveau XP", value=f"**Niveau {niveau}** ({xp_actuel} XP)", inline=True)
    em.add_field(name="🏆 Classement", value=f"**#{rang}** sur le serveur", inline=True)
    em.add_field(name="📈 Progression", value=f"`{barre}` vers niv.{niveau+1}", inline=False)
    em.add_field(name="📅 Sur le serveur depuis", value=f"**{jours} jours** et {heures}h\n({membre.joined_at.strftime('%d/%m/%Y')})", inline=True)
    em.add_field(name="🎂 Compte Discord créé", value=f"Il y a **{jours_discord} jours**\n({membre.created_at.strftime('%d/%m/%Y')})", inline=True)
    em.add_field(name="🎭 Rôle principal", value=role_top, inline=True)
    em.add_field(name="🆔 ID", value=f"`{membre.id}`", inline=True)

    statut = {
        discord.Status.online: "🟢 En ligne",
        discord.Status.idle: "🟡 Absent",
        discord.Status.dnd: "🔴 Ne pas déranger",
        discord.Status.offline: "⚫ Hors ligne"
    }
    em.add_field(name="📡 Statut", value=statut.get(membre.status, "⚫ Inconnu"), inline=True)
    em.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)

    await ctx.send(embed=em)

@bot.command()
async def serverstats(ctx):
    g = ctx.guild
    maintenant = datetime.datetime.now(datetime.timezone.utc)
    age_serveur = maintenant - g.created_at

    en_ligne = sum(1 for m in g.members if m.status != discord.Status.offline and not m.bot)
    bots = sum(1 for m in g.members if m.bot)
    humains = g.member_count - bots

    em = discord.Embed(title=f"📊 Statistiques de {g.name}", color=0x5865F2)
    em.set_thumbnail(url=g.icon.url if g.icon else "")

    em.add_field(name="👥 Membres total", value=f"**{g.member_count}**", inline=True)
    em.add_field(name="👤 Humains", value=f"**{humains}**", inline=True)
    em.add_field(name="🤖 Bots", value=f"**{bots}**", inline=True)
    em.add_field(name="🟢 En ligne maintenant", value=f"**{en_ligne}**", inline=True)
    em.add_field(name="📝 Salons texte", value=f"**{len(g.text_channels)}**", inline=True)
    em.add_field(name="🔊 Salons vocaux", value=f"**{len(g.voice_channels)}**", inline=True)
    em.add_field(name="🎭 Rôles", value=f"**{len(g.roles)}**", inline=True)
    em.add_field(name="😀 Emojis", value=f"**{len(g.emojis)}**", inline=True)
    em.add_field(name="🚀 Boosts", value=f"**{g.premium_subscription_count}** (Niveau {g.premium_tier})", inline=True)
    em.add_field(name="📅 Serveur créé", value=f"Il y a **{age_serveur.days} jours**\n({g.created_at.strftime('%d/%m/%Y')})", inline=False)
    em.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)

    await ctx.send(embed=em)

check_anniversaires.start()
bot.run(os.getenv("DISCORD_TOKEN"))
