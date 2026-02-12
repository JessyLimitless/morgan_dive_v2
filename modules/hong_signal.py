"""
홍인기 대왕개미 전략 — 매수 신호 스캐너
═══════════════════════════════════════════════════════════════════

Signal 1: 프로그램 순매수 기울기 양전환 (ka90005)
  - 시간대별 프로그램 순매수 누적금액의 기울기(slope) 계산
  - 기울기가 0→양 전환 시 = 프로그램 자금 유입 시작
  - 기울기가 양 + 가속 시 = 매수세 강화 (ACCELERATING)

Signal 2: 기관 가집계 순매수 증가 (ka10065)
  - 종목별 기관 잠정 순매수 수량을 주기적으로 추적
  - 연속 N회 증가 = 기관이 해당 종목을 축적 중

Combined: 프로그램 기울기 양전환 + 기관 가집계 증가 = 매수 후보
═══════════════════════════════════════════════════════════════════
"""
import logging
import time
from collections import defaultdict, deque
from datetime import datetime

logger = logging.getLogger("hong_signal")


# ═══════════════════════════════════════════════════════════════════
#  Utility: 단순 선형회귀 기울기
# ═══════════════════════════════════════════════════════════════════

def calc_slope(values: list, window: int = 10) -> float:
    """
    최근 `window`개 데이터의 선형회귀 기울기 계산.
    양수 = 상승 추세, 음수 = 하락 추세.
    """
    if len(values) < 2:
        return 0.0
    data = values[-window:]
    n = len(data)
    x_mean = (n - 1) / 2.0
    y_mean = sum(data) / n
    numer = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(data))
    denom = sum((i - x_mean) ** 2 for i in range(n))
    return numer / denom if denom != 0 else 0.0


# ═══════════════════════════════════════════════════════════════════
#  HongSignalScanner
# ═══════════════════════════════════════════════════════════════════

class HongSignalScanner:
    """
    홍인기 매수 신호 스캐너

    사용법:
        scanner = HongSignalScanner(kiwoom_logic)
        result  = scanner.scan(["005930", "000660", "035420"])

    result 구조:
        {
            "timestamp": "2026-02-09 10:30:15",
            "program": {
                "slope": 12.5,
                "trend": "ACCELERATING",
                "positive": True,
                "cumNet": 1234567,
                ...
            },
            "marketReady": True,
            "signals": [              # 매수 신호 (프로그램 OK + 기관 증가)
                {"code": "005930", "name": "삼성전자", "instNet": 5000, ...},
            ],
            "watchlist": [            # 관심 종목 (기관 증가 중, 프로그램 미확인)
                {"code": "000660", "name": "SK하이닉스", ...},
            ],
        }
    """

    def __init__(self, kiwoom_logic):
        self.kiwoom = kiwoom_logic

        # ── 기관 가집계 이력 저장소 (종목별) ──
        self._inst_history = defaultdict(lambda: deque(maxlen=30))
        self._inst_ts = defaultdict(lambda: deque(maxlen=30))

        # ═══════════════ 전략 파라미터 (튜닝 가능) ═══════════════
        self.program_slope_window = 10      # 기울기 계산 구간 (시간대 포인트 수)
        self.inst_increase_count = 3        # 기관 가집계 연속 증가 판정 기준
        self.min_inst_net = 500             # 최소 기관 순매수 수량(주) 필터
        self.min_sector_count = 3           # 주도 섹터 판정: 동일 업종 최소 종목 수

    # ═══════════════════════════════════════════════════════════════
    #  Phase 1: 프로그램 매수 기울기 분석 (ka90005)
    # ═══════════════════════════════════════════════════════════════

    def get_program_slope(self, mrkt_tp: str = "0") -> dict:
        """
        프로그램 순매수 기울기 분석.
        ka10065 orgn_tp=9000 (프로그램 가집계 랭킹) 총 순매수를 추적하여 기울기 산출.

        Returns:
            slope      — 기울기 값 (양수=매수세 유입)
            positive   — 기울기 양전환 여부
            cumNet     — 프로그램 총 순매수
            trend      — ACCELERATING / POSITIVE / FLAT / NEGATIVE / COLLECTING / NO_DATA
            dataPoints — 분석 데이터 포인트 수
        """
        # ── ka10065 프로그램 가집계 랭킹 ──
        try:
            prog_ranking = self.kiwoom.get_provisional_ranking(
                orgn_tp="9000", trde_tp="1", mrkt_tp=mrkt_tp
            )
        except Exception as e:
            logger.warning(f"Program ranking error: {e}")
            prog_ranking = []

        # 총 프로그램 순매수 계산
        total_net = sum(s["netQty"] for s in prog_ranking) if prog_ranking else 0

        # 시계열 추적
        if not hasattr(self, "_prog_history"):
            self._prog_history = deque(maxlen=60)
        self._prog_history.append(total_net)

        cum_values = list(self._prog_history)

        if not prog_ranking:
            return {
                "slope": 0, "positive": False, "cumNet": 0,
                "latestNet": 0, "dataPoints": 0, "trend": "NO_DATA",
            }

        if len(cum_values) < 2:
            return {
                "slope": 0, "positive": total_net > 0, "cumNet": total_net,
                "latestNet": total_net, "dataPoints": 1, "trend": "COLLECTING",
            }

        # ── 기울기 계산 ──
        slope = calc_slope(cum_values, self.program_slope_window)

        # ── 가속도 판정: 전반부 vs 후반부 기울기 비교 ──
        accelerating = False
        if len(cum_values) > self.program_slope_window:
            half = len(cum_values) // 2
            slope_1st = calc_slope(cum_values[:half], min(half, self.program_slope_window))
            slope_2nd = calc_slope(cum_values[half:], min(len(cum_values) - half, self.program_slope_window))
            accelerating = slope_2nd > slope_1st and slope_2nd > 0

        # ── 추세 판정 ──
        if accelerating:
            trend = "ACCELERATING"
        elif slope > 0:
            trend = "POSITIVE"
        elif abs(slope) < 1:
            trend = "FLAT"
        else:
            trend = "NEGATIVE"

        return {
            "slope": round(slope, 2),
            "positive": slope > 0,
            "cumNet": total_net,
            "latestNet": total_net,
            "dataPoints": len(cum_values),
            "trend": trend,
        }

    # ═══════════════════════════════════════════════════════════════
    #  Phase 2: 기관 가집계 추적 (ka10065)
    # ═══════════════════════════════════════════════════════════════

    def update_inst_provisional(self, stock_codes: list) -> dict:
        """
        ka10065 호출로 종목별 기관 가집계 업데이트 및 추세 판정.

        Returns: {
            "005930": {
                "instNet": 5000,      # 현재 기관 순매수
                "foreignNet": 3000,   # 외국인 순매수
                "programNet": 2000,   # 프로그램 순매수
                "delta": 500,         # 직전 대비 변화량
                "consecutive": 4,     # 연속 증가 횟수
                "increasing": True,   # 증가 판정 (consecutive >= 기준)
            },
            ...
        }
        """
        results = {}
        now = time.time()

        for code in stock_codes:
            try:
                prov = self.kiwoom.get_inst_provisional(code)
                inst_net = prov["instNet"]

                history = self._inst_history[code]
                ts_history = self._inst_ts[code]

                # 이전 값 대비 변화량
                delta = inst_net - history[-1] if history else 0

                history.append(inst_net)
                ts_history.append(now)

                # 연속 증가 횟수 계산 (뒤에서부터 탐색)
                consecutive = 0
                vals = list(history)
                for i in range(len(vals) - 1, 0, -1):
                    if vals[i] > vals[i - 1]:
                        consecutive += 1
                    else:
                        break

                results[code] = {
                    "instNet": inst_net,
                    "foreignNet": prov["foreignNet"],
                    "programNet": prov["programNet"],
                    "delta": delta,
                    "consecutive": consecutive,
                    "increasing": consecutive >= self.inst_increase_count,
                    "samples": len(history),
                }
            except Exception as e:
                logger.warning(f"ka10065 [{code}] error: {e}")
                results[code] = {"error": str(e)}

        return results

    # ═══════════════════════════════════════════════════════════════
    #  Phase 3: 통합 스캔 — 매수 신호 조합
    # ═══════════════════════════════════════════════════════════════

    def scan(self, stock_codes: list, mrkt_tp: str = "0") -> dict:
        """
        홍인기 전략 통합 스캔.

        1. 프로그램 기울기 확인 (마켓 타이밍)
        2. 기관 가집계 업데이트 (종목 선별)
        3. 매수 신호 조합

        Args:
            stock_codes: 스캔 대상 종목코드 리스트
            mrkt_tp: "0"=KOSPI, "1"=KOSDAQ

        Returns:
            signals   — 매수 신호 (프로그램 OK + 기관 증가)
            watchlist — 관심 종목 (기관 증가, 프로그램 미확인)
        """
        # ── Phase 1: 마켓 타이밍 ──
        program = self.get_program_slope(mrkt_tp)
        market_ready = program["positive"]

        # ── Phase 2: 종목별 기관 가집계 ──
        inst_data = self.update_inst_provisional(stock_codes)

        # ── Phase 3: 신호 조합 ──
        signals = []
        watchlist = []

        for code, data in inst_data.items():
            if "error" in data:
                continue
            if not data["increasing"]:
                continue
            if data["instNet"] < self.min_inst_net:
                continue

            # 종목명 조회
            name = code
            try:
                info = self.kiwoom.get_stock_info(code)
                name = info.get("name", code)
            except Exception:
                pass

            entry = {
                "code": code,
                "name": name,
                "instNet": data["instNet"],
                "foreignNet": data["foreignNet"],
                "programNet": data["programNet"],
                "delta": data["delta"],
                "consecutive": data["consecutive"],
                "strength": data["consecutive"] * abs(data["instNet"]),  # 신호 강도
            }

            if market_ready:
                signals.append(entry)
            else:
                watchlist.append(entry)

        # 신호 강도 기준 정렬
        signals.sort(key=lambda x: -x["strength"])
        watchlist.sort(key=lambda x: -x["strength"])

        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "program": program,
            "marketReady": market_ready,
            "signals": signals,
            "watchlist": watchlist,
            "scannedCount": len(stock_codes),
        }

    # ═══════════════════════════════════════════════════════════════
    #  Phase 4: 수급 주도주 전략 — 통합 시그널 스캔
    # ═══════════════════════════════════════════════════════════════

    def scan_strategy(self, mrkt_tp: str = "0") -> dict:
        """
        홍인기 수급 주도주 전략 — 풀 스캔.

        1. ka10032 거래대금 상위 50종목
        2. 업종 클러스터링 → 동일 업종 3+개 = 주도 섹터
        3. ka90005 프로그램 매매 기울기 + 가속 판정
        4. 주도 섹터 종목 중 ka10065 기관 가집계 연속 증가 필터
        5. 조합: 주도섹터 + 프로그램 OK + 기관 증가 = SIGNAL

        Returns:
            program        — 프로그램 매매 추이 분석
            leadingSectors — 주도 섹터 {업종명: {count, stocks}}
            signals        — 최종 시그널 [{code, name, sector, level, ...}]
            totalScanned   — 스캔 종목 수
        """
        now = datetime.now()
        is_market_hours = (
            now.weekday() < 5
            and now.hour >= 9 and (now.hour > 9 or now.minute >= 30)
            and now.hour < 16
        )

        # ── Phase 1: 거래대금 상위 종목 ──
        try:
            top_stocks = self.kiwoom.get_top_volume_stocks(mrkt_tp, count=50)
        except Exception as e:
            logger.warning(f"ka10032 error: {e}")
            top_stocks = []

        # ── Phase 2: 업종 클러스터링 ──
        sector_map = self.kiwoom._get_sector_map()
        sector_clusters = defaultdict(list)
        for stock in top_stocks:
            sector = sector_map.get(stock["code"], "기타")
            sector_clusters[sector].append(stock)

        leading_sectors = {}
        for sector, stocks in sector_clusters.items():
            if sector == "기타":
                continue
            if len(stocks) >= self.min_sector_count:
                leading_sectors[sector] = {
                    "count": len(stocks),
                    "stocks": [
                        {
                            "code": s["code"],
                            "name": s["name"],
                            "tradeAmt": s["tradeAmt"],
                            "changePct": s["changePct"],
                        }
                        for s in stocks
                    ],
                }

        # ── Phase 3: 프로그램 기울기 ──
        program = self.get_program_slope(mrkt_tp)

        # ── Phase 4: 주도 섹터 종목의 기관 가집계 체크 (ka10065 랭킹) ──
        leading_codes = []
        code_sector_map = {}
        code_stock_map = {}
        for sec_name, sec_data in leading_sectors.items():
            for s in sec_data["stocks"]:
                leading_codes.append(s["code"])
                code_sector_map[s["code"]] = sec_name
                code_stock_map[s["code"]] = s

        # 기관 가집계 랭킹 (한 번의 호출로 100종목)
        try:
            inst_ranking = self.kiwoom.get_provisional_ranking(
                orgn_tp="9100", trde_tp="1", mrkt_tp=mrkt_tp
            )
        except Exception as e:
            logger.warning(f"Institutional ranking error: {e}")
            inst_ranking = []

        inst_map = {s["code"]: s["netQty"] for s in inst_ranking}

        # 프로그램 가집계 (교차 확인용)
        try:
            prog_ranking = self.kiwoom.get_provisional_ranking(
                orgn_tp="9000", trde_tp="1", mrkt_tp=mrkt_tp
            )
        except Exception:
            prog_ranking = []
        prog_map = {s["code"]: s["netQty"] for s in prog_ranking}

        signals = []
        now_ts = time.time()

        for code in leading_codes:
            inst_net = inst_map.get(code, 0)

            # 이력 추적 및 연속 증가 판정
            history = self._inst_history[code]
            ts_history = self._inst_ts[code]

            delta = inst_net - history[-1] if history else 0
            history.append(inst_net)
            ts_history.append(now_ts)

            consecutive = 0
            vals = list(history)
            for i in range(len(vals) - 1, 0, -1):
                if vals[i] > vals[i - 1]:
                    consecutive += 1
                else:
                    break

            is_inst_increasing = consecutive >= self.inst_increase_count

            stock_info = code_stock_map.get(code, {})
            sector = code_sector_map.get(code, "기타")

            is_program_ok = program["positive"]
            is_accelerating = program["trend"] == "ACCELERATING"

            # 시그널 레벨 판정
            if is_program_ok and is_inst_increasing and is_accelerating:
                level = "STRONG"
            elif is_program_ok and is_inst_increasing:
                level = "ACTIVE"
            elif is_inst_increasing:
                level = "WATCH"
            elif inst_net > 0 and code in inst_map:
                level = "WATCH"  # 기관 순매수 중이면 관심 목록
            else:
                continue

            entry = {
                "code": code,
                "name": stock_info.get("name", code),
                "sector": sector,
                "tradeAmt": stock_info.get("tradeAmt", 0),
                "changePct": stock_info.get("changePct", 0),
                "instNet": inst_net,
                "foreignNet": 0,
                "programNet": prog_map.get(code, 0),
                "delta": delta,
                "consecutive": consecutive,
                "level": level,
                "explosive": is_accelerating and consecutive >= 5,
            }
            signals.append(entry)

        # 시그널 정렬: STRONG > ACTIVE > WATCH, 같은 레벨 내 기관 순매수 크기순
        level_priority = {"STRONG": 0, "ACTIVE": 1, "WATCH": 2}
        signals.sort(key=lambda x: (level_priority.get(x["level"], 9), -abs(x["instNet"])))

        return {
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "marketHours": is_market_hours,
            "program": program,
            "leadingSectors": leading_sectors,
            "leadingSectorCount": len(leading_sectors),
            "signals": signals,
            "totalScanned": len(top_stocks),
        }
