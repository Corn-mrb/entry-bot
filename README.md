# Entry Bot - QR 입장 체크인 시스템

Discord 서버용 QR 코드 기반 매장 입장 관리 봇

## 주요 기능

### 체크인 플로우
```
/매장등록 → QR 코드 생성
    ↓
QR 스캔 → Discord 채널로 이동
    ↓
체크인 버튼 클릭
    ↓
[암구호 설정시] Modal 팝업 입력
    ↓
[역할 검증] 최소 역할 확인
    ↓
✅ 성공 / ❌ 실패 → 채널 알림
```

### 핵심 기능
| 기능 | 설명 |
|------|------|
| 체크인 버튼 | 채널에 버튼 클릭으로 체크인 |
| 암구호 (선택) | 설정시 Modal로 입력 |
| 역할 검증 (선택) | 최소 역할 이상만 체크인 가능 |
| 채널 알림 | 성공/실패 체크인 채널에 알림 |
| 하루 1회 제한 | 같은 날 중복 체크인 방지 |
| 웹 대시보드 | 방문 기록 조회 + CSV/XLSX/PDF 내보내기 |

## 슬래시 명령어

| 명령어 | 설명 | 권한 |
|--------|------|------|
| `/매장등록` | 매장 생성 + 체크인 버튼 + QR 발급 | 허용된 역할 |
| `/매장수정` | 매장 정보 수정 (암구호, 역할 등) | 허용된 역할 |
| `/매장삭제` | 매장 삭제 | 허용된 역할 |
| `/매장목록` | 내 매장 목록 보기 | 허용된 역할 |
| `/매장qr재발급` | QR 코드 + 체크인 버튼 재발급 | 허용된 역할 |
| `/매장기록` | 웹 대시보드 접속 (방문 기록 조회/내보내기) | 관리자/허용된 역할 |
| `/매장체크인초기화` | 특정 유저 오늘 체크인 초기화 | 관리자/개발자 |
| `/매장방문삭제` | 특정 유저 전체 방문 기록 삭제 | 관리자/개발자 |

## 웹 대시보드

`/매장기록` 명령어로 접속 링크 발급 (1시간 유효)

### 기능
- 매장별/전체 방문 기록 조회
- 일별 방문 통계 그래프 (Chart.js)
- 데이터 내보내기: CSV, XLSX, PDF

## 설치

### 1. 패키지 설치
```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정 (.env)
```env
DISCORD_TOKEN=봇토큰
DISCORD_GUILD_ID=서버ID
ALLOWED_ROLE_IDS=역할ID1,역할ID2,역할ID3
ADMIN_ROLE_IDS=
DEVELOPER_USER_ID=개발자유저ID
DASHBOARD_URL=https://your-domain.com
```

### 3. 실행

**봇:**
```bash
python3 bot.py
```

**웹서버 (대시보드용):**
```bash
python3 web.py
```

### 4. PM2로 백그라운드 실행
```bash
pm2 start bot.py --name entry-bot --interpreter python3
pm2 start web.py --name entry-web --interpreter python3
pm2 save
```

## 환경변수

| 변수 | 설명 |
|------|------|
| DISCORD_TOKEN | 봇 토큰 |
| DISCORD_GUILD_ID | 서버 ID |
| ALLOWED_ROLE_IDS | 매장 관리 권한 역할 ID (쉼표 구분) |
| ADMIN_ROLE_IDS | 관리자 역할 ID (쉼표 구분) |
| DEVELOPER_USER_ID | 개발자 유저 ID |
| DASHBOARD_URL | 웹 대시보드 URL |

## 파일 구조

```
entry-bot/
├── bot.py           # Discord 봇
├── web.py           # FastAPI 웹서버 (대시보드)
├── config.py        # 환경변수 설정
├── database.py      # JSON 데이터 관리
├── templates/
│   └── dashboard.html  # 대시보드 웹페이지
├── data/
│   ├── stores.json    # 매장 데이터
│   ├── visits.json    # 방문 기록
│   └── tokens.json    # 대시보드 토큰
├── requirements.txt
├── .env
└── README.md
```

## VPS 배포

### 서버 정보
- **IP**: 139.162.80.142
- **경로**: /root/project/bots/entry-bot

### 배포 명령어
```bash
# 로컬에서 VPS로 업로드
scp -r /Users/gim-yeongseog/Downloads/bots/entry-bot root@139.162.80.142:/root/project/bots/

# VPS 접속
ssh root@139.162.80.142

# PM2로 실행
cd /root/project/bots/entry-bot
pm2 start bot.py --name entry-bot --interpreter python3
pm2 start web.py --name entry-web --interpreter python3
pm2 save
```

## GitHub
- **URL**: https://github.com/Corn-mrb/entry-bot
