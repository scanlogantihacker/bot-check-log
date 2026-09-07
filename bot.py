import io
import json
import os
import re
import discord
from discord import app_commands

with open("blacklist.json", "r", encoding="utf-8") as f:
    BLACKLIST = json.load(f)

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

def extract_jars(text: str):
    jars = set()
    # Finds filenames ending in .jar, including common spaces, brackets and version chars.
    pattern = re.compile(r'([A-Za-z0-9._+()\- \[\]]+\.jar)\b', re.I)
    for match in pattern.finditer(text):
        jar = match.group(1).strip().strip("\"'`")
        jar = jar.lstrip("/\\")
        if len(jar) > 2:
            jars.add(jar)
    return sorted(jars, key=str.lower)

def scan_text(text: str):
    lines = text.splitlines()
    detections = []
    lowered = [line.lower() for line in lines]

    for rule in BLACKLIST:
        keys = [x.lower() for x in rule["names"]]
        matches = []
        for i, line in enumerate(lowered):
            if any(key in line for key in keys):
                matches.append((i + 1, lines[i]))
        if matches:
            detections.append((rule, matches))

    return lines, detections, extract_jars(text)

def chunks(items, size=20):
    for i in range(0, len(items), size):
        yield items[i:i+size]

@tree.command(name="scan", description="Scan a Minecraft latest.log file")
@app_commands.describe(log="Chọn file latest.log hoặc file log Minecraft")
async def scan(interaction: discord.Interaction, log: discord.Attachment):
    await interaction.response.defer(ephemeral=True)

    name = (log.filename or "").lower()
    if not name.endswith((".log", ".txt")):
        await interaction.followup.send("❌ Hãy chọn file `.log` hoặc `.txt`.", ephemeral=True)
        return

    # Discord attachment size is limited by Discord/server settings.
    try:
        data = await log.read()
        text = data.decode("utf-8", errors="replace")
    except Exception as exc:
        await interaction.followup.send(f"❌ Không đọc được file: `{exc}`", ephemeral=True)
        return

    lines, detections, jars = scan_text(text)

    embed = discord.Embed(
        title="💗 Minecraft Log Scanner",
        description=f"**File:** `{log.filename}`\n**Số dòng:** `{len(lines)}`\n**File .jar tìm thấy:** `{len(jars)}`\n**Mục blacklist:** `{len(detections)}`",
        color=discord.Color.from_rgb(255, 77, 179)
    )

    if detections:
        embed.add_field(
            name="🔴 CẢNH BÁO",
            value="Phát hiện mục cần kiểm tra trong log. Đây **không phải bằng chứng tuyệt đối** vì log có thể chứa tên mod/client từ nhiều nguồn khác nhau.",
            inline=False
        )
        for rule, matches in detections[:8]:
            sample = "\n".join(
                f"`Line {ln}` {discord.utils.escape_markdown(line[:180])}"
                for ln, line in matches[:3]
            )
            value = f"**Loại:** {rule['type']}\n**Số lần:** {len(matches)}\n{sample}"
            if len(value) > 1000:
                value = value[:997] + "..."
            embed.add_field(name=f"🔴 {rule['name']}", value=value, inline=False)
    else:
        embed.add_field(
            name="🟢 Không phát hiện blacklist",
            value="Không tìm thấy tên nào trong danh sách blacklist hiện tại.",
            inline=False
        )

    await interaction.followup.send(embed=embed, ephemeral=True)

    # Send the complete JAR list as follow-up messages, only to the requester.
    if jars:
        for part in chunks(jars, 25):
            body = "\n".join(f"• `{j}`" for j in part)
            msg = f"📦 **Danh sách .jar ({len(jars)} tổng):**\n{body}"
            if len(msg) > 1900:
                # Extra-safe fallback for unusually long names.
                msg = msg[:1890] + "\n…"
            await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.followup.send(
            "📦 Không tìm thấy tên file `.jar` trong nội dung log.",
            ephemeral=True
        )

@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user} (ID: {client.user.id})")

token = os.getenv("DISCORD_TOKEN")
if not token:
    raise RuntimeError("Thiếu biến môi trường DISCORD_TOKEN.")
client.run(token)
