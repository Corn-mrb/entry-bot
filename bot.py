import discord
from discord.ext import commands
from discord import app_commands
import random
import os
from datetime import datetime
from io import BytesIO

from config import (
    DISCORD_TOKEN, DISCORD_GUILD_ID, BASE_URL,
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
        return True  # 설정 안 되어있으면 모두 허용
    user_role_ids = [role.id for role in interaction.user.roles]
    return any(rid in user_role_ids for rid in ALLOWED_ROLE_IDS)

def is_admin_or_developer(interaction: discord.Interaction) -> bool:
    """관리자 또는 개발자 권한 확인"""
    # 개발자 확인
    if interaction.user.id == DEVELOPER_USER_ID:
        return True
    
    # 관리자 역할 확인
    if ADMIN_ROLE_IDS:
        user_role_ids = [role.id for role in interaction.user.roles]
        if any(rid in user_role_ids for rid in ADMIN_ROLE_IDS):
            return True
    
    # 디스코드 관리자 권한 확인
    if interaction.user.guild_permissions.administrator:
        return True
    
    return False

def is_admin_or_helper(interaction: discord.Interaction) -> bool:
    """관리자 또는 Helper 권한 확인"""
    if is_admin_or_developer(interaction):
        return True
    return has_allowed_role(interaction)

# ----------------------------
# 봇 이벤트
# ----------------------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'✅ {bot.user} 봇이 준비되었습니다!')
    print(f'서버 수: {len(bot.guilds)}')
    print(f'로드된 매장 수: {len(get_stores())}')

# ----------------------------
# 매장 등록
# ----------------------------
@bot.tree.command(name="매장등록", description="매장 입장용 QR 생성")
@app_commands.describe(
    매장명="매장 또는 이벤트 이름",
    최소역할="입장 가능한 최소 역할 (선택사항)",
    부여역할="입장 승인 시 자동 부여할 역할 (선택사항)",
    암구호="오늘의 암구호 (선택사항)"
)
async def cmd_create_store(
    interaction: discord.Interaction,
    매장명: str,
    최소역할: discord.Role = None,
    부여역할: discord.Role = None,
    암구호: str = None
):
    if not has_allowed_role(interaction):
        await interaction.response.send_message("❌ 권한이 없습니다.", ephemeral=True)
        return
    
    # 매장 코드 생성 (숫자 2자리)
    stores = get_stores()
    while True:
        store_code = f"{random.randint(1, 99):02d}"
        if store_code not in stores:
            break
    
    # 매장 저장
    create_store(store_code, {
        "store_name": 매장명,
        "min_role_id": 최소역할.id if 최소역할 else None,
        "grant_role_id": 부여역할.id if 부여역할 else None,
        "passphrase": 암구호,
        "owner_id": interaction.user.id,
        "guild_id": interaction.guild_id,
        "created_at": _now_kst().isoformat()
    })
    
    # QR URL
    qr_url = f"{BASE_URL}/qr/{store_code}.png"
    checkin_url = f"{BASE_URL}/?loc={store_code}"
    
    embed = discord.Embed(
        title=f"🏪 {매장명} - 매장 등록 완료",
        color=discord.Color.blue()
    )
    embed.add_field(name="매장 코드", value=f"# **`{store_code}`**", inline=False)
    embed.add_field(name="체크인 URL", value=checkin_url, inline=False)
    embed.add_field(name="QR 이미지", value=qr_url, inline=False)
    
    if 최소역할:
        embed.add_field(name="최소 역할", value=최소역할.mention, inline=True)
    else:
        embed.add_field(name="최소 역할", value="없음 (모두 입장 가능)", inline=True)
    
    if 부여역할:
        embed.add_field(name="부여 역할", value=부여역할.mention, inline=True)
    
    embed.add_field(name="암구호", value="✅ 설정됨" if 암구호 else "❌ 없음", inline=True)
    
    embed.set_image(url=qr_url)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ----------------------------
# 매장 수정
# ----------------------------
@bot.tree.command(name="매장수정", description="매장 정보 수정")
@app_commands.describe(
    매장코드="수정할 매장의 코드",
    매장명="새 매장명 (선택사항)",
    최소역할="새 최소 역할 (선택사항)",
    부여역할="새 부여 역할 (선택사항)",
    암구호="새 암구호 (선택사항, 빈칸으로 제거)"
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
        if 암구호 == "":
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
    
    store_name = store['store_name']
    delete_store(매장코드)
    
    await interaction.response.send_message(f"✅ '{store_name}' 매장이 삭제되었습니다.", ephemeral=True)

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
        
        value = f"**코드**: `{code}`\n"
        value += f"**최소역할**: {min_role.name if min_role else '없음'}\n"
        value += f"**암구호**: {'설정됨' if store.get('passphrase') else '없음'}"
        
        embed.add_field(name=f"🏪 {store['store_name']}", value=value, inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

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
# 입장 (백업용 - 기존 방식)
# ----------------------------
@bot.tree.command(name="입장", description="매장 입장 인증 (백업용)")
@app_commands.describe(매장코드="매장 코드")
async def cmd_entry(interaction: discord.Interaction, 매장코드: str):
    store = get_store(매장코드)
    if not store:
        await interaction.response.send_message("❌ 유효하지 않은 매장 코드입니다.", ephemeral=True)
        return
    
    guild = bot.get_guild(store['guild_id'])
    member = guild.get_member(interaction.user.id) if guild else None
    
    if not member:
        await interaction.response.send_message("❌ 서버에 먼저 가입해주세요.", ephemeral=True)
        return
    
    # 역할 확인
    min_role_id = store.get('min_role_id')
    if min_role_id:
        min_role = guild.get_role(min_role_id)
        has_role = any(role >= min_role for role in member.roles) if min_role else True
        
        if not has_role:
            await interaction.response.send_message("❌ 입장 권한이 없습니다.", ephemeral=True)
            return
    
    # 암구호 확인이 필요하면 DM으로 안내
    if store.get('passphrase'):
        await interaction.response.send_message(
            f"🔐 **{store['store_name']}**\n\n암구호 입력이 필요합니다.\nQR 체크인을 이용해주세요: {BASE_URL}/?loc={매장코드}",
            ephemeral=True
        )
        return
    
    # 방문 기록 추가
    is_new = add_visit(매장코드, interaction.user.id, interaction.user.name, member.display_name)
    
    if not is_new:
        await interaction.response.send_message("✅ 이미 오늘 체크인했습니다.", ephemeral=True)
        return
    
    # 역할 부여
    grant_role_id = store.get('grant_role_id')
    if grant_role_id:
        grant_role = guild.get_role(grant_role_id)
        if grant_role and grant_role not in member.roles:
            try:
                await member.add_roles(grant_role)
            except:
                pass
    
    visit_count = get_user_visit_count(매장코드, interaction.user.id)
    
    await interaction.response.send_message(
        f"✅ **{store['store_name']}** 입장 완료!\n누적 {visit_count}번째 방문입니다.",
        ephemeral=True
    )

# ----------------------------
# 봇 실행
# ----------------------------
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ .env 파일에 DISCORD_TOKEN을 설정해주세요!")
        import sys
        sys.exit(1)
    
    bot.run(DISCORD_TOKEN)
