import httpx
from typing import Optional, List, Dict, Any
from config import DISCORD_TOKEN, DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, DISCORD_GUILD_ID, OAUTH_REDIRECT_URI

# ----------------------------
# Discord API 호출
# ----------------------------
async def discord_api(
    method: str,
    path: str,
    *,
    bot: bool = True,
    token: Optional[str] = None,
    json_body: Optional[dict] = None,
) -> httpx.Response:
    if bot:
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    else:
        headers = {"Authorization": f"Bearer {token}"}
    
    headers["User-Agent"] = "entry-bot (1.0)"
    
    if json_body is not None:
        headers["Content-Type"] = "application/json"

    url = f"https://discord.com/api/v10{path}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.request(method, url, headers=headers, json=json_body)
    return r

# ----------------------------
# 길드 멤버 정보
# ----------------------------
async def get_guild_member(user_id: int) -> Optional[dict]:
    if not DISCORD_GUILD_ID:
        return None
    r = await discord_api("GET", f"/guilds/{DISCORD_GUILD_ID}/members/{user_id}", bot=True)
    if r.status_code == 200:
        return r.json()
    return None

def member_display_name(member: dict) -> str:
    """서버 닉네임 또는 유저명 반환"""
    nick = member.get("nick")
    if nick:
        return nick
    u = member.get("user") or {}
    return u.get("global_name") or u.get("username") or str(u.get("id") or "")

def member_username(member: dict) -> str:
    """유저명 반환"""
    u = member.get("user") or {}
    username = u.get("username") or ""
    disc = u.get("discriminator")
    if disc and disc != "0":
        return f"{username}#{disc}"
    return username or str(u.get("id") or "")

async def get_member_role_ids(user_id: int) -> List[int]:
    """유저의 역할 ID 리스트 반환"""
    member = await get_guild_member(user_id)
    if not member:
        return []
    return [int(rid) for rid in (member.get("roles") or []) if str(rid).isdigit()]

async def get_guild_roles() -> Dict[int, str]:
    """길드의 모든 역할 반환 (id: name)"""
    if not DISCORD_GUILD_ID:
        return {}
    r = await discord_api("GET", f"/guilds/{DISCORD_GUILD_ID}/roles", bot=True)
    if r.status_code != 200:
        return {}
    roles = r.json()
    return {int(x["id"]): x.get("name", "") for x in roles if x.get("id")}

async def get_member_role_names(user_id: int) -> List[str]:
    """유저의 역할 이름 리스트 반환"""
    member = await get_guild_member(user_id)
    if not member:
        return []
    
    role_ids = [int(rid) for rid in (member.get("roles") or []) if str(rid).isdigit()]
    role_map = await get_guild_roles()
    
    names = []
    for rid in role_ids:
        if rid == DISCORD_GUILD_ID:  # @everyone 제외
            continue
        name = role_map.get(rid)
        if name:
            names.append(name)
    
    names.sort(key=lambda s: s.lower())
    return names

async def check_user_has_role(user_id: int, role_id: int) -> bool:
    """유저가 특정 역할을 가지고 있는지 확인"""
    role_ids = await get_member_role_ids(user_id)
    return role_id in role_ids

async def check_user_role_position(user_id: int, min_role_id: int) -> bool:
    """유저가 최소 역할 이상인지 확인 (역할 위치 기반)"""
    member = await get_guild_member(user_id)
    if not member:
        return False
    
    user_role_ids = [int(rid) for rid in (member.get("roles") or []) if str(rid).isdigit()]
    
    # 최소 역할이 유저 역할에 포함되어 있으면 True
    if min_role_id in user_role_ids:
        return True
    
    # 역할 위치 확인 (더 높은 역할이 있는지)
    r = await discord_api("GET", f"/guilds/{DISCORD_GUILD_ID}/roles", bot=True)
    if r.status_code != 200:
        return False
    
    roles = r.json()
    role_positions = {int(x["id"]): x.get("position", 0) for x in roles}
    
    min_role_position = role_positions.get(min_role_id, 0)
    
    for rid in user_role_ids:
        if role_positions.get(rid, 0) >= min_role_position:
            return True
    
    return False

async def add_role_to_member(user_id: int, role_id: int) -> bool:
    """유저에게 역할 부여"""
    if not DISCORD_GUILD_ID:
        return False
    r = await discord_api("PUT", f"/guilds/{DISCORD_GUILD_ID}/members/{user_id}/roles/{role_id}", bot=True)
    return r.status_code in (200, 204)

async def send_dm(user_id: int, content: str = None, embed: dict = None) -> bool:
    """유저에게 DM 전송"""
    # DM 채널 생성
    r = await discord_api("POST", "/users/@me/channels", bot=True, json_body={"recipient_id": str(user_id)})
    if r.status_code != 200:
        return False
    
    ch = r.json()
    ch_id = ch.get("id")
    if not ch_id:
        return False
    
    # 메시지 전송
    body: Dict[str, Any] = {}
    if content:
        body["content"] = content
    if embed:
        body["embeds"] = [embed]
    
    r = await discord_api("POST", f"/channels/{ch_id}/messages", bot=True, json_body=body)
    return r.status_code == 200

# ----------------------------
# OAuth2
# ----------------------------
def get_oauth_authorize_url(state: str) -> str:
    """Discord OAuth 인증 URL 생성"""
    from urllib.parse import urlencode
    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify",
        "state": state,
        "prompt": "none",
    }
    return "https://discord.com/oauth2/authorize?" + urlencode(params)

async def exchange_oauth_code(code: str) -> dict:
    """OAuth 코드를 토큰으로 교환"""
    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": OAUTH_REDIRECT_URI,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post("https://discord.com/api/v10/oauth2/token", data=data, headers=headers)
        r.raise_for_status()
        return r.json()

async def fetch_oauth_user(access_token: str) -> dict:
    """OAuth 토큰으로 유저 정보 가져오기"""
    r = await discord_api("GET", "/users/@me", bot=False, token=access_token)
    r.raise_for_status()
    return r.json()
