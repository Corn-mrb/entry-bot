import os
from dotenv import load_dotenv
from datetime import timezone, timedelta

load_dotenv()

# ----------------------------
# Timezone
# ----------------------------
KST = timezone(timedelta(hours=9))

# ----------------------------
# Discord 설정
# ----------------------------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
DISCORD_GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0") or 0)

# ----------------------------
# OAuth 설정
# ----------------------------
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# ----------------------------
# 세션 설정
# ----------------------------
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-this-secret-key")
HTTPS_ONLY = os.getenv("HTTPS_ONLY", "false").lower() == "true"
WEB_SESSION_TTL_SECONDS = int(os.getenv("WEB_SESSION_TTL_SECONDS", "180") or 180)

# ----------------------------
# 권한 설정
# ----------------------------
def parse_id_list(raw: str) -> list:
    """쉼표로 구분된 ID 문자열을 리스트로 변환"""
    result = []
    for part in (raw or "").split(","):
        part = part.strip()
        if part.isdigit():
            result.append(int(part))
    return result

# 매장 관리 권한 역할 ID 리스트
ALLOWED_ROLE_IDS = parse_id_list(os.getenv("ALLOWED_ROLE_IDS", ""))

# 관리자 권한 역할 ID 리스트
ADMIN_ROLE_IDS = parse_id_list(os.getenv("ADMIN_ROLE_IDS", ""))

# 개발자 유저 ID
DEVELOPER_USER_ID = int(os.getenv("DEVELOPER_USER_ID", "0") or 0)

# ----------------------------
# 데이터 저장 경로
# ----------------------------
DATA_DIR = "data"
STORES_FILE = os.path.join(DATA_DIR, "stores.json")
VISITS_FILE = os.path.join(DATA_DIR, "visits.json")
