import os
import json
from dotenv import load_dotenv
import discord
from discord.ext import commands
import yt_dlp
import asyncio
from discord.ext.commands import check, CheckFailure
from discord.utils import get


#모든 명령에 대해 실패 발생 시, 알려주는거 정의
def is_music_channel():
    def predicate(ctx):
        config = load_config()
        guild_id = str(ctx.guild.id)

        print(f"[DEBUG] Loaded config: {config}")
        print(f"[DEBUG] Guild ID: {guild_id}")
        print(f"[DEBUG] Channel ID: {ctx.channel.id}")
        print(f"[DEBUG] Allowed channel: {config.get(guild_id)}")
    
        if guild_id not in config:
            raise CheckFailure("⚠️ 먼저 '+setchannel` 명령어로 봇 명령 채널을 설정해주세요!")
        
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
            return json.load(f)  # ✅ 바로 JSON 파싱
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

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

#music queue
music_queue = []

#봇 접속시 뜨는 멘트
@bot.event
async def on_ready():
    print(f"{bot.user.name}이 서버에 들어왔습니다! ")

#에러 말하기
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("🚫 이 채널에선 음악 명령어를 사용할 수 없어요!\n지정된 음악 채널에서 사용해주세요.")

    else:
        await ctx.send("⚠️ 알 수 없는 명령어입니다")
        print(f"⚠️ 알 수 없는 에러 발생: {error}")

#혼자 남았을 때 나가기
async def on_voice_state_update(member, before, after):
    # 봇이 아니고, 음성 채널에서 나갔을 때
    if member.bot:
        return

    voice_client = discord.utils.get(bot.voice_clients, guild=member.guild)
    if voice_client is None or not voice_client.is_connected():
        return

    # 봇이 있는 음성 채널
    channel = voice_client.channel

    # 유저가 나간 후, 봇만 남았는지 확인
    if len([m for m in channel.members if not m.bot]) == 0:
        await asyncio.sleep(10)
        if len([m for m in channel.members if not m.bot]) == 0:
            await voice_client.disconnect()
            config = load_config()
            text_channel_id = config.get(str(member.guild.id))
            if text_channel_id:
                text_channel = bot.get_channel(text_channel_id)
                if text_channel:
                    await text_channel.send("👋 아무도 없어서 음성 채널을 떠났어요.")


#봇 명령 전용 채널 등록
@bot.command(name="setchannel")
@commands.has_permissions()
async def setchannel(ctx):
    config = load_config()
    guild_id = str(ctx.guild.id)
    
    if not isinstance(config, dict):
        config = []
        
    print("[DEBUG] BEFORE update:", config)

    config.update({guild_id: ctx.channel.id})
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
        "+play             ▶ [url 또는 노래 제목]을 붙여 노래 재생 \n"
        "+pause            ▶ 일시정지\n"
        "+resume           ▶ 일시정지 해제\n"

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
    global music_queue, current_song

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

        def after_playing(error):
            if error:
                print(f"🎵 재생 중 오류 발생: {error}")
            bot.loop.create_task(play_next(ctx))

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

        if not ctx.voice_client.is_playing():
            current_song = title
            ctx.voice_client.play(
                source,
                after = lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
            )
            await ctx.send(f"▶️ **{title}** 재생 중입니다!")
        
        else:
            music_queue.append(
                {"url": url, "title": title}
            )
            await ctx.send(f"➕ **{title}** 대기열에 추가됐어요!")

#play_next
async def play_next(ctx):
    global current_song
    if music_queue:
        next_song = music_queue.pop(0)
        current_song = next_song["title"]

        try:
            source = discord.FFmpegOpusAudio(
                next_song["url"],
                executable="/opt/homebrew/bin/ffmpeg",
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn"
            )

            vc = discord.utils.get(bot.voice_clients, guild=ctx.guild)
            if not vc or not vc.is_connected():
                await ctx.send("❌ 봇이 음성 채널에 연결되어 있지 않아요.")
                return

            try:
                vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))
                await ctx.send(f"▶️ **{current_song}** 재생 중입니다!")
            except Exception as e:
                print(f"오디오 재생 실패: {e}")
                await ctx.send("❌ 다음 곡 재생 중 오류가 발생했어요.")

        except Exception as e:
            print(f"FFmpeg 로딩 실패: {e}")
            await ctx.send("❌ 오디오 스트림을 불러오는 데 실패했어요.")
            current_song = None
    else:
        current_song = None


#queue
@bot.command(name="queue")
@is_music_channel()
async def queue_command(ctx):
    global current_song

    if not ctx.voice_client or not ctx.voice_client.is_connected():
        await ctx.send("❌ 봇이 음성 채널에 접속되어 있지 않아요.")
        return

    if not ctx.voice_client.is_playing() and not music_queue:
        await ctx.send("🎶 현재 재생 중인 곡이나 대기열이 없습니다.")
        return

    msg = "🎵 **현재 재생 중:**\n"
    if ctx.voice_client.is_playing():
        # 플레이 중인 곡 제목은 따로 저장(예: current_song)
        msg += f"▶️ {current_song}\n"
    else:
        msg += "▶️ 없음\n"

    if music_queue:
        msg += "\n📜 **대기열:**\n"
        for i, song in enumerate(music_queue[:10], start=1):
            msg += f"{i}. {song['title']}\n"
    else:
        msg += "\n📜 대기열이 비어 있어요."

    await ctx.send(msg)

#pause
@bot.command(name="pause")
@is_music_channel()
async def pause_command(ctx):
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ 먼저 음성 채널에 접속해주세요.")
        return

    if not ctx.voice_client or not ctx.voice_client.is_connected():
        await ctx.send("❌ 봇이 음성 채널에 연결되어 있지 않아요.")
        return

    if ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ 노래를 일시정지했어요!")
    else:
        await ctx.send("⚠️ 현재 재생 중인 노래가 없어요.")



#stop
@bot.command(name="stop")
@is_music_channel()
async def stop_command(ctx):
    global music_queue, current_song

    # 음성 채널에 접속하지 않은 경우
    if not ctx.voice_client or not ctx.voice_client.is_connected():
        await ctx.send("❌ 봇이 음성 채널에 연결되어 있지 않아요.")
        return

    # 재생 중이면 중지
    if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
        ctx.voice_client.stop()

    # 큐 비우기
    music_queue.clear()
    current_song = None

    # 채널 나가기
    await ctx.voice_client.disconnect()
    await ctx.send("⏹️ 재생을 중지하고 음성 채널에서 나갔어요.")

        
#resume
@bot.command(name="resume")
@is_music_channel()
async def resume_command(ctx):
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ 먼저 음성 채널에 접속해주세요.")
        return

    vc = get(bot.voice_clients, guild=ctx.guild)

    if not vc or not vc.is_connected():
        await ctx.send("❌ 봇이 음성 채널에 연결되어 있지 않아요.")
        return

    if vc.is_paused():
        vc.resume()
        await ctx.send("▶️ 재생을 다시 시작했어요!")
    elif vc.is_playing():
        await ctx.send("▶️ 이미 재생 중이에요!")
    else:
        await ctx.send("⚠️ 현재 재생 중인 노래가 없어요.")

#next_song
@bot.command(name="next")
@is_music_channel()
async def next_command(ctx):
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ 먼저 음성 채널에 접속해주세요.")
        return
    
    vc = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if not vc or not vc.is_connected():
        await ctx.send("❌ 봇이 음성 채널에 연결되어 있지 않아요.")
        return

    # ✅ 큐가 비어 있으면 재생 끊지 말고 메시지만
    if not music_queue:
        await ctx.send("📭 재생 목록에 다음 곡이 없어요!")
        return

    # ✅ 큐가 있다면 현재 곡 중지 → play_next 실행됨
    if vc.is_playing() or vc.is_paused():
        vc.stop()
        await ctx.send("⏭️ 다음 곡으로 넘어갈게요!")
    else:
        await ctx.send("⚠️ 현재 재생 중인 노래가 없어요.")

#previous_song(back)
#shuffle
#all_repeat
#one_repeat
#playlist
#emoji_control
#skip
#auto_leave
#delete_song
#delete_all





#봇 실행 함수. 항상 맨 밑에 들어가야함.
bot.run(TOKEN)