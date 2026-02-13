# Discord QR 입장 봇 - 개발 메모

## 현재 상태 (2026-01-09)

### 구현 완료
- 체크인 시스템 (QR → 채널 → 버튼 클릭)
- 암구호 Modal
- 역할 검증
- 하루 1회 제한
- 웹 대시보드 (토큰 기반 인증)
- CSV/XLSX/PDF 내보내기

### 미구현
- 초대 링크 자동 갱신 (15분마다)

---

## 슬래시 명령어

| 명령어 | 설명 | 권한 |
|--------|------|------|
| `/매장등록` | 매장 생성 + 체크인 버튼 + QR 발급 | ALLOWED_ROLE_IDS |
| `/매장수정` | 매장 정보 수정 | ALLOWED_ROLE_IDS |
| `/매장삭제` | 매장 삭제 | ALLOWED_ROLE_IDS |
| `/매장목록` | 내 매장 목록 | ALLOWED_ROLE_IDS |
| `/매장qr재발급` | QR + 체크인 버튼 재발급 | ALLOWED_ROLE_IDS |
| `/매장기록` | 웹 대시보드 접속 링크 | 관리자 + ALLOWED_ROLE_IDS |
| `/매장체크인초기화` | 오늘 체크인 초기화 | 관리자/개발자 |
| `/매장방문삭제` | 전체 방문 기록 삭제 | 관리자/개발자 |

### 삭제된 명령어
- `/매장방문` - 대시보드로 대체
- `/매장통계` - 대시보드로 대체
- `/매장방문기록` - 대시보드로 대체

---

## 권한 시스템

```python
# ALLOWED_ROLE_IDS - 매장 관리 권한
1316677722344394817  # Helper
1433819504819044536  # Bitcoin Corporation
1426195405124927780  # Bitcoin Accepted
1450069310033756232  # 센터장 | 컨퍼런스장

# 관리자 권한
- guild_permissions.administrator = True
- DEVELOPER_USER_ID = 1317050513602121768
```

---

## 파일 구조

```
entry-bot/
├── bot.py           # Discord 봇 (슬래시 명령어)
├── web.py           # FastAPI 웹서버 (대시보드 API)
├── config.py        # 환경변수 로드
├── database.py      # JSON 데이터 관리
├── templates/
│   └── dashboard.html  # 대시보드 UI (Chart.js)
├── data/
│   ├── stores.json    # 매장 데이터
│   ├── visits.json    # 방문 기록
│   └── tokens.json    # 대시보드 토큰 (1시간 유효)
├── requirements.txt
├── .env
├── README.md
└── CLAUDE.md
```

---

## 웹 대시보드

### 접속 방법
1. Discord에서 `/매장기록` 실행
2. 1시간 유효 토큰 발급
3. 링크 클릭 → 대시보드 접속

### API 엔드포인트 (web.py)
| 경로 | 설명 |
|------|------|
| GET `/dashboard` | 대시보드 페이지 |
| GET `/api/stores` | 매장 목록 |
| GET `/api/visits` | 방문 기록 |
| GET `/api/stats/daily` | 일별 통계 |
| GET `/api/export/csv` | CSV 내보내기 |
| GET `/api/export/xlsx` | Excel 내보내기 |
| GET `/api/export/pdf` | PDF 내보내기 |

### 토큰 인증
- 모든 API에 `?token=xxx` 필수
- `database.py`의 `verify_token()` 함수로 검증
- 만료 시 자동 삭제

---

## VPS 배포

### 서버 정보
- **IP**: 139.162.80.142
- **경로**: /root/project/bots/entry-bot
- **도메인**: entry.citadelcertify.org (Cloudflare)

### 배포 명령어
```bash
# 업로드
scp -r /Users/gim-yeongseog/Downloads/bots/entry-bot root@139.162.80.142:/root/project/bots/

# VPS 접속
ssh root@139.162.80.142

# PM2 실행
cd /root/project/bots/entry-bot
pm2 restart entry-bot || pm2 start bot.py --name entry-bot --interpreter python3
pm2 restart entry-web || pm2 start web.py --name entry-web --interpreter python3
pm2 save
```

### 주의사항
- `pm2 delete all` 사용 금지! (다른 봇들도 삭제됨)
- 봇 토큰 재생성 시 `.env` 업데이트 필요
- VPS에서 다른 봇들도 실행 중 (운동기부봇, 시타델페이, 전광판봇)

---

## 트러블슈팅

### "Interaction already acknowledged" 에러
- 원인: 같은 토큰으로 여러 봇 실행 중
- 해결: Discord Developer Portal에서 토큰 재생성

### stores.json 데이터 안 보임
- 원인: `get_store()` 함수가 캐시된 데이터만 사용
- 해결: `load_stores()` 호출 추가 (완료)

### 대시보드 토큰 만료
- 원인: 1시간 유효
- 해결: `/매장기록`으로 새 토큰 발급

---

## GitHub
- **URL**: https://github.com/Corn-mrb/entry-bot
- **작성자**: mr.b
