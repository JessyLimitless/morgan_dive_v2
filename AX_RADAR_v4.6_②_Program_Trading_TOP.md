# AX RADAR v4.6 — ② 프로그램 매매 순매수 TOP 50

> **목표**: 당일 프로그램 순매수 상위 50 종목을 대시보드에 테이블로 추가
> **선행 작업**: ① AX_RADAR_v4.5_Foreign_Accumulation.md 완료 후 진행
> **난이도**: 낮음 (API 1개, UI 테이블 1개)

---

## 1. 개요

프로그램 매매(알고리즘 자동매매)로 당일 순매수가 많은 종목 TOP 50을 보여주는 단순한 테이블입니다.
별도 점수 산출이나 기존 시그널과의 교차 분석 없이, **"오늘 프로그램이 뭘 사고 있나"**를 한눈에 보여주는 것이 목적입니다.

---

## 2. 사용할 키움 API

### ka90003 — 프로그램순매수상위50요청 (이것 하나만 사용)

**Request**:
- Method: POST
- URL: `/api/dostk/stkinfo`
- api-id: `ka90003`

```json
{
  "trde_upper_tp": "2",     // 1:순매도상위, 2:순매수상위
  "amt_qty_tp": "1",        // 1:금액, 2:수량
  "mrkt_tp": "P00101",      // P00101:코스피, P10102:코스닥
  "stex_tp": "1"            // 1:KRX, 2:NXT, 3:통합
}
```

**Response** (`prm_netprps_upper_50` 리스트):

| 필드 | 한글명 | 설명 |
|------|--------|------|
| `rank` | 순위 | |
| `stk_cd` | 종목코드 | |
| `stk_nm` | 종목명 | |
| `cur_prc` | 현재가 | 부호 포함 |
| `flu_sig` | 등락기호 | |
| `pred_pre` | 전일대비 | |
| `flu_rt` | 등락율 | |
| `acc_trde_qty` | 누적거래량 | |
| `prm_sell_amt` | 프로그램매도금액 | |
| `prm_buy_amt` | 프로그램매수금액 | |
| `prm_netprps_amt` | 프로그램순매수금액 | ⭐ 핵심 |

---

## 3. 백엔드 구현

### 3.1 app.py에 라우트 추가

```python
@app.route('/api/v3/program-top')
def api_program_top():
    """당일 프로그램 순매수 TOP 50"""
    try:
        data = get_with_cache(
            'program_top',
            lambda: _fetch_program_top(),
            ttl=30  # 30초 캐시 (당일 장중 데이터, 기존 갱신 주기와 동일)
        )
        return jsonify({"status": "ok", "data": data, "cached": False})
    except Exception as e:
        logger.error(f"Program TOP API error: {e}")
        cached = _cache.get('program_top')
        if cached:
            return jsonify({"status": "ok", "data": cached['data'], "cached": True})
        return jsonify({"status": "error", "message": str(e)}), 500


def _fetch_program_top():
    """코스피 + 코스닥 프로그램 순매수 TOP 50 통합"""
    
    # 코스피
    kospi = kiwoom_api._call("ka90003", "/api/dostk/stkinfo", {
        "trde_upper_tp": "2",
        "amt_qty_tp": "1",
        "mrkt_tp": "P00101",
        "stex_tp": "1"
    })
    time.sleep(0.3)
    
    # 코스닥
    kosdaq = kiwoom_api._call("ka90003", "/api/dostk/stkinfo", {
        "trde_upper_tp": "2",
        "amt_qty_tp": "1",
        "mrkt_tp": "P10102",
        "stex_tp": "1"
    })
    
    kospi_items = kospi.get("prm_netprps_upper_50", [])
    kosdaq_items = kosdaq.get("prm_netprps_upper_50", [])
    
    # 마켓 구분 태그 추가
    for item in kospi_items:
        item["market"] = "KOSPI"
    for item in kosdaq_items:
        item["market"] = "KOSDAQ"
    
    # 통합 후 순매수금액 기준 내림차순 정렬
    combined = kospi_items + kosdaq_items
    combined.sort(
        key=lambda x: abs(float(str(x.get("prm_netprps_amt", "0")).replace("+", "").replace("-", "").replace(",", "") or "0")),
        reverse=True
    )
    
    # 상위 50개 반환 + 순위 재부여
    result = []
    for i, item in enumerate(combined[:50]):
        result.append({
            "rank": i + 1,
            "stk_cd": item.get("stk_cd", "").replace("_NX", "").replace("_AL", ""),
            "stk_nm": item.get("stk_nm", ""),
            "market": item.get("market", ""),
            "cur_prc": item.get("cur_prc", "0"),
            "flu_sig": item.get("flu_sig", "3"),
            "pred_pre": item.get("pred_pre", "0"),
            "flu_rt": item.get("flu_rt", "0.00"),
            "acc_trde_qty": item.get("acc_trde_qty", "0"),
            "prm_sell_amt": item.get("prm_sell_amt", "0"),
            "prm_buy_amt": item.get("prm_buy_amt", "0"),
            "prm_netprps_amt": item.get("prm_netprps_amt", "0"),
        })
    
    return result
```

---

## 4. 프론트엔드 구현

### 4.1 대시보드 배치 (index.html)

**위치**: Stealth Accumulation Zone(①에서 추가한 섹션) 아래

```
┌─────────────────────────────────────────────────┐
│  [기존] Conviction Zone                          │
├─────────────────────────────────────────────────┤
│  [①] Stealth Accumulation Zone                  │
├─────────────────────────────────────────────────┤
│  [②] 🤖 Program Trading TOP                    │  ← 여기
│  │                                               │
│  │  테이블 (TOP 20 기본 표시, 펼치면 50)          │
│  │  #  종목  시장  현재가  등락률  순매수금액      │
│  │  1  삼성전자  KOSPI  74,800  +1.6%  +1,234억  │
│  │  2  SK하이닉스 KOSPI 210,000 +2.3%  +892억    │
│  │  ...                                          │
│  │  [더보기 → 50개 전체]                          │
│  └───────────────────────────────────────────────│
├─────────────────────────────────────────────────┤
│  [기존] AI 정량분석                               │
└─────────────────────────────────────────────────┘
```

### 4.2 UI 스펙

```css
/* 기존 White Theme 유지 (다크 섹션 아님) */
/* 기존 대시보드 테이블 스타일과 동일하게 */

.program-section {
    background: #FFFFFF;
    border: 1px solid #F1F5F9;
    border-radius: 12px;
    padding: 24px;
    margin: 24px 0;
}

.program-section .section-title {
    font-size: 16px;
    font-weight: 700;
    color: #0F172A;
    margin-bottom: 16px;
}

/* 순매수금액 강조 */
.program-net-positive { color: #DC2626; font-weight: 600; }  /* 빨강 = 매수 (한국 관례) */
.program-net-negative { color: #2563EB; }                     /* 파랑 = 매도 */
```

### 4.3 HTML 구조

```html
<div class="program-section">
    <div class="section-header">
        <h3 class="section-title">🤖 Program Trading TOP</h3>
        <span class="section-subtitle">당일 프로그램 순매수 상위</span>
    </div>
    
    <table class="program-table">
        <thead>
            <tr>
                <th>#</th>
                <th>종목</th>
                <th>시장</th>
                <th>현재가</th>
                <th>등락률</th>
                <th>프로그램 순매수</th>
            </tr>
        </thead>
        <tbody id="program-tbody">
            <!-- JS 동적 렌더링 -->
        </tbody>
    </table>
    
    <button id="program-toggle" class="toggle-btn" onclick="toggleProgramList()">
        더보기 ▼
    </button>
</div>
```

### 4.4 JavaScript

```javascript
let programShowAll = false;

async function fetchProgramTop() {
    try {
        const resp = await fetch('/api/v3/program-top');
        const json = await resp.json();
        if (json.status === 'ok') {
            window._programData = json.data;
            renderProgramTable(json.data);
        }
    } catch (err) {
        console.error('Program TOP fetch error:', err);
    }
}

function renderProgramTable(items) {
    const tbody = document.getElementById('program-tbody');
    const showCount = programShowAll ? 50 : 20;
    const display = items.slice(0, showCount);
    
    tbody.innerHTML = display.map(item => {
        const netAmt = parseFloat(String(item.prm_netprps_amt).replace(/[+,]/g, ''));
        const netClass = netAmt >= 0 ? 'program-net-positive' : 'program-net-negative';
        const fluRt = item.flu_rt;
        const priceClass = parseFloat(fluRt) >= 0 ? 'price-up' : 'price-down';
        
        return `<tr onclick="showStockPopup('${item.stk_cd}')">
            <td>${item.rank}</td>
            <td><strong>${item.stk_nm}</strong></td>
            <td><span class="market-badge market-${item.market.toLowerCase()}">${item.market}</span></td>
            <td>${formatPrice(item.cur_prc)}</td>
            <td class="${priceClass}">${fluRt}%</td>
            <td class="${netClass}">${formatAmount(item.prm_netprps_amt)}</td>
        </tr>`;
    }).join('');
    
    // 더보기 버튼 표시/숨김
    const toggleBtn = document.getElementById('program-toggle');
    if (items.length <= 20) {
        toggleBtn.style.display = 'none';
    } else {
        toggleBtn.textContent = programShowAll ? '접기 ▲' : '더보기 ▼';
    }
}

function toggleProgramList() {
    programShowAll = !programShowAll;
    if (window._programData) {
        renderProgramTable(window._programData);
    }
}

function formatAmount(val) {
    // 프로그램 순매수금액 포맷 (백만원 → 억원 변환)
    const num = parseFloat(String(val).replace(/[+,]/g, ''));
    if (isNaN(num)) return '-';
    const billion = num / 100;  // 백만 → 억
    const sign = num >= 0 ? '+' : '';
    return sign + billion.toFixed(0) + '억';
}

// 기존 30초 갱신 사이클에 추가
setInterval(fetchProgramTop, 30000);
fetchProgramTop();
```

---

## 5. 체크리스트

- [ ] app.py에 `/api/v3/program-top` 라우트 추가
- [ ] `_fetch_program_top()` 함수 구현 (코스피+코스닥 통합, 정렬)
- [ ] 캐시 TTL 30초, 에러 시 캐시 폴백
- [ ] index.html에 Program Trading TOP 섹션 추가
- [ ] 기본 20개 표시, 더보기 클릭 시 50개
- [ ] 종목 클릭 → 기존 상세 팝업 연동
- [ ] 기존 30초 갱신 사이클에 fetchProgramTop() 추가
- [ ] 숫자 파싱 (+/- 접두사), 종목코드 _NX/_AL 제거

---

## 6. API 호출량

| API | 호출 수 | 비고 |
|-----|---------|------|
| ka90003 × 2 (코스피, 코스닥) | 2회 | 30초마다 |
| **합계** | **2회/30초** | 기존 부하에 거의 영향 없음 |

---

## 7. 참고: 키움 API 공통 규격

- 도메인: `https://api.kiwoom.com`
- Method: POST, Content-Type: `application/json;charset=UTF-8`
- 인증: Header `authorization: Bearer {token}`
- Rate limit: `time.sleep(0.3)` 필수
- 종목코드: `_NX`, `_AL` suffix 자동 제거

---

*AX RADAR v4.6 — Program Trading TOP*
*Powered by Muze AI*
