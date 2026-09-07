import os
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import discord
from discord import app_commands


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"OK"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def start_health_server():
    port = int(os.getenv("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


with open("blacklist.json", "r", encoding="utf-8") as f:
    BLACKLIST = json.load(f)


intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def extract_jars(text):
    jars = set()
    pattern = re.compile(
        r'([A-Za-z0-9._+()\- \[\]]+\.jar)\b',
        re.I
    )

    for match in pattern.finditer(text):
        jar = match.group(1).strip().strip("\"'`")
        jar = jar.lstrip("/\\")
        if len(jar) > 2:
            jars.add(jar)

    return sorted(jars, key=str.lower)


def scan_text(text):
    lines = text.splitlines()
    detections = []

    for rule in BLACKLIST:
        keys = [x.lower() for x in rule["names"]]
        matches = []

        for i, line in enumerate(lines):
            low = line.lower()

            if any(key in low for key in keys):
                matches.append((i + 1, line))

        if matches:
            detections.append((rule, matches))

    return lines, detections, extract_jars(text)


@tree.command(
    name="scan",
    description="Scan file Minecraft latest.log"
)
@app_commands.describe(
    log="Chọn file latest.log hoặc file log Minecraft"
)
async def scan(
    interaction: discord.Interaction,
    log: discord.Attachment
):
    await interaction.response.defer(ephemeral=True)

    filename = (log.filename or "").lower()

    if not filename.endswith((".log", ".txt")):
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
            f"**Số file .jar:** `{len(jars)}`\n"
            f"**Blacklist phát hiện:** `{len(detections)}`"
        ),
        color=discord.Color.from_rgb(255, 77, 179)
    )

    if detections:
        embed.add_field(
            name="🔴 CẢNH BÁO",
            value=(
                "Phát hiện mục cần kiểm tra trong log.\n"
                "Đây không phải bằng chứng tuyệt đối."
            ),
            inline=False
        )

        for rule, matches in detections[:8]:
            sample = "\n".join(
                f"`Line {ln}` {line[:180]}"
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
            value="Không tìm thấy tên nào trong blacklist.",
            inline=False
        )

    await interaction.followup.send(
        embed=embed,
        ephemeral=True
    )

    if jars:
        for i in range(0, len(jars), 25):
            part = jars[i:i + 25]

            body = "\n".join(
                f"• `{jar}`"
                for jar in part
            )

            await interaction.followup.send(
                f"📦 **Danh sách .jar:**\n{body}",
                ephemeral=True
            )
    else:
        await interaction.followup.send(
            "📦 Không tìm thấy file `.jar` trong log.",
            ephemeral=True
        )


@client.event
async def on_ready():
    await tree.sync()
    print(
        f"Logged in as {client.user} "
        f"(ID: {client.user.id})"
    )


token = os.getenv("DISCORD_TOKEN")

if not token:
    raise RuntimeError(
        "Thiếu biến môi trường DISCORD_TOKEN trên Render."
    )


threading.Thread(
    target=start_health_server,
    daemon=True
).start()

client.run(token)
