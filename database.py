import os
import json
from datetime import datetime, date
from typing import Optional, Dict, List, Any
from config import DATA_DIR, STORES_FILE, VISITS_FILE, KST

# 디렉토리 생성
os.makedirs(DATA_DIR, exist_ok=True)

def _now_kst() -> datetime:
    return datetime.now(tz=KST)

def _today_kst() -> date:
    return _now_kst().date()

def _today_str() -> str:
    return _today_kst().isoformat()

# ----------------------------
# JSON 파일 관리
# ----------------------------
def load_json(filepath: str) -> dict:
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_json(filepath: str, data: dict):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ----------------------------
# 매장 데이터
# ----------------------------
_stores: Dict[str, Any] = {}

def load_stores() -> Dict[str, Any]:
    global _stores
    _stores = load_json(STORES_FILE)
    return _stores

def save_stores():
    save_json(STORES_FILE, _stores)

def get_stores() -> Dict[str, Any]:
    load_stores()  # 최신 데이터 로드
    return _stores

def get_store(store_code: str) -> Optional[Dict[str, Any]]:
    load_stores()  # 최신 데이터 로드
    return _stores.get(store_code)

def create_store(store_code: str, data: dict):
    _stores[store_code] = data
    save_stores()

def update_store(store_code: str, data: dict):
    if store_code in _stores:
        _stores[store_code].update(data)
        save_stores()

def delete_store(store_code: str):
    if store_code in _stores:
        del _stores[store_code]
        save_stores()

# ----------------------------
# 방문 기록 데이터
# ----------------------------
_visits: Dict[str, List[Dict[str, Any]]] = {}

def load_visits() -> Dict[str, List[Dict[str, Any]]]:
    global _visits
    _visits = load_json(VISITS_FILE)
    return _visits

def save_visits():
    save_json(VISITS_FILE, _visits)

def get_visits() -> Dict[str, List[Dict[str, Any]]]:
    load_visits()  # 최신 데이터 로드
    return _visits

def get_store_visits(store_code: str) -> List[Dict[str, Any]]:
    load_visits()  # 최신 데이터 로드
    return _visits.get(store_code, [])

def add_visit(store_code: str, user_id: int, username: str, nickname: str) -> bool:
    """방문 기록 추가. 오늘 이미 방문했으면 False 반환"""
    if store_code not in _visits:
        _visits[store_code] = []
    
    today = _today_str()
    
    # 오늘 이미 방문했는지 확인
    for visit in _visits[store_code]:
        if visit["user_id"] == user_id and visit["visit_date"] == today:
            return False
    
    # 새 방문 기록 추가
    _visits[store_code].append({
        "user_id": user_id,
        "username": username,
        "nickname": nickname,
        "visit_date": today,
        "visit_time": _now_kst().strftime("%H:%M:%S"),
        "created_at": _now_kst().isoformat()
    })
    save_visits()
    return True

def get_user_visit_count(store_code: str, user_id: int) -> int:
    """특정 유저의 특정 매장 방문 횟수"""
    count = 0
    for visit in _visits.get(store_code, []):
        if visit["user_id"] == user_id:
            count += 1
    return count

def get_user_all_visits(user_id: int) -> List[Dict[str, Any]]:
    """특정 유저의 모든 매장 방문 기록"""
    result = []
    for store_code, visits_list in _visits.items():
        store = get_store(store_code)
        store_name = store["store_name"] if store else store_code
        
        user_visits = [v for v in visits_list if v["user_id"] == user_id]
        if user_visits:
            last_visit = max(v["visit_date"] for v in user_visits)
            result.append({
                "store_code": store_code,
                "store_name": store_name,
                "visit_count": len(user_visits),
                "last_visit": last_visit
            })
    
    return sorted(result, key=lambda x: x["last_visit"], reverse=True)

def reset_today_checkin(store_code: str, user_id: int) -> bool:
    """오늘 체크인 기록 초기화"""
    if store_code not in _visits:
        return False
    
    today = _today_str()
    original_len = len(_visits[store_code])
    _visits[store_code] = [
        v for v in _visits[store_code]
        if not (v["user_id"] == user_id and v["visit_date"] == today)
    ]
    
    if len(_visits[store_code]) < original_len:
        save_visits()
        return True
    return False

def delete_user_visits(store_code: str, user_id: int) -> int:
    """특정 유저의 특정 매장 전체 방문 기록 삭제"""
    if store_code not in _visits:
        return 0
    
    original_len = len(_visits[store_code])
    _visits[store_code] = [
        v for v in _visits[store_code]
        if v["user_id"] != user_id
    ]
    
    deleted = original_len - len(_visits[store_code])
    if deleted > 0:
        save_visits()
    return deleted

def get_all_visits_for_export() -> List[Dict[str, Any]]:
    """전체 방문 기록 (xls 내보내기용)"""
    result = []
    for store_code, visits_list in _visits.items():
        store = get_store(store_code)
        store_name = store["store_name"] if store else store_code
        
        for visit in visits_list:
            result.append({
                "username": visit.get("username", ""),
                "nickname": visit.get("nickname", ""),
                "store_name": store_name,
                "visit_date": visit.get("visit_date", ""),
                "visit_time": visit.get("visit_time", "")
            })
    
    return sorted(result, key=lambda x: (x["visit_date"], x["visit_time"]), reverse=True)

def get_store_stats(store_code: str, start_date: str = None, end_date: str = None) -> List[Dict[str, Any]]:
    """매장 통계 (방문자별 횟수)"""
    if store_code not in _visits:
        return []
    
    user_stats = {}
    for visit in _visits[store_code]:
        visit_date = visit["visit_date"]
        
        # 날짜 필터링
        if start_date and visit_date < start_date:
            continue
        if end_date and visit_date > end_date:
            continue
        
        user_id = visit["user_id"]
        if user_id not in user_stats:
            user_stats[user_id] = {
                "user_id": user_id,
                "username": visit.get("username", ""),
                "nickname": visit.get("nickname", ""),
                "count": 0
            }
        user_stats[user_id]["count"] += 1
    
    return sorted(user_stats.values(), key=lambda x: x["count"], reverse=True)

# ----------------------------
# 대시보드 토큰 관리
# ----------------------------
TOKENS_FILE = os.path.join(DATA_DIR, "tokens.json")
_tokens: Dict[str, Any] = {}

def load_tokens() -> Dict[str, Any]:
    global _tokens
    _tokens = load_json(TOKENS_FILE)
    return _tokens

def save_tokens():
    save_json(TOKENS_FILE, _tokens)

def create_dashboard_token(user_id: int, username: str, expires_hours: int = 1) -> str:
    """대시보드 접근 토큰 생성"""
    import secrets
    token = secrets.token_urlsafe(24)

    now = _now_kst()
    from datetime import timedelta
    expires_at = now + timedelta(hours=expires_hours)

    _tokens[token] = {
        "user_id": user_id,
        "username": username,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat()
    }
    save_tokens()
    return token

def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """토큰 검증. 유효하면 토큰 정보 반환, 아니면 None"""
    # 파일에서 최신 토큰 로드
    load_tokens()

    if token not in _tokens:
        return None

    token_data = _tokens[token]
    expires_at = datetime.fromisoformat(token_data["expires_at"])

    if _now_kst() > expires_at:
        # 만료된 토큰 삭제
        del _tokens[token]
        save_tokens()
        return None

    return token_data

def cleanup_expired_tokens():
    """만료된 토큰 정리"""
    now = _now_kst()
    expired = []

    for token, data in _tokens.items():
        expires_at = datetime.fromisoformat(data["expires_at"])
        if now > expires_at:
            expired.append(token)

    for token in expired:
        del _tokens[token]

    if expired:
        save_tokens()

def get_daily_stats(store_code: str = None, days: int = 30) -> List[Dict[str, Any]]:
    """일별 방문 통계"""
    from datetime import timedelta

    today = _today_kst()
    start_date = today - timedelta(days=days)

    daily = {}
    for i in range(days + 1):
        d = (start_date + timedelta(days=i)).isoformat()
        daily[d] = 0

    visits_to_check = _visits.get(store_code, []) if store_code else []
    if not store_code:
        for visits_list in _visits.values():
            visits_to_check.extend(visits_list)

    for visit in visits_to_check:
        vd = visit.get("visit_date", "")
        if vd in daily:
            daily[vd] += 1

    return [{"date": d, "count": c} for d, c in sorted(daily.items())]

# 초기 로드
load_stores()
load_visits()
load_tokens()
