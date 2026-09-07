import io
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import discord
from discord import app_commands


# ---------- Render health server ----------
# Render Web Services require the process to listen on 0.0.0.0:$PORT.
# This tiny server exists only for Render health checks / wake-up requests.
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            body = b"OK"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            body = b"Not Found"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, format, *args):
        # Keep Render logs clean.
        return


def start_health_server():
    port = int(os.getenv("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"Render health server listening on 0.0.0.0:{port}")
    server.serve_forever()


# ---------- Load blacklist ----------
with open("blacklist.json", "r", encoding="utf-8") as f:
    BLACKLIST = json.load(f)


# ---------- Discord client ----------
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def extract_jars(text: str):
    jars = set()
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
        yield items[i:i + size]


@tree.command(name="scan", description="Scan a Minecraft latest.log file")
@app_commands.describe(log="Chọn file latest.log hoặc file log Minecraft")
async def scan(interaction: discord.Interaction, log: discord.Attachment):
    await interaction.response.defer(ephemeral=True)

    name = (log.filename or "").lower()

    if not name.endswith((".log", ".txt")):
        await interaction.followup.send(
            "❌ Hãy chọn file `.log` hoặc `.txt`.",
            ephemeral=True
        )
        return

    try:
        data = await log.read()
        text = data.decode("utf-8", errors="replace")
    except Exception as exc:
        await interaction.followup.send(
            f"❌ Không đọc được file: `{exc}`",
            ephemeral=True
        )
        return

    lines, detections, jars = scan_text(text)

    embed = discord.Embed(
        title="💗 Minecraft Log Scanner",
        description=(
            f"**File:** `{log.filename}`\n"
            f"**Số dòng:** `{len(lines)}`\n"
            f"**File .jar tìm thấy:** `{len(jars)}`\n"
            f"**Mục blacklist:** `{len(detections)}`"
        ),
        color=discord.Color.from_rgb(255, 77, 179)
    )

    if detections:
        embed.add_field(
            name="🔴 CẢNH BÁO",
            value=(
                "Phát hiện mục cần kiểm tra trong log. Đây **không phải bằng "
                "chứng tuyệt đối** vì log có thể chứa tên mod/client từ nhiều nguồn khác nhau."
            ),
            inline=False
        )

        for rule, matches in detections[:8]:
            sample = "\n".join(
                f"`Line {ln}` {discord.utils.escape_markdown(line[:180])}"
                for ln, line in matches[:3]
            )

            value = (
                f"**Loại:** {rule['type']}\n"
                f"**Số lần:** {len(matches)}\n"
                f"{sample}"
            )

            if len(value) > 1000:
                value = value[:997] + "..."

            embed.add_field(
                name=f"🔴 {rule['name']}",
                value=value,
                inline=False
            )
    else:
        embed.add_field(
            name="🟢 Không phát hiện blacklist",
            value="Không tìm thấy tên nào trong danh sách blacklist hiện tại.",
            inline=False
        )

    await interaction.followup.send(embed=embed, ephemeral=True)

    # Send the complete JAR list only to the requester.
    if jars:
        for part in chunks(jars, 25):
            body = "\n".join(f"• `{j}`" for j in part)
            msg = f"📦 **Danh sách .jar ({len(jars)} tổng):**\n{body}"

            if len(msg) > 1900:
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


# ---------- Start ----------
token = os.getenv("DISCORD_TOKEN")
if not token:
    raise RuntimeError("Thiếu biến môi trường DISCORD_TOKEN trên Render.")

# Start Render's required HTTP listener in the background.
threading.Thread(target=start_health_server, daemon=True).start()

# Start the Discord bot.
client.run(token)
