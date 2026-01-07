import os
import random
from io import BytesIO
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import qrcode

from config import (
    SESSION_SECRET, HTTPS_ONLY, BASE_URL, 
    WEB_SESSION_TTL_SECONDS, KST
)
from database import (
    get_store, get_stores, add_visit, get_user_visit_count,
    _now_kst
)
from discord_api import (
    get_oauth_authorize_url, get_discord_authorize_url,
    exchange_oauth_code, fetch_oauth_user,
    get_guild_member, member_display_name, member_username,
    get_member_role_names, check_user_role_position, add_role_to_member,
    send_dm
)

# ----------------------------
# App Setup
# ----------------------------
app = FastAPI(title="Entry Bot - QR Check-in System")

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    https_only=HTTPS_ONLY,
    same_site="lax",
)

templates = Jinja2Templates(directory="templates")

# ----------------------------
# Session TTL Middleware
# ----------------------------
@app.middleware("http")
async def session_ttl_middleware(request: Request, call_next):
    try:
        if request.session.get("user") and request.session.get("login_ts"):
            ts = int(request.session.get("login_ts") or 0)
            if ts > 0 and int(_now_kst().timestamp()) - ts > WEB_SESSION_TTL_SECONDS:
                request.session.clear()
    except Exception:
        pass
    return await call_next(request)

# ----------------------------
# Web Routes
# ----------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, loc: str = ""):
    """메인 페이지 - 체크인 화면"""
    if loc:
        request.session["loc"] = loc
    
    loc = (loc or request.session.get("loc") or "").strip()
    
    # 매장 정보 가져오기
    store = get_store(loc) if loc else None
    store_name = store["store_name"] if store else "등록되지 않은 장소"
    
    # 로그인 상태 확인
    is_logged_in = bool(request.session.get("user"))
    user = request.session.get("user") or {}
    
    # OAuth URL
    oauth_url = get_oauth_authorize_url(loc) if loc else ""
    discord_authorize_url = get_discord_authorize_url(loc) if loc else ""

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "loc": loc,
            "store_name": store_name,
            "store_exists": store is not None,
            "is_logged_in": is_logged_in,
            "user": user,
            "oauth_url": oauth_url,
            "discord_authorize_url": discord_authorize_url,
        },
    )

@app.get("/oauth/callback")
async def oauth_callback(request: Request, code: str = "", state: str = ""):
    """Discord OAuth 콜백"""
    loc = (state or request.session.get("loc") or "").strip()
    
    if not code:
        return RedirectResponse(f"/?loc={loc}", status_code=302)
    
    try:
        # 토큰 교환
        tok = await exchange_oauth_code(code)
        access_token = tok.get("access_token")
        if not access_token:
            raise RuntimeError("no access_token")
        
        # 유저 정보 가져오기
        user = await fetch_oauth_user(access_token)
        
        request.session["user"] = {
            "id": int(user.get("id")),
            "username": user.get("username") or "",
            "global_name": user.get("global_name") or "",
        }
        request.session["login_ts"] = int(_now_kst().timestamp())
        request.session["loc"] = loc
        
    except Exception as e:
        print(f"OAuth error: {e}")
        request.session.clear()
        return RedirectResponse(f"/?loc={loc}&error=oauth_failed", status_code=302)
    
    return RedirectResponse(f"/?loc={loc}", status_code=302)

@app.get("/logout")
async def logout(request: Request):
    """로그아웃"""
    loc = (request.session.get("loc") or "").strip()
    request.session.clear()
    return RedirectResponse(f"/?loc={loc}", status_code=302)

@app.post("/api/checkin")
async def api_checkin(request: Request):
    """체크인 API"""
    user = request.session.get("user")
    if not user:
        return JSONResponse({"success": False, "message": "로그인이 필요합니다."}, status_code=401)
    
    body = await request.json()
    loc = (body.get("loc") or request.session.get("loc") or "").strip()
    passphrase_input = (body.get("passphrase") or "").strip()
    
    if not loc:
        return JSONResponse({"success": False, "message": "매장 코드가 없습니다."}, status_code=400)
    
    # 매장 확인
    store = get_store(loc)
    if not store:
        return JSONResponse({"success": False, "message": "등록되지 않은 매장입니다."}, status_code=404)
    
    user_id = int(user.get("id"))
    
    # 서버 멤버 정보 가져오기
    member = await get_guild_member(user_id)
    if not member:
        return JSONResponse({
            "success": False, 
            "message": "디스코드 서버에 먼저 가입해주세요."
        }, status_code=403)
    
    nickname = member_display_name(member)
    username = member_username(member)
    
    # 역할 검증 (최소역할이 설정된 경우)
    min_role_id = store.get("min_role_id")
    if min_role_id:
        has_role = await check_user_role_position(user_id, min_role_id)
        if not has_role:
            role_names = await get_member_role_names(user_id)
            
            # 매장주에게 입장 실패 알림
            owner_id = store.get("owner_id")
            if owner_id:
                now = _now_kst()
                embed = {
                    "title": f"⚠️ [입장 실패] {nickname}님이 입장 시도",
                    "color": 0xFFA500,  # Orange
                    "description": "**실패 사유**: 입장 권한 부족 (최소 역할 미달)",
                    "fields": [
                        {"name": "장소", "value": store["store_name"], "inline": True},
                        {"name": "시도자", "value": f"<@{user_id}>", "inline": True},
                        {"name": "시도 시간", "value": f"{now.strftime('%H:%M')} (KST)", "inline": True},
                        {"name": "현재 역할", "value": ", ".join(role_names) if role_names else "(없음)", "inline": False},
                    ]
                }
                await send_dm(owner_id, embed=embed)
            
            return JSONResponse({
                "success": False,
                "message": "입장 권한이 없습니다. 필요한 역할이 부족합니다.",
                "user_roles": role_names
            }, status_code=403)
    
    # 암구호 검증 (암구호가 설정된 경우)
    store_passphrase = store.get("passphrase")
    if store_passphrase:
        if not passphrase_input:
            return JSONResponse({
                "success": False,
                "message": "암구호를 입력해주세요.",
                "need_passphrase": True
            }, status_code=400)
        
        if passphrase_input != store_passphrase:
            # 매장주에게 암구호 오류 알림
            owner_id = store.get("owner_id")
            if owner_id:
                now = _now_kst()
                role_names = await get_member_role_names(user_id)
                
                embed = {
                    "title": f"⚠️ [입장 실패] {nickname}님이 입장 시도",
                    "color": 0xFF0000,  # Red
                    "description": "**실패 사유**: 암구호 불일치",
                    "fields": [
                        {"name": "장소", "value": store["store_name"], "inline": True},
                        {"name": "시도자", "value": f"<@{user_id}>", "inline": True},
                        {"name": "시도 시간", "value": f"{now.strftime('%H:%M')} (KST)", "inline": True},
                        {"name": "입력한 암구호", "value": f"`{passphrase_input}`", "inline": True},
                        {"name": "역할", "value": ", ".join(role_names) if role_names else "(없음)", "inline": False},
                    ]
                }
                await send_dm(owner_id, embed=embed)
            
            return JSONResponse({
                "success": False,
                "message": "암구호가 일치하지 않습니다."
            }, status_code=403)
    
    # 방문 기록 추가 (중복 체크)
    is_new_visit = add_visit(loc, user_id, username, nickname)
    
    if not is_new_visit:
        return JSONResponse({
            "success": True,
            "message": "이미 오늘 체크인했습니다. (하루 1회)",
            "already_checked_in": True
        })
    
    # 방문 횟수
    visit_count = get_user_visit_count(loc, user_id)
    
    # 역할 부여 (설정된 경우)
    role_granted = False
    grant_role_id = store.get("grant_role_id")
    if grant_role_id:
        role_granted = await add_role_to_member(user_id, grant_role_id)
    
    # 역할 목록 가져오기
    role_names = await get_member_role_names(user_id)
    
    # 매장주에게 DM 알림 (성공)
    owner_id = store.get("owner_id")
    if owner_id:
        now = _now_kst()
        label = "오늘 첫 방문" if visit_count == 1 else f"누적 {visit_count}회차"
        
        embed = {
            "title": f"✅ [입장 성공] {nickname}님이 체크인! ({label})",
            "color": 0x00FF00,  # Green
            "fields": [
                {"name": "장소", "value": store["store_name"], "inline": True},
                {"name": "방문자", "value": f"<@{user_id}>", "inline": True},
                {"name": "방문 시간", "value": f"{now.strftime('%H:%M')} (KST)", "inline": True},
                {"name": "방문 횟수", "value": f"{visit_count}번째 방문", "inline": True},
                {"name": "역할", "value": ", ".join(role_names) if role_names else "(없음)", "inline": False},
            ]
        }
        
        if role_granted:
            embed["fields"].append({
                "name": "역할 부여", 
                "value": "✅ 부여됨", 
                "inline": True
            })
        
        await send_dm(owner_id, embed=embed)
    
    return JSONResponse({
        "success": True,
        "message": f"{store['store_name']} 체크인 완료!",
        "visit_count": visit_count,
        "role_granted": role_granted,
        "nickname": nickname
    })

# ----------------------------
# QR Code Generation
# ----------------------------
@app.get("/qr/{store_code}.png")
async def qr_image(request: Request, store_code: str):
    """QR 코드 이미지 생성"""
    url = f"{BASE_URL}/?loc={store_code}"
    
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    
    return Response(content=buf.getvalue(), media_type="image/png")

# ----------------------------
# Health Check
# ----------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}
