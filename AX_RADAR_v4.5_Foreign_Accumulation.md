# AX RADAR v4.5 — Foreign Accumulation Radar 구현 명세서

> **목표**: 외국인 매수 비중 증가율을 추적하는 "Stealth Accumulation" 핵심 서비스 추가
> **작업 기준**: 기존 AX RADAR v4.4 코드베이스에 신규 모듈 + API + UI 추가

---

## 1. 프로젝트 컨텍스트

### 1.1 기존 코드베이스 구조

```
morgan_dive_v2/
├── .env                        # KIWOOM_APPKEY, KIWOOM_SECRETKEY
├── app.py                      # Flask 서버 + 전체 API 라우트
├── config.py                   # 기관 코드, 섹터맵, 환경변수
├── requirements.txt
├── modules/
│   ├── __init__.py
│   ├── kiwoom.py               # TokenManager + KiwoomAPI + KiwoomLogic
│   ├── conviction.py           # ConvictionEngine (외국인 ∩ 개인 → Score)
│   └── analysis.py             # MarketAnalyzer (데이터 → 내러티브)
└── templates/
    ├── index.html              # Daily X 대시보드 (White Theme, 30초 갱신)
    ├── article_base.html       # Article 공통 레이아웃 (Dark Theme)
    ├── wsj.html / radar.html / etf.html / column.html
```

### 1.2 기존 키움 API 연동 패턴

`modules/kiwoom.py`의 `KiwoomAPI` 클래스를 통해 모든 API 호출을 수행합니다.

```python
# 기존 호출 패턴 (참고용)
class KiwoomAPI:
    BASE_URL = "https://api.kiwoom.com"
    
    def _call(self, api_id: str, url: str, body: dict) -> dict:
        headers = {
            "api-id": api_id,
            "authorization": f"Bearer {self.token_manager.get_token()}",
            "cont-yn": "",
            "next-key": "",
            "Content-Type": "application/json;charset=UTF-8"
        }
        resp = requests.post(f"{self.BASE_URL}{url}", headers=headers, json=body)
        time.sleep(0.3)  # Rate limit 필수
        return resp.json()
```

### 1.3 기존 캐시 패턴

모든 API 응답은 in-memory 딕셔너리에 캐시됩니다. 실패 시 캐시된 데이터를 자동 반환합니다.

```python
# 기존 캐시 패턴
_cache = {}

def get_with_cache(cache_key, fetch_fn, ttl=30):
    now = time.time()
    if cache_key in _cache and (now - _cache[cache_key]['ts']) < ttl:
        return _cache[cache_key]['data']
    try:
        data = fetch_fn()
        _cache[cache_key] = {'data': data, 'ts': now}
        return data
    except:
        if cache_key in _cache:
            return _cache[cache_key]['data']
        return None
```

---

## 2. 신규 기능: Foreign Accumulation Radar

### 2.1 개념 정의

**외국인 매수 비중 증가율 (Foreign Accumulation Rate)**

기존 Conviction Signal이 "오늘 외국인이 뭘 사고 있나" (단기 수급)를 보여준다면,
Foreign Accumulation Radar는 **"외국인이 조용히 지분을 늘리고 있는 종목"** (중기 축적 트렌드)을 잡아냅니다.

- 비중이 꾸준히 올라가면서 한도소진율도 같이 올라가는 종목 = **기관의 진짜 확신 매수**
- 개인 투자자에게는 보이지 않는 "스텔스 축적" 패턴을 시각화

### 2.2 서비스명

- 영문: **Foreign Accumulation Radar** (줄여서 **FA Radar**)
- 한글: **외국인 스텔스 축적 레이더**
- 대시보드 섹션명: **🔍 Stealth Accumulation**

---

## 3. 사용할 키움 REST API 상세 스펙

### 3.1 ka10008 — 주식외국인종목별매매동향 ⭐ 핵심

> 종목별 외국인 보유비중(wght) 시계열 데이터 → 비중 증가율 계산의 핵심

**Request**:
- Method: POST
- URL: `/api/dostk/frgnistt`
- api-id: `ka10008`

```json
{
  "stk_cd": "005930"      // 종목코드 (필수)
}
```

**Response** (`stk_frgnr` 리스트):

| 필드 | 한글명 | 설명 | 활용 |
|------|--------|------|------|
| `dt` | 일자 | YYYYMMDD | 시계열 기준 |
| `close_pric` | 종가 | 부호포함 (+/-) | 주가 참조 |
| `pred_pre` | 전일대비 | 부호포함 | 등락 참조 |
| `trde_qty` | 거래량 | | 거래량 참조 |
| `chg_qty` | 변동수량 | 외국인 순매수/매도 수량 | **매수 강도 계산** |
| `poss_stkcnt` | 보유주식수 | 외국인 현재 보유 주식수 | **보유량 추이** |
| `wght` | 비중 | 외국인 보유 비중 (%) | ⭐ **비중 증가율 핵심** |
| `gain_pos_stkcnt` | 취득가능주식수 | 추가 매수 가능 수량 | 여력 참조 |
| `frgnr_limit` | 외국인한도 | 전체 한도 주식수 | 한도 대비 비율 |
| `frgnr_limit_irds` | 외국인한도증감 | 한도 변동 | 한도 변경 감지 |
| `limit_exh_rt` | 한도소진률 | 한도 대비 보유 비율 (%) | **소진율 추이** |

**Response Example**:
```json
{
  "stk_frgnr": [
    {
      "dt": "20241105",
      "close_pric": "135300",
      "pred_pre": "0",
      "trde_qty": "0",
      "chg_qty": "0",
      "poss_stkcnt": "6663509",
      "wght": "+26.10",
      "gain_pos_stkcnt": "18863197",
      "frgnr_limit": "25526706",
      "frgnr_limit_irds": "0",
      "limit_exh_rt": "+26.10"
    }
  ],
  "return_code": 0,
  "return_msg": "정상적으로 처리되었습니다"
}
```

**주의사항**:
- `wght`, `limit_exh_rt` 값에 `+` 접두사 붙어옴 → `float(val.replace('+',''))` 파싱 필요
- `chg_qty` 양수=순매수, 음수=순매도
- 연속조회(cont-yn/next-key)로 과거 데이터 페이징 가능

---

### 3.2 ka10036 — 외인한도소진율증가상위 ⭐ 1차 스크리닝

> 한도소진율이 급증한 종목을 기간별로 순위 조회 → 1차 필터링용

**Request**:
- Method: POST
- URL: `/api/dostk/rkinfo`
- api-id: `ka10036`

```json
{
  "mrkt_tp": "000",     // 000:전체, 001:코스피, 101:코스닥
  "dt": "5",            // 0:당일, 1:전일, 5:5일, 10:10일, 20:20일, 60:60일
  "stex_tp": "1"        // 1:KRX, 2:NXT, 3:통합
}
```

**Response** (`for_limit_exh_rt_incrs_upper` 리스트):

| 필드 | 한글명 | 설명 | 활용 |
|------|--------|------|------|
| `rank` | 순위 | | 스크리닝 순위 |
| `stk_cd` | 종목코드 | | 종목 식별 |
| `stk_nm` | 종목명 | | 종목명 표시 |
| `cur_prc` | 현재가 | | 가격 표시 |
| `pred_pre_sig` | 전일대비기호 | 1:상한,2:상승,3:보합,4:하한,5:하락 | 등락 표시 |
| `pred_pre` | 전일대비 | | 등락폭 |
| `trde_qty` | 거래량 | | 유동성 참조 |
| `poss_stkcnt` | 보유주식수 | | 보유량 |
| `gain_pos_stkcnt` | 취득가능주식수 | | 매수여력 |
| `base_limit_exh_rt` | 기준한도소진율 | 기간 시작 시점 소진율 | **변화 기준점** |
| `limit_exh_rt` | 한도소진율 | 현재 소진율 | **현재 수준** |
| `exh_rt_incrs` | 소진율증가 | 기간 내 증가폭 (%p) | ⭐ **핵심 지표** |

**Response Example**:
```json
{
  "for_limit_exh_rt_incrs_upper": [
    {
      "rank": "1",
      "stk_cd": "005930",
      "stk_nm": "삼성전자",
      "cur_prc": "14255",
      "pred_pre_sig": "3",
      "pred_pre": "0",
      "trde_qty": "0",
      "poss_stkcnt": "0",
      "gain_pos_stkcnt": "600000",
      "base_limit_exh_rt": "-283.33",
      "limit_exh_rt": "0.00",
      "exh_rt_incrs": "+283.33"
    }
  ],
  "return_code": 0,
  "return_msg": "정상적으로 처리되었습니다"
}
```

---

### 3.3 ka10034 — 외인기간별매매상위 (보조)

> 기간별 외국인 순매수 TOP → 매수 모멘텀 교차 확인

**Request**:
- Method: POST
- URL: `/api/dostk/rkinfo`
- api-id: `ka10034`

```json
{
  "mrkt_tp": "001",     // 000:전체, 001:코스피, 101:코스닥
  "trde_tp": "2",       // 1:순매도, 2:순매수, 3:순매매
  "dt": "5",            // 0:당일, 1:전일, 5:5일, 10:10일, 20:20일, 60:60일
  "stex_tp": "1"        // 1:KRX, 2:NXT, 3:통합
}
```

**Response** (`for_dt_trde_upper` 리스트):

| 필드 | 한글명 | 활용 |
|------|--------|------|
| `rank` | 순위 | TOP N 확인 |
| `stk_cd` | 종목코드 | 종목 식별 |
| `stk_nm` | 종목명 | 표시 |
| `cur_prc` | 현재가 | 가격 |
| `pred_pre_sig` | 전일대비기호 | 등락 |
| `pred_pre` | 전일대비 | 등락폭 |
| `sel_bid` | 매도호가 | |
| `buy_bid` | 매수호가 | |
| `trde_qty` | 거래량 | |
| `netprps_qty` | 순매수량 | **순매수 규모** |
| `gain_pos_stkcnt` | 취득가능주식수 | 매수 여력 |

---

### 3.4 ka10131 — 기관외국인연속매매현황 (기존 사용중)

> 이미 conviction.py에서 사용 중. 외국인 연속매수일 데이터.
> Foreign Accumulation Score에도 재활용.

---

### 3.5 ka10009 — 주식기관요청 (보조)

> 종목별 기관/외국인 일별순매매 + 외국인지분율

**Request**:
- Method: POST
- URL: `/api/dostk/frgnistt`
- api-id: `ka10009`

```json
{
  "stk_cd": "005930"
}
```

**Response 주요 필드**:

| 필드 | 한글명 | 활용 |
|------|--------|------|
| `date` | 날짜 | |
| `close_pric` | 종가 | |
| `orgn_daly_nettrde` | 기관일별순매매 | 기관 동반 매수 확인 |
| `frgnr_daly_nettrde` | 외국인일별순매매 | 외국인 일별 순매매 |
| `frgnr_qota_rt` | 외국인지분율 | **지분율 직접 조회** |

---

## 4. Accumulation Score 산출 로직

### 4.1 점수 체계 (0~100점)

```
Foreign Accumulation Score =

  ① 비중 변화율       (30점) — ka10008 wght의 5일/20일 증가폭
  ② 한도소진율 증가   (25점) — ka10036 exh_rt_incrs
  ③ 연속매수일         (20점) — ka10131 연속매수일 수
  ④ 순매수 금액 순위   (15점) — ka10034 기간별 매매 TOP 내 위치
  ⑤ 거래량 대비 매수비중 (10점) — ka10008 chg_qty / trde_qty
```

### 4.2 각 항목 세부 계산

#### ① 비중 변화율 (30점)

```python
def calc_weight_change_score(wght_today: float, wght_5d_ago: float, wght_20d_ago: float) -> float:
    """
    ka10008에서 가져온 비중(wght) 시계열로 계산
    - 5일 변화: 단기 축적 (가중치 60%)
    - 20일 변화: 중기 축적 (가중치 40%)
    """
    change_5d = wght_today - wght_5d_ago   # ex: 26.10 - 25.80 = +0.30%p
    change_20d = wght_today - wght_20d_ago  # ex: 26.10 - 25.20 = +0.90%p
    
    # 정규화: 0.5%p 이상 변화 → 만점
    score_5d = min(change_5d / 0.5 * 100, 100) * 0.6
    score_20d = min(change_20d / 1.0 * 100, 100) * 0.4
    
    raw = score_5d + score_20d
    return min(raw / 100 * 30, 30)  # 30점 만점 스케일링
```

#### ② 한도소진율 증가 (25점)

```python
def calc_exhaustion_score(exh_rt_incrs: float) -> float:
    """
    ka10036의 exh_rt_incrs 값 직접 사용
    - 1%p 이상 증가 → 만점 기준
    """
    normalized = min(abs(exh_rt_incrs) / 1.0, 1.0)
    return normalized * 25
```

#### ③ 연속매수일 (20점)

```python
def calc_consecutive_score(consecutive_days: int) -> float:
    """
    ka10131 연속매수일 (기존 conviction.py 로직 재활용)
    - 5일 이상 연속매수 → 만점
    """
    return min(consecutive_days / 5, 1.0) * 20
```

#### ④ 순매수 금액 순위 (15점)

```python
def calc_ranking_score(rank_in_top: int, total_ranked: int = 30) -> float:
    """
    ka10034 기간별 매매 TOP 내 순위
    - 1위 → 15점, 30위 → 0.5점
    """
    if rank_in_top <= 0 or rank_in_top > total_ranked:
        return 0
    return (1 - (rank_in_top - 1) / total_ranked) * 15
```

#### ⑤ 거래량 대비 매수비중 (10점)

```python
def calc_volume_dominance_score(chg_qty: int, trde_qty: int) -> float:
    """
    ka10008의 chg_qty(변동수량) / trde_qty(거래량)
    - 외국인 매수가 전체 거래량의 30% 이상 → 만점
    """
    if trde_qty <= 0:
        return 0
    ratio = abs(chg_qty) / trde_qty
    return min(ratio / 0.3, 1.0) * 10
```

### 4.3 종합 점수 + 등급

```python
GRADE_THRESHOLDS = {
    'S': 80,    # Stealth Conviction — 강력 축적
    'A': 60,    # Active Accumulation — 적극 축적
    'B': 40,    # Building Position — 포지션 구축 중
    'C': 20,    # Casual Interest — 관심 수준
}

def get_grade(score: float) -> str:
    for grade, threshold in GRADE_THRESHOLDS.items():
        if score >= threshold:
            return grade
    return 'D'  # Minimal Activity
```

---

## 5. 백엔드 구현

### 5.1 신규 파일: `modules/accumulation.py`

```python
"""
Foreign Accumulation Radar Engine

주요 클래스:
- AccumulationEngine: 외국인 매수비중 증가율 분석 엔진

의존성:
- modules.kiwoom.KiwoomAPI (기존)
- modules.kiwoom.KiwoomLogic (기존)
"""

import time
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class AccumulationEngine:
    """외국인 스텔스 축적 분석 엔진"""
    
    def __init__(self, kiwoom_api):
        """
        Args:
            kiwoom_api: KiwoomAPI 인스턴스 (기존 modules/kiwoom.py)
        """
        self.api = kiwoom_api
        self._cache = {}
    
    # ── 1차 스크리닝: 한도소진율 급증 종목 ──
    
    def get_exhaustion_surge_stocks(self, market: str = "000", period: str = "5") -> List[dict]:
        """
        ka10036: 외인한도소진율증가상위 호출
        
        Args:
            market: "000"(전체), "001"(코스피), "101"(코스닥)
            period: "0"(당일), "1"(전일), "5"(5일), "10"(10일), "20"(20일), "60"(60일)
        
        Returns:
            [{"stk_cd", "stk_nm", "exh_rt_incrs", "limit_exh_rt", "base_limit_exh_rt", ...}]
        """
        body = {
            "mrkt_tp": market,
            "dt": period,
            "stex_tp": "1"  # KRX
        }
        result = self.api._call("ka10036", "/api/dostk/rkinfo", body)
        items = result.get("for_limit_exh_rt_incrs_upper", [])
        return self._parse_exhaustion_items(items)
    
    # ── 2차 상세: 종목별 비중 시계열 ──
    
    def get_foreign_weight_history(self, stk_cd: str) -> List[dict]:
        """
        ka10008: 주식외국인종목별매매동향
        종목의 일별 외국인 비중(wght), 보유주식수, 한도소진율 시계열 반환
        
        Args:
            stk_cd: 종목코드 (예: "005930")
        
        Returns:
            [{"dt", "wght", "poss_stkcnt", "chg_qty", "trde_qty", "limit_exh_rt", ...}]
        """
        body = {"stk_cd": stk_cd}
        result = self.api._call("ka10008", "/api/dostk/frgnistt", body)
        items = result.get("stk_frgnr", [])
        return self._parse_weight_items(items)
    
    # ── 3차 보조: 기간별 순매수 TOP ──
    
    def get_foreign_period_top(self, market: str = "001", period: str = "5") -> List[dict]:
        """
        ka10034: 외인기간별매매상위
        
        Args:
            market: 시장구분
            period: 기간
        
        Returns:
            [{"rank", "stk_cd", "stk_nm", "netprps_qty", ...}]
        """
        body = {
            "mrkt_tp": market,
            "trde_tp": "2",   # 순매수
            "dt": period,
            "stex_tp": "1"
        }
        result = self.api._call("ka10034", "/api/dostk/rkinfo", body)
        return result.get("for_dt_trde_upper", [])
    
    # ── 종합 분석: Accumulation Score 산출 ──
    
    def analyze(self, top_n: int = 15) -> List[dict]:
        """
        전체 파이프라인 실행:
        1. ka10036으로 한도소진율 급증 종목 스크리닝 (5일 + 20일)
        2. 각 종목별 ka10008로 비중 시계열 조회
        3. ka10034로 순매수 순위 교차 확인
        4. ka10131 연속매수일 데이터 결합 (기존 로직)
        5. Accumulation Score 산출 및 정렬
        
        Args:
            top_n: 최종 반환할 상위 종목 수 (기본 15)
        
        Returns:
            [{
                "rank": 1,
                "stk_cd": "005930",
                "stk_nm": "삼성전자",
                "cur_prc": "+74800",
                "pred_pre": "+1200",
                "pred_pre_sig": "2",
                "accumulation_score": 82.5,
                "grade": "S",
                "wght_now": 26.10,
                "wght_5d_ago": 25.80,
                "wght_20d_ago": 25.20,
                "wght_change_5d": 0.30,
                "wght_change_20d": 0.90,
                "exh_rt_incrs": 0.45,
                "consecutive_days": 7,
                "period_rank": 3,
                "volume_dominance": 0.22,
                "detail_scores": {
                    "weight_change": 24.0,
                    "exhaustion": 11.3,
                    "consecutive": 20.0,
                    "ranking": 13.5,
                    "volume": 7.3
                },
                "signal": "STEALTH_CONVICTION",
                "sparkline": [25.2, 25.4, 25.5, 25.7, 25.8, 26.1]
            }]
        """
        pass  # 아래 구현 가이드 참조
    
    # ── 내부 헬퍼 ──
    
    @staticmethod
    def _parse_num(val: str) -> float:
        """키움 API 숫자 파싱: '+26.10' → 26.10, '-3441' → -3441.0"""
        if not val:
            return 0.0
        return float(str(val).replace('+', '').replace(',', ''))
    
    def _parse_exhaustion_items(self, items: list) -> list:
        """ka10036 응답 정규화"""
        parsed = []
        for item in items:
            parsed.append({
                "rank": int(item.get("rank", 0)),
                "stk_cd": item.get("stk_cd", "").replace("_NX", "").replace("_AL", ""),
                "stk_nm": item.get("stk_nm", ""),
                "cur_prc": item.get("cur_prc", "0"),
                "pred_pre_sig": item.get("pred_pre_sig", "3"),
                "pred_pre": item.get("pred_pre", "0"),
                "poss_stkcnt": self._parse_num(item.get("poss_stkcnt", "0")),
                "base_limit_exh_rt": self._parse_num(item.get("base_limit_exh_rt", "0")),
                "limit_exh_rt": self._parse_num(item.get("limit_exh_rt", "0")),
                "exh_rt_incrs": self._parse_num(item.get("exh_rt_incrs", "0")),
            })
        return parsed
    
    def _parse_weight_items(self, items: list) -> list:
        """ka10008 응답 정규화"""
        parsed = []
        for item in items:
            parsed.append({
                "dt": item.get("dt", ""),
                "close_pric": self._parse_num(item.get("close_pric", "0")),
                "chg_qty": self._parse_num(item.get("chg_qty", "0")),
                "trde_qty": self._parse_num(item.get("trde_qty", "0")),
                "poss_stkcnt": self._parse_num(item.get("poss_stkcnt", "0")),
                "wght": self._parse_num(item.get("wght", "0")),
                "limit_exh_rt": self._parse_num(item.get("limit_exh_rt", "0")),
            })
        return parsed
```

### 5.2 `analyze()` 메서드 구현 가이드

```python
def analyze(self, top_n: int = 15) -> List[dict]:
    results = []
    
    # Step 1: 1차 스크리닝 — 5일 + 20일 한도소진율 증가 종목 합집합
    surge_5d = self.get_exhaustion_surge_stocks(market="000", period="5")
    surge_20d = self.get_exhaustion_surge_stocks(market="000", period="20")
    
    # 합집합 (중복 시 5일 데이터 우선)
    candidates = {}
    for item in surge_20d + surge_5d:
        cd = item["stk_cd"]
        if cd not in candidates:
            candidates[cd] = item
        else:
            # 5일 데이터로 덮어쓰기 (더 최신)
            candidates[cd].update(item)
    
    # Step 2: 기간별 순매수 TOP 매핑 (순위 참조용)
    period_top_5d = self.get_foreign_period_top(market="001", period="5")
    period_top_map = {}
    for item in period_top_5d:
        cd = item.get("stk_cd", "").replace("_NX", "").replace("_AL", "")
        rank = int(item.get("rank", 0))
        if cd and rank > 0:
            period_top_map[cd] = rank
    
    # Step 3: 각 후보 종목 상세 분석
    for stk_cd, screening_data in candidates.items():
        time.sleep(0.3)  # Rate limit
        
        # ka10008: 비중 시계열
        weight_history = self.get_foreign_weight_history(stk_cd)
        if not weight_history or len(weight_history) < 2:
            continue
        
        # 비중 시계열에서 5일전, 20일전 추출
        wght_now = weight_history[0]["wght"]  # 최신
        wght_5d = weight_history[min(4, len(weight_history)-1)]["wght"]
        wght_20d = weight_history[min(19, len(weight_history)-1)]["wght"]
        
        # 스파크라인용 최근 비중 추이 (최대 20일, 오래된 것부터)
        sparkline = [h["wght"] for h in reversed(weight_history[:20])]
        
        # 거래량 대비 매수비중 (최근 1일)
        latest = weight_history[0]
        vol_dominance = (abs(latest["chg_qty"]) / latest["trde_qty"]
                         if latest["trde_qty"] > 0 else 0)
        
        # 연속매수일 (ka10131 — 기존 conviction.py 로직 호출)
        # consecutive_days = self.get_consecutive_buy_days(stk_cd)
        consecutive_days = 0  # 기존 로직 연결 필요
        
        # 순매수 순위
        period_rank = period_top_map.get(stk_cd, 0)
        
        # ── Score 계산 ──
        s1 = calc_weight_change_score(wght_now, wght_5d, wght_20d)
        s2 = calc_exhaustion_score(screening_data["exh_rt_incrs"])
        s3 = calc_consecutive_score(consecutive_days)
        s4 = calc_ranking_score(period_rank)
        s5 = calc_volume_dominance_score(latest["chg_qty"], latest["trde_qty"])
        
        total_score = s1 + s2 + s3 + s4 + s5
        grade = get_grade(total_score)
        
        # 시그널 결정
        signal = "STEALTH_CONVICTION" if grade == "S" else \
                 "ACTIVE_ACCUMULATION" if grade == "A" else \
                 "BUILDING_POSITION" if grade == "B" else \
                 "WATCHING"
        
        results.append({
            "stk_cd": stk_cd,
            "stk_nm": screening_data["stk_nm"],
            "cur_prc": screening_data["cur_prc"],
            "pred_pre": screening_data["pred_pre"],
            "pred_pre_sig": screening_data["pred_pre_sig"],
            "accumulation_score": round(total_score, 1),
            "grade": grade,
            "wght_now": wght_now,
            "wght_5d_ago": wght_5d,
            "wght_20d_ago": wght_20d,
            "wght_change_5d": round(wght_now - wght_5d, 2),
            "wght_change_20d": round(wght_now - wght_20d, 2),
            "exh_rt_incrs": screening_data["exh_rt_incrs"],
            "consecutive_days": consecutive_days,
            "period_rank": period_rank,
            "volume_dominance": round(vol_dominance, 4),
            "detail_scores": {
                "weight_change": round(s1, 1),
                "exhaustion": round(s2, 1),
                "consecutive": round(s3, 1),
                "ranking": round(s4, 1),
                "volume": round(s5, 1),
            },
            "signal": signal,
            "sparkline": sparkline,
        })
    
    # 점수 내림차순 정렬 후 순위 부여
    results.sort(key=lambda x: x["accumulation_score"], reverse=True)
    for i, item in enumerate(results[:top_n]):
        item["rank"] = i + 1
    
    return results[:top_n]
```

### 5.3 app.py에 추가할 라우트

```python
# ── app.py에 추가 ──

from modules.accumulation import AccumulationEngine

# 초기화 (기존 kiwoom_api 인스턴스 재활용)
accumulation_engine = AccumulationEngine(kiwoom_api)

@app.route('/api/v3/accumulation')
def api_accumulation():
    """Foreign Accumulation Radar API"""
    try:
        data = get_with_cache(
            'accumulation_radar',
            lambda: accumulation_engine.analyze(top_n=15),
            ttl=120  # 2분 캐시 (API 호출량 고려)
        )
        return jsonify({"status": "ok", "data": data, "cached": False})
    except Exception as e:
        logger.error(f"Accumulation API error: {e}")
        cached = _cache.get('accumulation_radar')
        if cached:
            return jsonify({"status": "ok", "data": cached['data'], "cached": True})
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/v3/accumulation/<stk_cd>')
def api_accumulation_detail(stk_cd):
    """종목별 외국인 비중 시계열 상세"""
    try:
        history = accumulation_engine.get_foreign_weight_history(stk_cd)
        return jsonify({"status": "ok", "data": history})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
```

---

## 6. 프론트엔드 구현

### 6.1 대시보드 배치 (index.html)

**위치**: 기존 Conviction Zone 섹션 바로 아래에 신규 섹션 추가

```
┌─────────────────────────────────────────────────────┐
│  [기존] Navigation Bar (5 links)                     │
├─────────────────────────────────────────────────────┤
│  [기존] 지수 카드 (KOSPI/KOSDAQ/NASDAQ)              │
├─────────────────────────────────────────────────────┤
│  [기존] Smart Money Intensity TOP 5                  │
├─────────────────────────────────────────────────────┤
│  [기존] 3사 기관 추적 (MS/JP/GS)                     │
├─────────────────────────────────────────────────────┤
│  [기존] Conviction Zone (Dark BG)                    │
├─────────────────────────────────────────────────────┤
│  [신규] 🔍 Stealth Accumulation Zone (Dark BG)      │  ← 여기
│  │ "외국인이 조용히 축적 중인 종목"                      │
│  │                                                   │
│  │ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐    │
│  │ │ S등급 │ │ A등급 │ │ A등급 │ │ B등급 │ │ B등급 │    │
│  │ │ 삼성전│ │ SK하이│ │ LG에너│ │ 카카오│ │ NAVER │    │
│  │ │ 82.5  │ │ 71.2  │ │ 65.8  │ │ 48.3  │ │ 42.1  │    │
│  │ │ ▁▃▅▇ │ │ ▂▄▆█ │ │ ▃▅▇█ │ │ ▁▂▃▅ │ │ ▂▃▄▅ │    │
│  │ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘    │
│  │                                                   │
│  │ [전체 15종목 테이블 - 스크롤]                       │
│  └───────────────────────────────────────────────────│
├─────────────────────────────────────────────────────┤
│  [기존] AI 정량분석                                   │
└─────────────────────────────────────────────────────┘
```

### 6.2 UI 디자인 스펙

#### Stealth Accumulation Zone

```css
/* 배경: Conviction Zone과 동일한 다크 톤 */
background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
border-radius: 16px;
padding: 32px;
margin: 24px 0;

/* Accent 색상 */
--stealth-green: #10B981;     /* 축적 = 초록 계열 (성장 느낌) */
--stealth-emerald: #059669;   /* 진한 초록 */
--grade-s: #F59E0B;           /* S등급 = 골드 (기존과 통일) */
--grade-a: #10B981;           /* A등급 = 에메랄드 */
--grade-b: #3B82F6;           /* B등급 = 블루 */
--grade-c: #6B7280;           /* C등급 = 그레이 */
```

#### 종목 카드 디자인

```html
<div class="accumulation-card" data-grade="S">
  <div class="card-header">
    <span class="grade-badge grade-s">S</span>
    <span class="stock-name">삼성전자</span>
    <span class="stock-code">005930</span>
  </div>
  
  <div class="score-display">
    <span class="score-value">82.5</span>
    <span class="score-label">Accumulation Score</span>
  </div>
  
  <!-- 비중 변화 스파크라인 (Canvas 또는 SVG) -->
  <div class="sparkline-container">
    <canvas class="weight-sparkline" width="120" height="40"></canvas>
  </div>
  
  <div class="weight-change">
    <div class="change-item">
      <span class="label">5D</span>
      <span class="value positive">+0.30%p</span>
    </div>
    <div class="change-item">
      <span class="label">20D</span>
      <span class="value positive">+0.90%p</span>
    </div>
  </div>
  
  <div class="signal-badge">STEALTH CONVICTION</div>
</div>
```

#### 전체 테이블 (TOP 15)

```html
<table class="accumulation-table">
  <thead>
    <tr>
      <th>#</th>
      <th>종목</th>
      <th>Score</th>
      <th>Grade</th>
      <th>비중(현재)</th>
      <th>5D 변화</th>
      <th>20D 변화</th>
      <th>소진율↑</th>
      <th>연속매수</th>
      <th>비중 추이</th>
      <th>Signal</th>
    </tr>
  </thead>
  <tbody>
    <!-- JavaScript로 동적 렌더링 -->
  </tbody>
</table>
```

### 6.3 JavaScript Fetch 로직

```javascript
// 기존 30초 갱신 사이클에 추가
async function fetchAccumulation() {
    try {
        const resp = await fetch('/api/v3/accumulation');
        const json = await resp.json();
        if (json.status === 'ok') {
            renderAccumulationCards(json.data.slice(0, 5));  // 상위 5개 카드
            renderAccumulationTable(json.data);               // 전체 테이블
        }
    } catch (err) {
        console.error('Accumulation fetch error:', err);
    }
}

function renderAccumulationCards(items) {
    const container = document.getElementById('accumulation-cards');
    container.innerHTML = items.map(item => `
        <div class="accumulation-card" data-grade="${item.grade}" 
             onclick="showStockPopup('${item.stk_cd}')">
            <div class="card-header">
                <span class="grade-badge grade-${item.grade.toLowerCase()}">${item.grade}</span>
                <span class="stock-name">${item.stk_nm}</span>
            </div>
            <div class="score-display">
                <span class="score-value">${item.accumulation_score}</span>
            </div>
            <canvas class="weight-sparkline" 
                    data-values="${item.sparkline.join(',')}">
            </canvas>
            <div class="weight-change">
                <span class="change-5d ${item.wght_change_5d >= 0 ? 'positive' : 'negative'}">
                    5D: ${item.wght_change_5d >= 0 ? '+' : ''}${item.wght_change_5d}%p
                </span>
                <span class="change-20d ${item.wght_change_20d >= 0 ? 'positive' : 'negative'}">
                    20D: ${item.wght_change_20d >= 0 ? '+' : ''}${item.wght_change_20d}%p
                </span>
            </div>
            <div class="signal-badge signal-${item.signal.toLowerCase()}">${item.signal.replace('_', ' ')}</div>
        </div>
    `).join('');
    
    // 스파크라인 렌더링
    container.querySelectorAll('.weight-sparkline').forEach(drawSparkline);
}

function drawSparkline(canvas) {
    const values = canvas.dataset.values.split(',').map(Number);
    const ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height;
    const min = Math.min(...values), max = Math.max(...values);
    const range = max - min || 1;
    
    ctx.clearRect(0, 0, w, h);
    ctx.beginPath();
    ctx.strokeStyle = '#10B981';
    ctx.lineWidth = 2;
    
    values.forEach((v, i) => {
        const x = (i / (values.length - 1)) * w;
        const y = h - ((v - min) / range) * (h - 4) - 2;
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
    
    // 영역 채우기
    ctx.lineTo(w, h);
    ctx.lineTo(0, h);
    ctx.closePath();
    ctx.fillStyle = 'rgba(16, 185, 129, 0.1)';
    ctx.fill();
}

// 갱신 사이클에 추가
setInterval(fetchAccumulation, 120000);  // 2분마다 (API 부하 고려)
fetchAccumulation();  // 초기 로드
```

---

## 7. Rate Limit & 성능 최적화

### 7.1 API 호출량 추산

| 단계 | API | 호출 수 | 비고 |
|------|-----|---------|------|
| 1차 스크리닝 | ka10036 × 2 (5일, 20일) | 2 | 기간별 1회 |
| 2차 순매수 TOP | ka10034 × 1 | 1 | 코스피 5일 |
| 3차 종목별 상세 | ka10008 × N | ~30 | 후보 종목 수 |
| **합계** | | **~33회** | × 0.3초 = **~10초** |

### 7.2 최적화 전략

```python
# 1. TTL을 120초(2분)으로 설정 — 기존 30초보다 길게
# 2. 1차 스크리닝 결과를 별도 캐시하여 재활용
# 3. 장중(09:00~15:30)에만 자동 갱신, 장마감 후 1회 확정 분석
# 4. 후보 종목 수 제한: TOP 30까지만 상세 조회

ACCUMULATION_TTL = 120  # 2분
CANDIDATE_LIMIT = 30    # 상세 조회 최대 종목 수
```

---

## 8. 기존 Conviction Signal과의 통합

### 8.1 크로스 시그널: Stealth Conviction

```python
def find_stealth_conviction(conviction_data, accumulation_data):
    """
    Conviction Signal (단기 수급) + Accumulation Radar (중기 축적)
    양쪽 모두에 등장하는 종목 = 최고 확신도
    
    - Conviction: 외국인 순매수 ∩ 개인 순매도 (오늘)
    - Accumulation: 외국인 비중 꾸준히 증가 (5~20일)
    - 교집합: 오늘도 사고 있고, 며칠째 계속 사고 있음 → "진짜 확신"
    """
    conviction_codes = {item["stk_cd"] for item in conviction_data}
    accumulation_codes = {item["stk_cd"] for item in accumulation_data if item["grade"] in ("S", "A")}
    
    stealth = conviction_codes & accumulation_codes
    return stealth  # 이 종목들에 ⭐ 특별 뱃지 부여
```

### 8.2 UI 통합

Conviction Zone과 Accumulation Zone 양쪽에 모두 등장하는 종목에는
**"⚡ Stealth Conviction"** 골드 뱃지를 추가합니다.

---

## 9. 체크리스트

### 백엔드
- [ ] `modules/accumulation.py` 생성
- [ ] `AccumulationEngine` 클래스 구현
- [ ] `analyze()` 전체 파이프라인 구현
- [ ] `_parse_num()` 유틸리티 (키움 API 숫자 파싱)
- [ ] 기존 `conviction.py`의 연속매수일 로직 재활용 연결
- [ ] `app.py`에 `/api/v3/accumulation` 라우트 추가
- [ ] `app.py`에 `/api/v3/accumulation/<stk_cd>` 라우트 추가
- [ ] 캐시 TTL 120초 설정
- [ ] 에러 핸들링 + 캐시 폴백

### 프론트엔드
- [ ] index.html에 Stealth Accumulation Zone 섹션 추가
- [ ] 상위 5개 카드 UI (등급별 색상, 스파크라인)
- [ ] 전체 15종목 테이블 UI
- [ ] 비중 추이 스파크라인 (Canvas)
- [ ] fetchAccumulation() + 2분 갱신 사이클
- [ ] 종목 클릭 → 기존 상세 팝업 연동
- [ ] Stealth Conviction 크로스 뱃지

### 통합 & 테스트
- [ ] Conviction Signal과 크로스 시그널 로직
- [ ] API 응답 형식 일관성 확인 (status/data/cached)
- [ ] Rate limit 준수 확인 (0.3초 간격)
- [ ] 장중/장마감 후 동작 분기 확인
- [ ] 캐시 미스 시 폴백 동작 확인

---

## 10. 참고: 키움 API 공통 규격

- **도메인**: `https://api.kiwoom.com` (운영)
- **Method**: POST
- **Content-Type**: `application/json;charset=UTF-8`
- **인증**: Header `authorization: Bearer {token}`
- **api-id**: 각 API별 고유 ID (Header)
- **연속조회**: `cont-yn: Y` + `next-key` 값으로 페이징
- **Rate limit**: `time.sleep(0.3)` 필수
- **종목코드**: `_NX`, `_AL` suffix 자동 제거 필요
- **숫자 필드**: `+/-` 접두사 + 문자열 → float 변환 필요

---

*AX RADAR v4.5 — Foreign Accumulation Radar*
*Powered by Muze AI*
