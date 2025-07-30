import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
import json
from dotenv import load_dotenv
import discord
from discord.ext import commands
import yt_dlp
from discord.ext.commands import check, CheckFailure
from discord.utils import get
import random
from datetime import datetime
import re

executor = ThreadPoolExecutor(max_workers=5) # 워커 수는 필요에 따라 조절

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
intents.members = True
intents.voice_states = True
bot = commands.Bot(command_prefix="+", intents=intents, help_command=None)

#music queue
music_queue = []
current_song = None
repeat_mode = "off"

#반복 재생 전역 설정
repeat_mode = None

#봇이 음성방 나가면 반복 모드 Off 기타 다른 것도 가능
def reset_music_state():
    global repeat_mode
    repeat_mode = None
    current_song = None
    music_queue.clear()

#음악의 분, 초 표현
def format_duration(seconds):
    if seconds is None:
        return "N/A"
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    if hours > 0:
        return f"{int(hours):02}:{int(minutes):02}:{int(secs):02}"
    return f"{int(minutes):02}:{int(secs):02}"

# 사용 예:
reset_music_state()  # stop할 때, 혼자 남았을 때 등

#봇 접속시 뜨는 멘트
@bot.event
async def on_ready():
    print(f"{bot.user.name}이 서버에 들어왔습니다! ")

#에러 말하기
async def on_command_error(ctx, error):
    print(f"DEBUG: on_command_error 호출됨. 에러 타입: {type(error)}, 에러 내용: {error}") # <-- 이 줄이 보이나요?

    if isinstance(error, commands.CheckFailure):
        print("DEBUG: 에러가 CheckFailure 타입입니다. 디스코드 메시지 전송 시도...")
        try:
            await ctx.send("🚫 이 채널에선 음악 명령어를 사용할 수 없어요!\n지정된 음악 채널에서 사용해주세요.")
            print("DEBUG: Discord 채널로 CheckFailure 메시지 전송 완료 (또는 시도).")
        except Exception as send_error:
            print(f"ERROR: Discord 채널로 CheckFailure 메시지 전송 실패: {send_error}")
    else:
        print("DEBUG: 알 수 없는 에러 타입입니다.")
        try:
            await ctx.send("⚠️ 알 수 없는 명령어입니다")
            print("DEBUG: Discord 채널로 '알 수 없는 명령어' 메시지 전송 완료 (또는 시도).")
        except Exception as send_error:
            print(f"ERROR: Discord 채널로 메시지 전송 실패 (알 수 없는 명령어): {send_error}")
        print(f"⚠️ 알 수 없는 에러 발생: {error}")

#혼자 남았을 때 나가기
@bot.event
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
            reset_music_state()

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
        "\n" # 구분선
        "🎶 **음악 재생 및 관리**\n"
        "+join             ▶ 봇을 현재 음성 채널로 초대\n"
        "+play [url/제목]  ▶ 노래 재생 또는 대기열에 추가\n"
        "+pause            ▶ 현재 재생 중인 곡 일시정지\n"
        "+resume           ▶ 일시정지된 곡 재생 재개\n"
        "+stop             ▶ 현재 곡 재생 중지 및 음성 채널에서 봇 퇴장\n"
        "+next [skip]      ▶ 다음 곡 재생 (현재 곡 스킵)\n"
        "+queue [list]     ▶ 현재 재생 목록 및 대기열 확인\n"
        "+shuffle          ▶ 재생 대기열 섞기\n"
        "+repeat [one/all/off] ▶ 반복 모드 설정 (현재 곡, 전체 큐, 끄기)\n"
        "```\n" #구분선
        "ℹ️ **참고:** 모든 음악 명령어는 `+setchannel`로 지정된 채널에서만 작동합니다."
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


# #play 기능
# @bot.command(name="play")
# @is_music_channel()
# async def play_command(ctx, *, search: str):
#     global music_queue, current_song

#     if not ctx.author.voice or not ctx.author.voice.channel:
#         await ctx.send("❌ 먼저 음성 채널에 접속해주세요.")
#         return
    
#     voice_channel = ctx.author.voice.channel

#     if ctx.voice_client is None:
#         vc = await voice_channel.connect()
#     else:
#         vc = ctx.voice_client
#         if vc.channel != voice_channel:
#             await vc.move_to(voice_channel)
#     processing_message = await ctx.send("🔄 노래 정보를 가져오는 중이에요... 잠시만 기다려주세요! \n플레이리스트라면 오래 걸릴 수 있어요!")
#     ydl_option = {
#         'format': "bestaudio[ext=webm]+bestaudio[ext=mp4]/bestaudio/best",
#         #'noplaylist': True, # 플레이리스트 전체를 막으려면 이 주석을 해제
#         'quiet': True,
#         'default_search': 'ytsearch',
#         'extract_flat': 'in_playlist' # 플레이리스트의 경우 URL만 빠르게 추출
#     }
    
#     try:
#         loop = asyncio.get_event_loop()
#         with yt_dlp.YoutubeDL(ydl_option) as ydl:
#             info = await loop.run_in_executor(executor, lambda: ydl.extract_info(search, download=False))
            
#         entries_to_process = []

#         if 'entries' in info and info['entries']:
#             for entry_item in info['entries']:
#                 if entry_item.get('_type') == 'url':
#                     try:
#                         nested_info = await loop.run_in_executor(executor, lambda: ydl.extract_info(entry_item['url'], download=False))
#                         entries_to_process.append(nested_info)
#                     except Exception as nested_e:
#                         print(f"플레이리스트 항목 상세 정보 추출 실패: {entry_item.get('title', 'Unknown Title')} - {nested_e}")
#                         await processing_message.edit(content=f"⚠️ 플레이리스트 항목 '{entry_item.get('title', 'Unknown')}'을(를) 처리하지 못했습니다.") # 오류 발생 시 메시지 수정
#                         continue
#                 else: #그 외
#                     entries_to_process.append(entry_item)
#         elif 'url' in info:
#             entries_to_process.append(info)
#         else:
#             await processing_message.edit(content="❌ 검색 결과가 없습니다.") # 오류 발생 시 메시지 수정
#             return
        
#         if not entries_to_process:
#             await processing_message.edit(content="❌ 검색 결과가 없습니다.") # 오류 발생 시 메시지 수정
#             return

#     except Exception as e:
#         print(f"yt_dlp 예외: {e}")
#         await processing_message.edit(content="❌ 유효한 URL 또는 검색어를 입력해주세요. (YouTube에서 찾을 수 없거나 접근 문제)") # 오류 발생 시 메시지 수정
#         return
    
#     await processing_message.delete() # 모든 정보 추출 성공 시 메시지 삭제

#     newly_added_songs_titles = [] # 새로 추가될 곡들의 제목 리스트
#     total_songs_to_add = len(entries_to_process)
    

#     if total_songs_to_add > 1:
#         await ctx.send(f"📚 총 {total_songs_to_add}개의 곡이 대기열에 추가됩니다. 잠시만 기다려주세요!")

#     for i, entry in enumerate(entries_to_process):
#         url = entry.get("url")
#         title = entry.get('title', 'Unknown title')
#         duration = entry.get('duration')

#         if url is None:
#             await ctx.send(f"❌ '{title}'에 대한 스트림 URL을 찾을 수 없습니다. (yt_dlp URL 없음 오류)")
#             continue

#         song_info = {"title": title, "url": url, "duration": duration}

#         # 첫 번째 곡이고 봇이 현재 재생 중이거나 일시정지 상태가 아니라면 바로 재생
#         if i == 0 and not vc.is_playing() and not vc.is_paused() and current_song is None:
#             try:
#                 source = await discord.FFmpegOpusAudio.from_probe(
#                     url,
#                     executable="/opt/homebrew/bin/ffmpeg",
#                     before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 10 -timeout 5000000 -user_agent \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36\"",
#                     options="-vn"
#                 )
#             except Exception as e:
#                 print(f"FFmpeg probe 실패, fallback 중 (play_command 첫 곡): {e}")
#                 source = discord.FFmpegOpusAudio(
#                     url,
#                     executable="/opt/homebrew/bin/ffmpeg",
#                     before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 10 -timeout 5000000 -user_agent \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36\"",
#                     options="-vn"
#                 )

#             current_song = song_info
#             # after 콜백에서 play_next 호출 시 self가 없으므로 bot.loop를 명시
#             vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))
#             await ctx.send(f"▶️ **{title}** 재생 중입니다!")
#         else:
#             # 첫 곡이 아니거나 이미 재생 중인 경우 대기열에 추가
#             music_queue.append(song_info)
#             newly_added_songs_titles.append(title) # 추가된 곡 제목 리스트에 추가

#     # 모든 곡 추가 작업이 끝난 후 요약 메시지 (코드 블록 사용)
#     if len(newly_added_songs_titles) > 0:
#         if len(newly_added_songs_titles) == 1:
#             await ctx.send(f"➕ **{newly_added_songs_titles[0]}** 대기열에 추가됐어요!")
#         else:
#             display_limit = 10 # 코드 블록에 표시할 최대 곡 수
#             songs_to_display = newly_added_songs_titles[:display_limit]
            
#             formatted_list = "\n".join([f"{idx+1}. {title}" for idx, title in enumerate(songs_to_display)])

#             if len(newly_added_songs_titles) > display_limit:
#                 formatted_list += f"\n... 외 {len(newly_added_songs_titles) - display_limit}곡"
            
#             await ctx.send(
#                 f"📚 **총 {len(newly_added_songs_titles)}곡**이 대기열에 추가됐어요!\n"
#                 f"```\n{formatted_list}\n```" # 코드 블록으로 묶기
#             )
@bot.command(name="play")
@is_music_channel()
async def play_command(ctx, *, search: str):
    global music_queue, current_song

    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ 먼저 음성 채널에 접속해주세요.")
        return
    
    youtube_url_pattern = re.compile(
        r'^(https?://)?(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com)/.+$'
    )
    
    is_url = search.startswith('http://') or search.startswith('https://')

    if is_url and not youtube_url_pattern.match(search):
        await ctx.send("❌ 지원되지 않는 URL 형식이에요. YouTube 또는 YouTube Music 동영상/재생 목록 URL을 입력해주세요. 아니면 검색어를 입력해주세요.")
        return

    voice_channel = ctx.author.voice.channel

    if ctx.voice_client is None:
        vc = await voice_channel.connect()
    else:
        vc = ctx.voice_client
        if vc.channel != voice_channel:
            await vc.move_to(voice_channel)
    
    processing_message = await ctx.send("🔄 노래 정보를 가져오는 중이에요... 잠시만 기다려주세요! \n플레이리스트라면 오래 걸릴 수 있어요!")
    
    # yt_dlp 옵션 수정: thumbnail과 artist 정보도 가져오도록 설정
    ydl_option = {
        'format': "bestaudio[ext=webm]+bestaudio[ext=mp4]/bestaudio/best",
        'quiet': True,
        'default_search': 'ytsearch',
        'extract_flat': False,
        'force_generic_extractor': True,
        'cachedir': False,
        'no_warnings': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'opus',
            'preferredquality': '192',
        }],
        'writes_thumbnail': True, # 썸네일 정보 가져오기 활성화
        'writedescription': True, # 아티스트 정보 등을 위해 설명 가져오기 활성화
        'getcomments': False,
    }
    
    try:
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(ydl_option) as ydl:
            info = await loop.run_in_executor(executor, lambda: ydl.extract_info(search, download=False))
            
        entries_to_process = []

        if 'entries' in info and info['entries']:
            for entry_item in info['entries']:
                entries_to_process.append(entry_item)
        elif 'url' in info:
            entries_to_process.append(info)
        else:
            await processing_message.edit(content="❌ 검색 결과가 없습니다.")
            return
        
        if not entries_to_process:
            await processing_message.edit(content="❌ 검색 결과가 없습니다.")
            return

    except Exception as e:
        print(f"yt_dlp 예외: {e}")
        await processing_message.edit(content="❌ 노래 정보를 가져오는 데 문제가 발생했습니다. 유효한 YouTube 링크 또는 검색어를 다시 확인해주세요.")
        return
    
    await processing_message.delete()

    newly_added_songs_titles = []
    total_songs_to_add = len(entries_to_process)

    if total_songs_to_add > 1:
        await ctx.send(f"📚 총 {total_songs_to_add}개의 곡이 대기열에 추가됩니다. 잠시만 기다려주세요!")

    for i, entry in enumerate(entries_to_process):
        url = entry.get("url")
        title = entry.get('title', 'Unknown title')
        duration = entry.get('duration')
        thumbnail_url = entry.get('thumbnail') # 썸네일 URL
        artist = entry.get('artist') or entry.get('channel') or 'Unknown Artist'

        # --- 디버그를 위한 print 추가 ---
        print(f"DEBUG: Song Info for '{title}':")
        print(f"  URL: {url}")
        print(f"  Duration: {duration}")
        print(f"  Thumbnail URL: {thumbnail_url}") # <- 이 부분 확인!
        print(f"  Artist: {artist}")
        # --- 디버그 print 끝 ---

        if url is None:
            await ctx.send(f"❌ '{title}'에 대한 스트림 URL을 찾을 수 없습니다. (yt_dlp URL 없음 오류)")
            continue

        song_info = {
            "title": title,
            "url": url,
            "duration": duration,
            "thumbnail": thumbnail_url,
            "artist": artist
        }

        if i == 0 and not vc.is_playing() and not vc.is_paused() and current_song is None:
            try:
                ydl_opts_stream = {
                    'format': "bestaudio[ext=webm]+bestaudio[ext=mp4]/bestaudio/best",
                    'quiet': True,
                    'no_warnings': True,
                    'cachedir': False,
                }
                loop = asyncio.get_event_loop()
                with yt_dlp.YoutubeDL(ydl_opts_stream) as ydl_stream:
                    stream_info = await loop.run_in_executor(executor, lambda: ydl_stream.extract_info(url, download=False))
                    stream_url = stream_info.get('url')

                if not stream_url:
                    await ctx.send(f"❌ **{title}** 스트림을 가져올 수 없어 재생할 수 없습니다.")
                    print(f"DEBUG: 첫 곡 스트림 URL 없음 - {title}")
                    asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
                    return

                source = discord.FFmpegOpusAudio(
                    stream_url,
                    #executable="/opt/homebrew/bin/ffmpeg", 서버에 올리기 위해 경로 변결
                    executable="ffmpeg",
                    before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 10 -timeout 5000000 -user_agent \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36\"",
                    options="-vn"
                )

            except Exception as e:
                print(f"FFmpeg probe 실패, fallback 중 (play_command 첫 곡): {e}")
                await ctx.send(f"❌ **{title}** 재생 중 오류가 발생하여 건너뜁니다.")
                asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
                return

            current_song = song_info
            vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))
            
            embed = discord.Embed(
                title="현재 재생 중",
                description=f"**[{title}]({url})**",
                color=discord.Color.green()
            )
            
            if artist and artist != 'Unknown Artist':
                embed.add_field(name="아티스트", value=artist, inline=True)
            
            if duration:
                embed.add_field(name="재생 시간", value=format_duration(duration), inline=True)
            
            if thumbnail_url:
                embed.set_image(url=thumbnail_url) # 앨범 아트 (유튜브 썸네일)
            
            embed.set_footer(text=f"idiotbot | {datetime.now().strftime('%Y-%m-%d %H:%M')}", icon_url=bot.user.avatar.url)

            await ctx.send(embed=embed)
        else:
            music_queue.append(song_info)
            newly_added_songs_titles.append(title)

    if len(newly_added_songs_titles) > 0:
        if len(newly_added_songs_titles) == 1:
            await ctx.send(f"➕ **{newly_added_songs_titles[0]}** 대기열에 추가됐어요!")
        else:
            display_limit = 10
            songs_to_display = newly_added_songs_titles[:display_limit]
            
            formatted_list = "\n".join([f"{idx+1}. {title}" for idx, title in enumerate(songs_to_display)])

            if len(newly_added_songs_titles) > display_limit:
                formatted_list += f"\n... 외 {len(newly_added_songs_titles) - display_limit}곡"
            
            await ctx.send(
                f"📚 **총 {len(newly_added_songs_titles)}곡**이 대기열에 추가됐어요!\n"
                f"```\n{formatted_list}\n```"
            )

#play_next
# async def play_next(ctx):
#     global current_song, music_queue

#     if music_queue:
#         next_song = music_queue.pop(0)
#         current_song = next_song

#         try:
#             source = discord.FFmpegOpusAudio(
#                 next_song["url"],
#                 executable="/opt/homebrew/bin/ffmpeg",
#                 before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 10 -timeout 5000000 -user_agent \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36\"",
#                 options="-vn"
#             )

#             vc = discord.utils.get(bot.voice_clients, guild=ctx.guild)
#             if not vc or not vc.is_connected():
#                 await ctx.send("❌ 봇이 음성 채널에 연결되어 있지 않아요.")
#                 return

#             try:
#                 vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))
#                 await ctx.send(f"▶️ **{current_song['title']}** 재생 중입니다!")
#             except Exception as e:
#                 print(f"오디오 재생 실패: {e}")
#                 await ctx.send("❌ 다음 곡 재생 중 오류가 발생했어요.")

#         except Exception as e:
#             print(f"FFmpeg 로딩 실패: {e}")
#             await ctx.send("❌ 오디오 스트림을 불러오는 데 실패했어요.")
#             current_song = None
#     else:
#         current_song = None
#play_next 수정
async def play_next(ctx):
    global current_song, music_queue

    if music_queue:
        next_song = music_queue.pop(0)
        current_song = next_song

        vc = discord.utils.get(bot.voice_clients, guild=ctx.guild)
        if not vc or not vc.is_connected():
            await ctx.send("❌ 봇이 음성 채널에 연결되어 있지 않아요.")
            current_song = None
            return

        try:
            ydl_opts_stream = {
                'format': "bestaudio[ext=webm]+bestaudio[ext=mp4]/bestaudio/best",
                'quiet': True,
                'no_warnings': True,
                'cachedir': False,
                'extract_flat': False,
            }
            loop = asyncio.get_event_loop()
            with yt_dlp.YoutubeDL(ydl_opts_stream) as ydl:
                stream_info = await loop.run_in_executor(executor, lambda: ydl.extract_info(next_song["url"], download=False))
                stream_url = stream_info.get('url')

            if not stream_url:
                await ctx.send(f"❌ **{next_song['title']}** (URL 없음) 스트림을 가져올 수 없어 건너뜁니다.")
                print(f"DEBUG: 스트림 URL 없음 - {next_song['title']}")
                asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
                return

            source = discord.FFmpegOpusAudio(
                stream_url,
                #executable="/opt/homebrew/bin/ffmpeg", 호스팅을 위한 경로 변경
                executable="ffmpeg",
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 10 -timeout 5000000 -user_agent \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36\"",
                options="-vn"
            )

            try:
                vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))
                
                embed = discord.Embed(
                    title="다음 곡 재생 중",
                    description=f"**[{next_song['title']}]({next_song['url']})**",
                    color=discord.Color.blue()
                )
                if next_song.get('artist') and next_song.get('artist') != 'Unknown Artist':
                    embed.add_field(name="아티스트", value=next_song['artist'], inline=True)
                if next_song.get('duration'):
                    embed.add_field(name="재생 시간", value=format_duration(next_song['duration']), inline=True)
                
                thumbnail_url_next = next_song.get('thumbnail') # <- 썸네일 URL 가져오기
                # --- 디버그를 위한 print 추가 ---
                print(f"DEBUG: Play Next Song Info for '{next_song['title']}':")
                print(f"  Thumbnail URL: {thumbnail_url_next}") # <- 이 부분 확인!
                # --- 디버그 print 끝 ---

                if thumbnail_url_next: # <- 썸네일 URL이 있을 경우에만 설정
                    embed.set_image(url=thumbnail_url_next)
                
                embed.set_footer(text=f"idiotbot | {datetime.now().strftime('%Y-%m-%d %H:%M')}", icon_url=bot.user.avatar.url)
                
                await ctx.send(embed=embed)

            except Exception as e:
                print(f"오디오 재생 실패 (play_next): {e}")
                await ctx.send(f"❌ **{next_song['title']}** 재생 중 오류가 발생하여 건너뜁니다.")
                asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)

        except Exception as e:
            print(f"FFmpeg 로딩 실패 (play_next): {e}")
            await ctx.send(f"❌ **{next_song['title']}** 스트림을 불러오는 데 실패하여 건너뜁니다.")
            current_song = None
            asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
    else:
        current_song = None
        await ctx.send("🎶 대기열이 모두 비었습니다.")


#queue
@bot.command(name="queue", aliases=["list"])
@is_music_channel()
async def queue_command(ctx):
    global current_song, music_queue

    if not ctx.voice_client or not ctx.voice_client.is_connected():
        await ctx.send("❌ 봇이 음성 채널에 접속되어 있지 않아요.")
        return

    if not ctx.voice_client.is_playing() and not music_queue:
        await ctx.send("🎶 현재 재생 중인 곡이나 대기열이 없습니다.")
        return
    
    response_lines = []

    response_lines.append("🎵 **현재 재생 중:**")
    if current_song and ctx.voice_client.is_playing(): # current_song이 있고 재생 중일 때
        current_duration_formatted = format_duration(current_song.get('duration'))#노래 분, 초 가져오기
        response_lines.append(f"▶️ **{current_song['title']}** ({current_duration_formatted})")
    else:
        response_lines.append("▶️ 없음")

    # 대기열 표시
    if music_queue:
        response_lines.append("\n📜 **대기열:**")
        
        # 코드 블록에 표시할 최대 곡 수
        display_limit = 15
        songs_to_display = music_queue[:display_limit]
        
        # 대기열 목록을 줄바꿈으로 연결하여 코드 블록에 넣을 문자열 생성
        formatted_queue_list_items = []
        
        #최대길이
        max_title_length = 40

        max_idx_digits = len(str(display_limit))

        for idx, song in enumerate(songs_to_display):
            duration_formatted = format_duration(song.get('duration'))
            title = song['title']
            #노래 제목이 최대길이 넘으면 자르고 점 붙히기
            if len(title) > max_title_length:
                title = title[:max_title_length - 3] + "···"
            
            padded_idx_str = f"{idx+1:>{max_idx_digits}}"
            padded_title_str = f"{title:<{max_title_length}}"

            #조합
            formatted_queue_list_items.append(f"{padded_idx_str}. {padded_title_str} {duration_formatted}")

        # formatted_queue_list_items 리스트를 하나의 문자열로 합쳐서 formatted_queue_list에 저장
        formatted_queue_list = "\n".join(formatted_queue_list_items)
        
        # 코드 블록 시작
        response_lines.append("```")
        response_lines.append(formatted_queue_list)

        if len(music_queue) > display_limit:
            response_lines.append(f"... 외 {len(music_queue) - display_limit}곡")
        
        #코드 블록 끝
        response_lines.append("```")
    else:
        response_lines.append("\n📜 대기열이 비어 있어요.")

    #합쳐서 메시지 전송
    await ctx.send("\n".join(response_lines))


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
    reset_music_state()
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
@bot.command(name="next", aliases=["skip"])
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


#previous_song(back) -> 나중에 할 것 복잡함


#shuffle
@bot.command(name="shuffle")
@is_music_channel()
async def shuffle_command(ctx):
    global music_queue

    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ 먼저 음성 채널에 접속해주세요.")
        return

    if len(music_queue)<= 1:
        await ctx.send("⚠️ 셔플할 대기열이 충분하지 않아요.")
        return
    
    random.shuffle(music_queue)

    await ctx.send("🔀 재생 대기열이 셔플됐어요!")
    await queue_command(ctx) #셔플 후 큐 부르기

#repeat
@bot.command(name="repeat")
@is_music_channel()
async def repeat_mode_toggle(ctx, mode: str = None):
    global repeat_mode

    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ 먼저 음성 채널에 접속해주세요.")
        return

    if mode == "one":
        repeat_mode = "one"
        await ctx.send("🔁 현재 곡 반복 모드로 설정됐어요!")
    elif mode == "all":
        repeat_mode = "all"
        await ctx.send("🔂 전체 큐 반복 모드로 설정됐어요!")
    elif mode == "off":
        repeat_mode = None
        await ctx.send("⏹️ 반복 모드를 끄겠습니다.")
    else:
        await ctx.send("❓ 사용법: `+repeat one`, `+repeat all`, `+repeat off`")



#emoji_control
#auto_leave
#delete_song
#delete_all





#봇 실행 함수. 항상 맨 밑에 들어가야함.
bot.run(TOKEN)