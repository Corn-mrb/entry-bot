import discord
from discord.ext import commands
from discord import app_commands
import random
import os
from datetime import datetime
from io import BytesIO
import qrcode

from config import (
    DISCORD_TOKEN, DISCORD_GUILD_ID,
    ALLOWED_ROLE_IDS, ADMIN_ROLE_IDS, DEVELOPER_USER_ID, KST
)
from database import (
    get_stores, get_store, create_store, update_store, delete_store,
    get_store_visits, get_user_all_visits, get_user_visit_count,
    reset_today_checkin, delete_user_visits, get_store_stats,
    get_all_visits_for_export, add_visit, save_stores, _now_kst
)

# ----------------------------
# 봇 설정
# ----------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ----------------------------
# 권한 확인 함수
# ----------------------------
def has_allowed_role(interaction: discord.Interaction) -> bool:
    """매장 관리 권한 확인"""
    if not ALLOWED_ROLE_IDS:
        return True
    user_role_ids = [role.id for role in interaction.user.roles]
    return any(rid in user_role_ids for rid in ALLOWED_ROLE_IDS)

def is_admin_or_developer(interaction: discord.Interaction) -> bool:
    """관리자 또는 개발자 권한 확인"""
    if interaction.user.id == DEVELOPER_USER_ID:
        return True
    if ADMIN_ROLE_IDS:
        user_role_ids = [role.id for role in interaction.user.roles]
        if any(rid in user_role_ids for rid in ADMIN_ROLE_IDS):
            return True
    if interaction.user.guild_permissions.administrator:
        return True
    return False

def is_admin_or_helper(interaction: discord.Interaction) -> bool:
    """관리자 또는 Helper 권한 확인"""
    if is_admin_or_developer(interaction):
        return True
    return has_allowed_role(interaction)

# ----------------------------
# QR 코드 생성 함수
# ----------------------------
def generate_qr_image(url: str) -> BytesIO:
    """QR 코드 이미지 생성"""
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ----------------------------
# 체크인 Modal (암구호 입력)
# ----------------------------
class CheckinModal(discord.ui.Modal, title="체크인"):
    passphrase = discord.ui.TextInput(
        label="암구호",
        placeholder="암구호를 입력하세요",
        required=True,
        max_length=100
    )

    def __init__(self, store_code: str, store: dict):
        super().__init__()
        self.store_code = store_code
        self.store = store

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        member = interaction.user
        guild = interaction.guild

        # 역할 검증 (최소역할이 설정된 경우)
        min_role_id = self.store.get("min_role_id")
        if min_role_id:
            min_role = guild.get_role(min_role_id)
            if min_role:
                has_role = any(role >= min_role for role in member.roles)
                if not has_role:
                    # 채널에 입장 실패 알림
                    channel_id = self.store.get("channel_id")
                    if channel_id and guild:
                        try:
                            channel = guild.get_channel(channel_id)
                            if channel:
                                now = _now_kst()
                                role_names = [r.name for r in member.roles if r.name != "@everyone"]

                                embed = discord.Embed(
                                    title=f"⚠️ [입장 실패] {member.display_name}님이 입장 시도",
                                    color=discord.Color.orange(),
                                    description="**실패 사유**: 입장 권한 부족 (최소 역할 미달)"
                                )
                                embed.add_field(name="장소", value=self.store["store_name"], inline=True)
                                embed.add_field(name="시도자", value=f"<@{member.id}>", inline=True)
                                embed.add_field(name="시도 시간", value=now.strftime('%H:%M') + " (KST)", inline=True)
                                embed.add_field(name="필요 역할", value=min_role.name, inline=True)
                                embed.add_field(name="현재 역할", value=", ".join(role_names) if role_names else "(없음)", inline=False)

                                await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
                        except:
                            pass

                    await interaction.followup.send("❌ 입장 권한이 없습니다.", ephemeral=True)
                    return

        # 암구호 검증
        if self.passphrase.value != self.store.get("passphrase"):
            # 채널에 실패 알림
            channel_id = self.store.get("channel_id")
            if channel_id and guild:
                try:
                    channel = guild.get_channel(channel_id)
                    if channel:
                        now = _now_kst()
                        role_names = [r.name for r in member.roles if r.name != "@everyone"]

                        embed = discord.Embed(
                            title=f"⚠️ [입장 실패] {member.display_name}님이 입장 시도",
                            color=discord.Color.red(),
                            description="**실패 사유**: 암구호 불일치"
                        )
                        embed.add_field(name="장소", value=self.store["store_name"], inline=True)
                        embed.add_field(name="시도자", value=f"<@{member.id}>", inline=True)
                        embed.add_field(name="시도 시간", value=now.strftime('%H:%M') + " (KST)", inline=True)
                        embed.add_field(name="입력한 암구호", value=f"`{self.passphrase.value}`", inline=True)
                        embed.add_field(name="역할", value=", ".join(role_names) if role_names else "(없음)", inline=False)

                        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
                except:
                    pass

            await interaction.followup.send("❌ 암구호가 일치하지 않습니다.", ephemeral=True)
            return

        # 체크인 처리
        await process_checkin_deferred(interaction, self.store_code, self.store)


# ----------------------------
# 체크인 처리 함수 (deferred용 - followup 사용)
# ----------------------------
async def process_checkin_deferred(interaction: discord.Interaction, store_code: str, store: dict):
    """체크인 처리 (defer 후 호출)"""
    member = interaction.user
    guild = interaction.guild

    # 방문 기록 추가 (중복 체크)
    is_new_visit = add_visit(store_code, member.id, member.name, member.display_name)

    if not is_new_visit:
        await interaction.followup.send("✅ 이미 오늘 체크인했습니다. (하루 1회)", ephemeral=True)
        return

    # 방문 횟수
    visit_count = get_user_visit_count(store_code, member.id)

    # 역할 부여 (설정된 경우)
    role_granted = False
    grant_role_id = store.get("grant_role_id")
    if grant_role_id and guild:
        grant_role = guild.get_role(grant_role_id)
        if grant_role and grant_role not in member.roles:
            try:
                await member.add_roles(grant_role)
                role_granted = True
            except:
                pass

    # 역할 목록
    role_names = [r.name for r in member.roles if r.name != "@everyone"]

    # 채널에 알림 (성공)
    channel_id = store.get("channel_id")
    if channel_id and guild:
        try:
            channel = guild.get_channel(channel_id)
            if channel:
                now = _now_kst()
                label = "오늘 첫 방문" if visit_count == 1 else f"누적 {visit_count}회차"

                embed = discord.Embed(
                    title=f"✅ [입장 성공] {member.display_name}님이 체크인! ({label})",
                    color=discord.Color.green()
                )
                embed.add_field(name="장소", value=store["store_name"], inline=True)
                embed.add_field(name="방문자", value=f"<@{member.id}>", inline=True)
                embed.add_field(name="방문 시간", value=now.strftime('%H:%M') + " (KST)", inline=True)
                embed.add_field(name="방문 횟수", value=f"{visit_count}번째 방문", inline=True)
                embed.add_field(name="역할", value=", ".join(role_names) if role_names else "(없음)", inline=False)

                if role_granted:
                    embed.add_field(name="역할 부여", value="✅ 부여됨", inline=True)

                await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except:
            pass

    # 성공 메시지
    msg = f"✅ **{store['store_name']}** 체크인 완료!\n누적 **{visit_count}번째** 방문입니다!"
    if role_granted:
        msg += "\n🎖️ 역할이 부여되었습니다!"

    await interaction.followup.send(msg, ephemeral=True)

# ----------------------------
# Persistent View 등록
# ----------------------------
class PersistentCheckinView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="체크인", style=discord.ButtonStyle.green, emoji="✅", custom_id="persistent_checkin")
    async def checkin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 메시지 ID로 매장 찾기 (같은 채널에 여러 매장 가능)
        message_id = interaction.message.id
        stores = get_stores()

        store_code = None
        store = None
        for code, s in stores.items():
            if s.get("message_id") == message_id:
                store_code = code
                store = s
                break

        if not store:
            await interaction.response.send_message("❌ 등록되지 않은 매장입니다.", ephemeral=True)
            return

        # 암구호가 설정된 경우 Modal 표시 (먼저 처리)
        if store.get("passphrase"):
            modal = CheckinModal(store_code, store)
            await interaction.response.send_modal(modal)
            return

        # 암구호 없으면 바로 체크인 처리
        await interaction.response.defer(ephemeral=True)

        member = interaction.user
        guild = interaction.guild

        # 역할 검증
        min_role_id = store.get("min_role_id")
        if min_role_id:
            min_role = guild.get_role(min_role_id)
            if min_role:
                has_role = any(role >= min_role for role in member.roles)
                if not has_role:
                    # 채널에 입장 실패 알림
                    channel_id = store.get("channel_id")
                    if channel_id and guild:
                        try:
                            channel = guild.get_channel(channel_id)
                            if channel:
                                now = _now_kst()
                                role_names = [r.name for r in member.roles if r.name != "@everyone"]

                                embed = discord.Embed(
                                    title=f"⚠️ [입장 실패] {member.display_name}님이 입장 시도",
                                    color=discord.Color.orange(),
                                    description="**실패 사유**: 입장 권한 부족 (최소 역할 미달)"
                                )
                                embed.add_field(name="장소", value=store["store_name"], inline=True)
                                embed.add_field(name="시도자", value=f"<@{member.id}>", inline=True)
                                embed.add_field(name="시도 시간", value=now.strftime('%H:%M') + " (KST)", inline=True)
                                embed.add_field(name="필요 역할", value=min_role.name, inline=True)
                                embed.add_field(name="현재 역할", value=", ".join(role_names) if role_names else "(없음)", inline=False)

                                await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
                        except:
                            pass

                    await interaction.followup.send("❌ 입장 권한이 없습니다.", ephemeral=True)
                    return

        await process_checkin_deferred(interaction, store_code, store)

# ----------------------------
# 봇 이벤트
# ----------------------------
@bot.event
async def on_ready():
    # Persistent View 등록
    bot.add_view(PersistentCheckinView())

    guild = discord.Object(id=DISCORD_GUILD_ID)

    # 디버그: sync 전 명령어 수
    global_commands = bot.tree.get_commands()  # 글로벌 명령어
    print(f'[DEBUG] 글로벌 명령어 수: {len(global_commands)}')
    for cmd in global_commands:
        print(f'  - {cmd.name}')

    try:
        # 글로벌 명령어를 Guild에 복사
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f'[DEBUG] Sync 완료! {len(synced)}개 명령어 동기화됨')
        for cmd in synced:
            print(f'  - /{cmd.name}')
    except Exception as e:
        print(f'[ERROR] Sync 실패: {e}')

    print(f'✅ {bot.user} 봇이 준비되었습니다!')
    print(f'서버 수: {len(bot.guilds)}')
    print(f'로드된 매장 수: {len(get_stores())}')

# ----------------------------
# 매장 등록 (현재 채널에 체크인 버튼 생성)
# ----------------------------
@bot.tree.command(name="매장등록", description="매장 체크인 버튼 생성 및 QR 코드 발급")
@app_commands.describe(
    매장명="매장 또는 이벤트 이름",
    체크인채널="체크인 버튼을 표시할 채널 (미지정시 현재 채널)",
    최소역할="입장 가능한 최소 역할 (선택사항)",
    부여역할="입장 승인 시 자동 부여할 역할 (선택사항)",
    암구호="오늘의 암구호 (선택사항)"
)
async def cmd_create_store(
    interaction: discord.Interaction,
    매장명: str,
    체크인채널: discord.TextChannel = None,
    최소역할: discord.Role = None,
    부여역할: discord.Role = None,
    암구호: str = None
):
    if not has_allowed_role(interaction):
        await interaction.response.send_message("❌ 권한이 없습니다.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild
    channel = 체크인채널 or interaction.channel  # 지정된 채널 또는 현재 채널

    # 매장 코드 생성 (숫자 2자리)
    stores = get_stores()
    while True:
        store_code = f"{random.randint(10, 99)}"
        if store_code not in stores:
            break

    # 체크인 Embed 생성
    embed = discord.Embed(
        title=f"🏪 {매장명}",
        description="아래 버튼을 눌러 체크인하세요!",
        color=discord.Color.blue()
    )
    embed.add_field(name="매장 코드", value=f"`{store_code}`", inline=True)

    if 최소역할:
        embed.add_field(name="최소 역할", value=최소역할.mention, inline=True)

    if 암구호:
        embed.add_field(name="암구호", value="✅ 필요", inline=True)
    else:
        embed.add_field(name="암구호", value="❌ 불필요", inline=True)

    embed.set_footer(text="체크인은 하루 1회만 가능합니다.")

    # 체크인 버튼과 함께 메시지 전송 (멘션 알림 없이)
    view = PersistentCheckinView()
    checkin_msg = await channel.send(
        embed=embed,
        view=view,
        allowed_mentions=discord.AllowedMentions.none()
    )

    # QR 코드 생성 (Discord 채널 URL)
    channel_url = f"https://discord.com/channels/{guild.id}/{channel.id}"
    qr_buf = generate_qr_image(channel_url)
    qr_file = discord.File(qr_buf, filename=f"qr_{store_code}.png")

    # 매장 저장
    create_store(store_code, {
        "store_name": 매장명,
        "min_role_id": 최소역할.id if 최소역할 else None,
        "grant_role_id": 부여역할.id if 부여역할 else None,
        "passphrase": 암구호,
        "owner_id": interaction.user.id,
        "guild_id": guild.id,
        "channel_id": channel.id,
        "message_id": checkin_msg.id,
        "created_at": _now_kst().isoformat()
    })

    # 결과 Embed
    result_embed = discord.Embed(
        title=f"✅ {매장명} - 매장 등록 완료",
        color=discord.Color.green()
    )
    result_embed.add_field(name="매장 코드", value=f"**`{store_code}`**", inline=True)
    result_embed.add_field(name="체크인 채널", value=channel.mention, inline=True)
    result_embed.add_field(name="채널 URL", value=channel_url, inline=False)

    if 최소역할:
        result_embed.add_field(name="최소 역할", value=최소역할.mention, inline=True)

    if 부여역할:
        result_embed.add_field(name="부여 역할", value=부여역할.mention, inline=True)

    result_embed.add_field(name="암구호", value="✅ 설정됨" if 암구호 else "❌ 없음", inline=True)
    result_embed.set_image(url=f"attachment://qr_{store_code}.png")
    result_embed.set_footer(text="QR 코드를 스캔하면 체크인 채널로 이동합니다.")

    await interaction.followup.send(embed=result_embed, file=qr_file, ephemeral=True)

# ----------------------------
# 매장 수정
# ----------------------------
@bot.tree.command(name="매장수정", description="매장 정보 수정")
@app_commands.describe(
    매장코드="수정할 매장의 코드",
    매장명="새 매장명 (선택사항)",
    최소역할="새 최소 역할 (선택사항)",
    부여역할="새 부여 역할 (선택사항)",
    암구호="새 암구호 (선택사항, '없음' 입력시 제거)"
)
async def cmd_update_store(
    interaction: discord.Interaction,
    매장코드: str,
    매장명: str = None,
    최소역할: discord.Role = None,
    부여역할: discord.Role = None,
    암구호: str = None
):
    if not has_allowed_role(interaction):
        await interaction.response.send_message("❌ 권한이 없습니다.", ephemeral=True)
        return

    store = get_store(매장코드)
    if not store:
        await interaction.response.send_message("❌ 존재하지 않는 매장 코드입니다.", ephemeral=True)
        return

    if store['owner_id'] != interaction.user.id and not is_admin_or_developer(interaction):
        await interaction.response.send_message("❌ 본인이 생성한 매장만 수정할 수 있습니다.", ephemeral=True)
        return

    changes = {}
    change_list = []

    if 매장명:
        changes['store_name'] = 매장명
        change_list.append(f"매장명: {매장명}")

    if 최소역할:
        changes['min_role_id'] = 최소역할.id
        change_list.append(f"최소역할: {최소역할.mention}")

    if 부여역할:
        changes['grant_role_id'] = 부여역할.id
        change_list.append(f"부여역할: {부여역할.mention}")

    if 암구호 is not None:
        if 암구호.lower() in ["없음", "제거", "삭제", ""]:
            changes['passphrase'] = None
            change_list.append("암구호: 제거됨")
        else:
            changes['passphrase'] = 암구호
            change_list.append("암구호: 변경됨")

    if not change_list:
        await interaction.response.send_message("❌ 변경할 내용이 없습니다.", ephemeral=True)
        return

    changes['updated_at'] = _now_kst().isoformat()
    update_store(매장코드, changes)

    # 채널의 Embed도 업데이트
    guild = interaction.guild
    channel_id = store.get("channel_id")
    message_id = store.get("message_id")

    if channel_id and message_id:
        try:
            channel = guild.get_channel(channel_id)
            if channel:
                msg = await channel.fetch_message(message_id)
                updated_store = get_store(매장코드)

                embed = discord.Embed(
                    title=f"🏪 {updated_store['store_name']}",
                    description="아래 버튼을 눌러 체크인하세요!",
                    color=discord.Color.blue()
                )
                embed.add_field(name="매장 코드", value=f"`{매장코드}`", inline=True)

                min_role_id = updated_store.get("min_role_id")
                if min_role_id:
                    min_role = guild.get_role(min_role_id)
                    embed.add_field(name="최소 역할", value=min_role.mention if min_role else "삭제된 역할", inline=True)

                if updated_store.get("passphrase"):
                    embed.add_field(name="암구호", value="✅ 필요", inline=True)
                else:
                    embed.add_field(name="암구호", value="❌ 불필요", inline=True)

                embed.set_footer(text="체크인은 하루 1회만 가능합니다.")

                await msg.edit(embed=embed)
        except:
            pass

    embed = discord.Embed(
        title="✅ 매장 정보 수정 완료",
        description=f"**매장**: {store['store_name']}\n**코드**: `{매장코드}`",
        color=discord.Color.green()
    )
    embed.add_field(name="변경사항", value="\n".join(change_list), inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

# ----------------------------
# 매장 삭제
# ----------------------------
@bot.tree.command(name="매장삭제", description="매장 삭제")
@app_commands.describe(매장코드="삭제할 매장의 코드")
async def cmd_delete_store(interaction: discord.Interaction, 매장코드: str):
    if not has_allowed_role(interaction):
        await interaction.response.send_message("❌ 권한이 없습니다.", ephemeral=True)
        return

    store = get_store(매장코드)
    if not store:
        await interaction.response.send_message("❌ 존재하지 않는 매장 코드입니다.", ephemeral=True)
        return

    if store['owner_id'] != interaction.user.id and not is_admin_or_developer(interaction):
        await interaction.response.send_message("❌ 본인이 생성한 매장만 삭제할 수 있습니다.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    store_name = store['store_name']

    # 체크인 메시지 삭제
    channel_id = store.get("channel_id")
    message_id = store.get("message_id")
    if channel_id and message_id:
        try:
            channel = interaction.guild.get_channel(channel_id)
            if channel:
                msg = await channel.fetch_message(message_id)
                await msg.delete()
        except:
            pass

    delete_store(매장코드)

    await interaction.followup.send(f"✅ '{store_name}' 매장이 삭제되었습니다.", ephemeral=True)

# ----------------------------
# 매장 목록
# ----------------------------
@bot.tree.command(name="매장목록", description="내가 생성한 매장 목록 보기")
async def cmd_list_stores(interaction: discord.Interaction):
    if not has_allowed_role(interaction):
        await interaction.response.send_message("❌ 권한이 없습니다.", ephemeral=True)
        return

    stores = get_stores()
    my_stores = {k: v for k, v in stores.items() if v['owner_id'] == interaction.user.id}

    if not my_stores:
        await interaction.response.send_message("생성한 매장이 없습니다.", ephemeral=True)
        return

    embed = discord.Embed(title="📋 내 매장 목록", color=discord.Color.blue())

    for code, store in my_stores.items():
        guild = bot.get_guild(store['guild_id'])
        min_role = guild.get_role(store['min_role_id']) if guild and store.get('min_role_id') else None
        channel = guild.get_channel(store['channel_id']) if guild and store.get('channel_id') else None

        value = f"**코드**: `{code}`\n"
        value += f"**채널**: {channel.mention if channel else '없음'}\n"
        value += f"**최소역할**: {min_role.name if min_role else '없음'}\n"
        value += f"**암구호**: {'설정됨' if store.get('passphrase') else '없음'}"

        embed.add_field(name=f"🏪 {store['store_name']}", value=value, inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

# ----------------------------
# QR 코드 재발급 (체크인 버튼도 재생성)
# ----------------------------
@bot.tree.command(name="매장qr재발급", description="매장 QR 코드 재발급 및 체크인 버튼 재생성")
@app_commands.describe(
    매장코드="QR 코드를 발급받을 매장 코드",
    체크인채널="체크인 버튼을 표시할 채널 (미지정시 기존 채널)"
)
async def cmd_regenerate_qr(interaction: discord.Interaction, 매장코드: str, 체크인채널: discord.TextChannel = None):
    if not has_allowed_role(interaction):
        await interaction.response.send_message("❌ 권한이 없습니다.", ephemeral=True)
        return

    store = get_store(매장코드)
    if not store:
        await interaction.response.send_message("❌ 존재하지 않는 매장 코드입니다.", ephemeral=True)
        return

    if store['owner_id'] != interaction.user.id and not is_admin_or_developer(interaction):
        await interaction.response.send_message("❌ 본인이 생성한 매장만 QR 재발급이 가능합니다.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild

    # 새 채널 지정 또는 기존 채널 사용
    if 체크인채널:
        channel = 체크인채널
    else:
        channel_id = store.get("channel_id")
        channel = guild.get_channel(channel_id) if channel_id else None

    if not channel:
        await interaction.followup.send("❌ 체크인 채널을 찾을 수 없습니다. 채널을 지정해주세요.", ephemeral=True)
        return

    # 기존 체크인 메시지 삭제 시도
    old_message_id = store.get("message_id")
    if old_message_id:
        try:
            old_channel = guild.get_channel(store.get("channel_id"))
            if old_channel:
                old_msg = await old_channel.fetch_message(old_message_id)
                await old_msg.delete()
        except:
            pass  # 이미 삭제됨

    # 새 체크인 버튼 메시지 생성
    min_role = guild.get_role(store.get("min_role_id")) if store.get("min_role_id") else None

    checkin_embed = discord.Embed(
        title=f"🏪 {store['store_name']}",
        description="아래 버튼을 눌러 체크인하세요!",
        color=discord.Color.blue()
    )
    checkin_embed.add_field(name="매장 코드", value=f"`{매장코드}`", inline=True)
    if min_role:
        checkin_embed.add_field(name="최소 역할", value=min_role.mention, inline=True)
    checkin_embed.add_field(name="암구호", value="✅ 필요" if store.get("passphrase") else "❌ 불필요", inline=True)
    checkin_embed.set_footer(text="체크인은 하루 1회만 가능합니다.")

    view = PersistentCheckinView()
    checkin_msg = await channel.send(embed=checkin_embed, view=view, allowed_mentions=discord.AllowedMentions.none())

    # 매장 정보 업데이트
    update_store(매장코드, {
        "channel_id": channel.id,
        "message_id": checkin_msg.id
    })

    # QR 코드 생성
    channel_url = f"https://discord.com/channels/{guild.id}/{channel.id}"
    qr_buf = generate_qr_image(channel_url)
    qr_file = discord.File(qr_buf, filename=f"qr_{매장코드}.png")

    result_embed = discord.Embed(
        title=f"✅ {store['store_name']} - QR 재발급 완료",
        description=f"체크인 버튼이 {channel.mention}에 생성되었습니다.",
        color=discord.Color.green()
    )
    result_embed.add_field(name="채널 URL", value=channel_url, inline=False)
    result_embed.set_image(url=f"attachment://qr_{매장코드}.png")
    result_embed.set_footer(text="QR 코드를 스캔하면 체크인 채널로 이동합니다.")

    await interaction.followup.send(embed=result_embed, file=qr_file, ephemeral=True)

# ----------------------------
# 매장 방문 (방문자 목록)
# ----------------------------
@bot.tree.command(name="매장방문", description="매장별 방문자 목록")
@app_commands.describe(매장코드="조회할 매장 코드")
async def cmd_store_visits(interaction: discord.Interaction, 매장코드: str):
    if not has_allowed_role(interaction):
        await interaction.response.send_message("❌ 권한이 없습니다.", ephemeral=True)
        return

    store = get_store(매장코드)
    if not store:
        await interaction.response.send_message("❌ 존재하지 않는 매장 코드입니다.", ephemeral=True)
        return

    visits = get_store_visits(매장코드)
    if not visits:
        await interaction.response.send_message(f"**{store['store_name']}**\n방문 기록이 없습니다.", ephemeral=True)
        return

    # 유저별 집계
    user_stats = {}
    for v in visits:
        uid = v['user_id']
        if uid not in user_stats:
            user_stats[uid] = {
                'nickname': v.get('nickname', ''),
                'username': v.get('username', ''),
                'count': 0
            }
        user_stats[uid]['count'] += 1

    # 정렬
    sorted_stats = sorted(user_stats.items(), key=lambda x: x[1]['count'], reverse=True)

    lines = []
    for i, (uid, stat) in enumerate(sorted_stats[:20], 1):
        name = stat['nickname'] or stat['username'] or str(uid)
        lines.append(f"{i}. {name} — {stat['count']}회")

    embed = discord.Embed(
        title=f"📋 {store['store_name']} 방문 기록",
        description="\n".join(lines),
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"총 {len(user_stats)}명 방문")

    await interaction.response.send_message(embed=embed, ephemeral=True)

# ----------------------------
# 매장 통계 (막대 그래프)
# ----------------------------
@bot.tree.command(name="매장통계", description="매장 방문 통계 (막대 그래프)")
@app_commands.describe(
    매장코드="조회할 매장 코드",
    시작일="시작일 (YYYYMMDD)",
    종료일="종료일 (YYYYMMDD)"
)
async def cmd_store_stats(
    interaction: discord.Interaction,
    매장코드: str,
    시작일: str = None,
    종료일: str = None
):
    if not is_admin_or_developer(interaction):
        await interaction.response.send_message("❌ 관리자 또는 개발자만 사용 가능합니다.", ephemeral=True)
        return

    store = get_store(매장코드)
    if not store:
        await interaction.response.send_message("❌ 존재하지 않는 매장 코드입니다.", ephemeral=True)
        return

    # 날짜 변환
    start_date = None
    end_date = None
    if 시작일:
        try:
            start_date = f"{시작일[:4]}-{시작일[4:6]}-{시작일[6:8]}"
        except:
            pass
    if 종료일:
        try:
            end_date = f"{종료일[:4]}-{종료일[4:6]}-{종료일[6:8]}"
        except:
            pass

    stats = get_store_stats(매장코드, start_date, end_date)

    if not stats:
        await interaction.response.send_message(f"**{store['store_name']}**\n해당 기간 방문 기록이 없습니다.", ephemeral=True)
        return

    # 막대 그래프 생성
    max_count = max(s['count'] for s in stats)
    max_bar_length = 12

    lines = []
    for i, stat in enumerate(stats[:15], 1):
        name = stat['nickname'] or stat['username'] or str(stat['user_id'])
        if len(name) > 10:
            name = name[:9] + "…"

        bar_length = int((stat['count'] / max_count) * max_bar_length)
        bar = "█" * bar_length

        lines.append(f"{name:<10} {bar} {stat['count']}회")

    period = ""
    if start_date and end_date:
        period = f"\n{start_date} ~ {end_date}"

    embed = discord.Embed(
        title=f"📊 {store['store_name']} · 방문 통계{period}",
        description="```\n" + "\n".join(lines) + "\n```",
        color=discord.Color.gold()
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)

# ----------------------------
# 매장 방문 기록 (유저별)
# ----------------------------
@bot.tree.command(name="매장방문기록", description="특정 유저의 매장 방문 기록")
@app_commands.describe(유저="조회할 유저")
async def cmd_user_visits(interaction: discord.Interaction, 유저: discord.Member):
    if not is_admin_or_helper(interaction):
        await interaction.response.send_message("❌ 권한이 없습니다.", ephemeral=True)
        return

    visits = get_user_all_visits(유저.id)

    if not visits:
        await interaction.response.send_message(f"**{유저.display_name}**님의 방문 기록이 없습니다.", ephemeral=True)
        return

    lines = []
    total_count = 0
    for i, v in enumerate(visits, 1):
        lines.append(f"{i}. {v['store_name']} — {v['visit_count']}회 ({v['last_visit']})")
        total_count += v['visit_count']

    embed = discord.Embed(
        title=f"📋 {유저.display_name}님의 방문 기록",
        description="\n".join(lines),
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"총 방문: {len(visits)}개 매장 / {total_count}회")

    await interaction.response.send_message(embed=embed, ephemeral=True)

# ----------------------------
# 매장 기록 (xls 내보내기)
# ----------------------------
@bot.tree.command(name="매장기록", description="전체 방문 기록 xls 다운로드")
async def cmd_export_visits(interaction: discord.Interaction):
    if not is_admin_or_developer(interaction):
        await interaction.response.send_message("❌ 관리자 또는 개발자만 사용 가능합니다.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        import openpyxl
        from openpyxl import Workbook

        visits = get_all_visits_for_export()

        wb = Workbook()
        ws = wb.active
        ws.title = "방문기록"

        # 헤더
        ws.append(["유저명", "닉네임", "매장명", "방문일자", "방문시간"])

        # 데이터
        for v in visits:
            ws.append([
                v['username'],
                v['nickname'],
                v['store_name'],
                v['visit_date'],
                v['visit_time']
            ])

        # 파일 저장
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)

        filename = f"방문기록_{_now_kst().strftime('%Y%m%d_%H%M%S')}.xlsx"
        file = discord.File(buf, filename=filename)

        await interaction.followup.send(f"✅ 전체 방문 기록 ({len(visits)}건)", file=file, ephemeral=True)

    except ImportError:
        await interaction.followup.send("❌ openpyxl 패키지가 설치되지 않았습니다.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ 오류 발생: {str(e)}", ephemeral=True)

# ----------------------------
# 매장 체크인 초기화
# ----------------------------
@bot.tree.command(name="매장체크인초기화", description="특정 유저의 오늘 체크인 기록 초기화")
@app_commands.describe(
    유저="초기화할 유저",
    매장코드="매장 코드"
)
async def cmd_reset_checkin(interaction: discord.Interaction, 유저: discord.Member, 매장코드: str):
    if not is_admin_or_developer(interaction):
        await interaction.response.send_message("❌ 관리자 또는 개발자만 사용 가능합니다.", ephemeral=True)
        return

    store = get_store(매장코드)
    if not store:
        await interaction.response.send_message("❌ 존재하지 않는 매장 코드입니다.", ephemeral=True)
        return

    if reset_today_checkin(매장코드, 유저.id):
        await interaction.response.send_message(
            f"✅ **{유저.display_name}**님의 **{store['store_name']}** 오늘 체크인 기록을 초기화했습니다.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message("❌ 초기화할 기록이 없습니다.", ephemeral=True)

# ----------------------------
# 매장 방문 삭제
# ----------------------------
@bot.tree.command(name="매장방문삭제", description="특정 유저의 전체 방문 기록 삭제")
@app_commands.describe(
    유저="삭제할 유저",
    매장코드="매장 코드"
)
async def cmd_delete_visits(interaction: discord.Interaction, 유저: discord.Member, 매장코드: str):
    if not is_admin_or_developer(interaction):
        await interaction.response.send_message("❌ 관리자 또는 개발자만 사용 가능합니다.", ephemeral=True)
        return

    store = get_store(매장코드)
    if not store:
        await interaction.response.send_message("❌ 존재하지 않는 매장 코드입니다.", ephemeral=True)
        return

    deleted = delete_user_visits(매장코드, 유저.id)

    if deleted > 0:
        await interaction.response.send_message(
            f"✅ **{유저.display_name}**님의 **{store['store_name']}** 방문 기록 {deleted}건을 삭제했습니다.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message("❌ 삭제할 기록이 없습니다.", ephemeral=True)

# ----------------------------
# 봇 실행
# ----------------------------
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ .env 파일에 DISCORD_TOKEN을 설정해주세요!")
        import sys
        sys.exit(1)

    bot.run(DISCORD_TOKEN)
