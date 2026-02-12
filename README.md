# AX RADAR v4.4 — Smart Money Intelligence Platform

> **"기관의 속마음을 읽다"** — 외국인 스마트머니가 베팅하는 한국 AX 수혜주를 추적합니다.
> Powered by Muze AI

---

## Quick Start

```bash
# 가상환경
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# .env 설정 (키움 REST API 키)
# KIWOOM_APPKEY=your_appkey
# KIWOOM_SECRETKEY=your_secretkey

# 실행
python app.py
```

브라우저에서 `http://localhost:5000` 접속

---

## 프로젝트 개요

AX RADAR는 AI 전환(AX) 시대의 주식 시장 정보 서비스입니다.
모건스탠리, JP모건, 골드만삭스 3대 외국계 기관의 실시간 수급 데이터를 추적하고,
외국인 순매수 TOP 10과 개인 순매도의 교집합에서 **Conviction Signal**을 산출합니다.

### 핵심 기능

| 기능 | 설명 |
|------|------|
| **Conviction Signal** | 외국인 순매수 TOP 10 ∩ 개인 순매도 → 6개월 승률 95% 교집합 종목 |
| **Smart Money Intensity** | 3사 통합 진정성 순위 — 매매의 진심을 점수화 (0~100) |
| **3사 기관 추적** | MS/JP/GS 각 기관별 진정성 TOP, 순매수/순매도 TOP |
| **AI 정량분석** | 캐시된 수급 데이터 기반 시장 내러티브 자동 생성 |
| **프리미엄 Article** | WSJ 시황, Daily Radar, AX ETF Alpha, Editor Column |

---

## 기술 스택

| 구분 | 기술 |
|------|------|
| Backend | Flask (Python 3.10+) |
| Frontend | Vanilla HTML/CSS/JS (Jinja2 템플릿) |
| Data Source | 키움 REST API (실시간) + pykrx (장마감 후 확정) |
| 디자인 | White Theme (Dashboard) + Dark Theme (Articles) |
| 폰트 | Plus Jakarta Sans / JetBrains Mono / Noto Sans KR |

---

## 파일 구조

```
morgan_dive_v2/
├── .env                        # 키움 API 키 (KIWOOM_APPKEY, KIWOOM_SECRETKEY)
├── app.py                      # Flask 서버 + 전체 API 라우트
├── config.py                   # 설정 (기관 코드, 섹터맵, 환경변수)
├── requirements.txt            # Python 의존성
├── README.md                   # 이 문서
│
├── modules/
│   ├── __init__.py
│   ├── kiwoom.py               # TokenManager + KiwoomAPI + KiwoomLogic
│   ├── conviction.py           # ConvictionEngine (외국인 ∩ 개인 → Score)
│   └── analysis.py             # MarketAnalyzer (데이터 → 내러티브)
│
└── templates/
    ├── index.html              # Daily X 대시보드 (라이브 데이터, 30초 갱신)
    ├── article_base.html       # Article 공통 레이아웃 (다크 테마)
    ├── wsj.html                # Wall Street 시황 분석
    ├── radar.html              # Daily Radar 브리핑
    ├── etf.html                # AX ETF Alpha Board (20선)
    └── column.html             # Editor Column
```

---

## 페이지 & 라우트

| 경로 | 템플릿 | 설명 | 테마 |
|------|--------|------|------|
| `/` | index.html | 라이브 데이터 대시보드 (키움 API, 30초 갱신) | White |
| `/wsj` | wsj.html | Wall Street 글로벌 시황 분석 | Dark |
| `/radar` | radar.html | Daily X Briefing 수급 분석 | Dark |
| `/etf` | etf.html | AX Alpha Board 최종 정예 20선 | Dark |
| `/column` | column.html | Editor Column (SaaSpocalypse 등) | Dark |

- Page 1 (Daily X): CSS/JS 전부 인라인, 키움 API 실시간 연동
- Pages 2~5: Jinja2 `article_base.html` 상속, 정적 프리미엄 아티클
- 네비게이션: 5-link 상단 바 (모든 페이지 공유)

---

## API Endpoints

| Method | Endpoint | 설명 | 키움 API |
|--------|----------|------|----------|
| GET | `/api/v3/indices` | KOSPI/KOSDAQ + NASDAQ | ka20001 + Yahoo |
| GET | `/api/v3/smart-money` | 3사 통합 진정성 TOP 5 | ka10039 + ka10001 |
| GET | `/api/v3/institutions` | 3사 순매수/순매도 TOP 5 | ka10039 |
| GET | `/api/v3/market-stats` | 외국인/기관 순매수 집계 | ka90009 + ka20001 |
| GET | `/api/v3/mismatches` | 기관 언행불일치 감지 | ka10039 |
| GET | `/api/v3/stock/<code>` | 종목 상세 팝업 | ka10001 |
| GET | `/api/v3/sectors` | 섹터 히트맵 | ka20003 |
| GET | `/api/v3/foreign-top` | 외국인 TOP 20 (5일) | pykrx |
| GET | `/api/v3/analysis` | AI 정량분석 내러티브 | 캐시 집계 |
| GET | `/api/conviction` | Conviction Signal | ka90009 + pykrx + ka10131 |

### API 공통 응답 형식

```json
{
  "status": "ok",
  "data": { ... },
  "cached": false
}
```

실패 시 캐시된 데이터 자동 반환 (`"cached": true`).

---

## 핵심 개념

### Conviction Signal

외국인 순매수 TOP 10과 개인 순매도의 **교집합** 종목을 찾아 점수화합니다.

```
Conviction Score (0~100) =
  외국인 매수 강도  (35점) — TOP 10 내 상대 순위
+ 개인 매도 강도    (25점) — 공포 매도 크기
+ 외국인 연속 매수  (20점) — ka10131 연속매수일
+ 개인 연속 매도    (10점) — 공포 지속 기간
+ 거래대금 지배력   (10점) — 외국인 비중
```

- 장중: 개인 매도 = -(외국인 + 기관) 역산 추정
- 장마감 후(16시~): pykrx 확정 데이터 자동 전환

### Smart Money Intensity

3사(MS/JP/GS) 통합 진정성 점수입니다.

```
Intensity = 기관중복 보너스(Triple=40/Double=20) + 금액비중 × 60
```

- 복수 기관 동시 매수 종목에 가중치 (TRIPLE/DOUBLE 뱃지)

### 기관 코드 매핑

| 기관 | 회원사 코드 (mmcm_cd) |
|------|---------------------|
| Morgan Stanley | 036 |
| JP Morgan | 033 |
| Goldman Sachs | 045 |

---

## 설정 (.env)

```env
# 키움 REST API
KIWOOM_APPKEY=your_appkey
KIWOOM_SECRETKEY=your_secretkey

# Flask
DEBUG=false
SECRET_KEY=your_secret_key
REFRESH_INTERVAL=30000
```

키움 API 미설정 시 `DISCONNECTED` 모드로 기동 (토큰 발급 실패 → API 호출 불가).

### 키움 REST API 규격

- **도메인**: `https://api.kiwoom.com` (운영) / `https://mockapi.kiwoom.com` (모의)
- **Method**: POST, Content-Type: `application/json;charset=UTF-8`
- **인증**: Header `authorization: Bearer {token}` (au10001로 발급)
- **Rate limit**: `time.sleep(0.3)` 필수
- **종목코드**: `_NX`, `_AL` suffix 자동 제거

---

## 디자인 시스템

### Dashboard (index.html) — White Theme

| 요소 | 값 |
|------|-----|
| 배경 | #F8F9FB |
| 카드 | #FFFFFF, border: #F1F5F9, shadow: subtle |
| 상승 | #DC2626 (빨강, 한국 관례) |
| 하락 | #2563EB (파랑) |
| 외국인 | #EA580C (딥 오렌지) |
| 기관 | #1D4ED8 (딥 블루) |
| Conviction Zone | Dark (#0F172A → #1E293B), 골드 accent (#F59E0B) |

### Articles (wsj/radar/etf/column) — Dark Theme

| 요소 | 값 |
|------|-----|
| 배경 | #0a0a12 |
| 골드 accent | #F59E0B |
| 카테고리 | WSJ=amber, Radar=blue, ETF=cyan, Column=pink |
| Muze AI 워터마크 | 전 페이지 |

---

## 개발 히스토리

| 버전 | 날짜 | 주요 변경 |
|------|------|-----------|
| v1.0 | 2026-02-05 | Morgan Dive → AX RADAR 피벗, 3사 기관 분리 |
| v2.0 | 2026-02-05 | Blueprint v2, 프리미엄 UI 설계 |
| v3.0 | 2026-02-06 | 화이트 테마, 키움 REST API 전면 연동 |
| v3.1 | 2026-02-06 | 더미 데이터 제거, 실제 API 데이터만 사용 |
| v3.2 | 2026-02-06 | 지수 마이너스 버그, JP Morgan 코드(033) 수정 |
| v4.1 | 2026-02-07 | Conviction Signal + Premium UI + 멀티페이지(5 pages) |
| v4.2 | 2026-02-08 | AI Market Analysis 내러티브 + 레이아웃 정제 |
| v4.4 | 2026-02-08 | Smart Money Intelligence + sparklines + insight badges |

---

*Built with Flask, Kiwoom REST API, pykrx, Chart.js, Phosphor Icons*
*Powered by Muze AI*
