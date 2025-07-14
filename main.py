import os
import json
from dotenv import load_dotenv
import discord
from discord.ext import commands
import yt_dlp
import asyncio
from discord.ext.commands import check, CheckFailure


#모든 명령에 대해 실패 발생 시, 알려주는거 정의
def is_music_channel():
    def predicate(ctx):
        config = load_config()
        guild_id = str(ctx.guild.id)

        if guild_id not in config:
            raise CheckFailure("⚠️ 먼저 +setchannel` 명령어로 봇 명령 채널을 설정해주세요!")
        
        if ctx.channel.id != config[guild_id]:
            raise CheckFailure("🚫 이 채널은 음악봇 명령 채널이 아닙니다.")
        
        return True
    return check(predicate)

#봇 명령 채널 설정
CONFIG_FILE = "channel_config.json"

if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, 'w') as f:
        json.dump({}, f)

def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            content = f.read().strip()
            if not content:
                return{}
            return json.loads(content)
    except json.JSONDecodeError:
        return{}

#컨픽 저장
def save_config(data):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(data, f, indent=4)

#토큰 로딩
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

#디버깅용 토큰
print(TOKEN)

#명령 접두사
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="+", intents=intents, help_command=None)

#봇 접속시 뜨는 멘트
@bot.event
async def on_ready():
    print(f"{bot.user.name}이 서버에 들어왔습니다! ")


#봇 명령 전용 채널 등록
@bot.command()
@commands.has_permissions(administrator=True)
async def setchannel(ctx):
    config = load_config()
    guild_id = str(ctx.guild.id)

    config[guild_id] = ctx.channel.id
    save_config(config)

    await ctx.send(f"✅ 이 채널이 **봇 명령 채널**로 설정되었습니다.")
    print(f"config: {config}")
    print("JSON 저장 경로:", os.path.abspath(CONFIG_FILE))


#help
@bot.command(name = "help")
async def help_command(ctx):
    help_text = (
        "📌 **사용 가능한 명령어 목록**\n"
        "```\n"
        "+setchannel       ▶ 원하는 채널에서 입력 시, 해당 채널을 봇 명령 채널로 등록 (관리자 전용)\n"
        "+help             ▶ 명령어 목록 보기\n"
        # 이후 추가될 명령어도 여기에 계속 추가할 수 있어
        "```\n"
    )
    await ctx.send(help_text)

#manual join
@bot.command(name="join")
@is_music_channel()
async def join_command(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send(f"🔊 **{channel.name}** 채널에 접속했어요!")
    else:
        await ctx.send("❌ 먼저 음성 채널에 들어가주세요!")


#play 기능
@bot.command(name="play")
@is_music_channel()
async def play_command(ctx, *, search: str):
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ 먼저 음성 채널에 접속해주세요.")
        return
    
    voice_channel = ctx.author.voice.channel

    if ctx.voice_client is None:
        vc = await voice_channel.connect()
    else:
        vc = ctx.voice_client
        if vc.channel != voice_channel:
            await vc.move_to(voice_channel)

    ydl_option = {
        'format': "bestaudio/best",
        'noplaylist': True,
        'quiet': True,
        'default_search': 'ytsearch'
    }
    with yt_dlp.YoutubeDL(ydl_option) as ydl:
        try:
            info = ydl.extract_info(search, download=False)
            if 'entries' in info:
                info = info['entries'][0]

        except Exception as e:
            await ctx.send("❌ 유효한 URL 또는 검색어를 입력해주세요.")
            return
        
        url = info['url']
        title = info.get('title', 'Unknown title')

        try:
            source = await discord.FFmpegOpusAudio.from_probe(
                url,
                executable="/opt/homebrew/bin/ffmpeg",
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn"
                )
        
        except Exception as e:
            print("⚠️ FFmpeg probe 실패, fallback 중:", e)

            source = discord.FFmpegOpusAudio(url,
            executable="/opt/homebrew/bin/ffmpeg",
            before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            options="-vn"
            )

        ctx.voice_client.stop()
        ctx.voice_client.play(source)

        await ctx.send(f"▶️ **{title}** 재생 중입니다!")

#봇 실행 함수. 항상 맨 밑에 들어가야함.
bot.run(TOKEN)