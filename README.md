# Entry Bot - QR 입장 시스템

Discord 서버용 QR 코드 기반 입장 관리 시스템

## 기능

### 체크인 플로우
1. 매장주가 `/매장등록` → QR코드 생성
2. 방문자가 QR 스캔 → 웹페이지 열림
3. Discord OAuth 로그인 (앱에서 승인 버튼만 클릭)
4. 역할 검증 + 암구호 입력 (설정된 경우)
5. 체크인 완료 → 매장주에게 DM 알림

### 명령어

| 명령어 | 설명 | 권한 |
|--------|------|------|
| /매장등록 | QR코드 생성 | 허용된 역할 |
| /매장수정 | 설정 변경 | 허용된 역할 |
| /매장삭제 | 매장 삭제 | 허용된 역할 |
| /매장목록 | 내 매장 보기 | 허용된 역할 |
| /매장방문 | 매장별 방문자 목록 | 허용된 역할 |
| /매장통계 | 막대 그래프 통계 | 관리자/개발자 |
| /매장방문기록 | 유저별 방문 기록 | 관리자/Helper |
| /매장기록 | 전체 방문 기록 xls | 관리자/개발자 |
| /매장체크인초기화 | 오늘 기록 초기화 | 관리자/개발자 |
| /매장방문삭제 | 전체 기록 삭제 | 관리자/개발자 |
| /입장 | 백업용 입장 | 모두 |

## 설치

### 1. 패키지 설치
```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정
```bash
cp .env.example .env
nano .env
```

### 3. Discord 앱 설정
1. [Discord Developer Portal](https://discord.com/developers/applications)
2. OAuth2 → Redirects에 `https://your-domain.com/oauth/callback` 추가
3. Bot → Intents 활성화 (SERVER MEMBERS, MESSAGE CONTENT)

### 4. 실행

**웹서버 (FastAPI):**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

**봇:**
```bash
python bot.py
```

### 5. PM2로 백그라운드 실행
```bash
pm2 start main.py --name entry-web --interpreter python3 -- -m uvicorn main:app --host 0.0.0.0 --port 8000
pm2 start bot.py --name entry-bot --interpreter python3
pm2 save
```

## 환경변수

| 변수 | 설명 |
|------|------|
| DISCORD_TOKEN | 봇 토큰 |
| DISCORD_CLIENT_ID | OAuth 클라이언트 ID |
| DISCORD_CLIENT_SECRET | OAuth 클라이언트 시크릿 |
| DISCORD_GUILD_ID | 서버 ID |
| OAUTH_REDIRECT_URI | OAuth 콜백 URL |
| BASE_URL | 웹서버 기본 URL |
| SESSION_SECRET | 세션 암호화 키 |
| ALLOWED_ROLE_IDS | 매장 관리 권한 역할 ID (쉼표 구분) |
| ADMIN_ROLE_IDS | 관리자 역할 ID (쉼표 구분) |
| DEVELOPER_USER_ID | 개발자 유저 ID |

## 파일 구조

```
entry-bot/
├── main.py          # FastAPI 웹서버
├── bot.py           # Discord 봇
├── config.py        # 환경변수 설정
├── database.py      # 데이터 관리
├── discord_api.py   # Discord API 헬퍼
├── templates/
│   └── index.html   # 체크인 웹페이지
├── data/            # 데이터 저장 (Git 제외)
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```
