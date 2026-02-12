"""
AX RADAR v4.5 — Foreign Accumulation Radar Engine

외국인 매수 비중 증가율을 추적하는 "Stealth Accumulation" 분석 엔진.
ka10036(한도소진율증가상위) + ka10008(외국인종목별매매동향) + ka10034(외인기간별매매상위)
→ Accumulation Score(0~100) 산출.
"""
import logging
import time
from typing import List

logger = logging.getLogger("accumulation")

# ── Grade Thresholds ──
GRADE_THRESHOLDS = {
    "S": 80,  # Stealth Conviction
    "A": 60,  # Active Accumulation
    "B": 40,  # Building Position
    "C": 20,  # Casual Interest
}

SIGNAL_MAP = {
    "S": "STEALTH_CONVICTION",
    "A": "ACTIVE_ACCUMULATION",
    "B": "BUILDING_POSITION",
    "C": "WATCHING",
    "D": "WATCHING",
}


# ═══════════════════════════════════════════════════════════════════
#  Score Calculation Functions
# ═══════════════════════════════════════════════════════════════════

def calc_weight_change_score(wght_now: float, wght_5d: float, wght_20d: float) -> float:
    """① 비중 변화율 (30점). 5D 60% + 20D 40%."""
    change_5d = wght_now - wght_5d
    change_20d = wght_now - wght_20d

    score_5d = min(max(change_5d / 0.5, 0), 1.0) * 0.6
    score_20d = min(max(change_20d / 1.0, 0), 1.0) * 0.4

    raw = (score_5d + score_20d) * 100
    return min(raw / 100 * 30, 30)


def calc_exhaustion_score(exh_rt_incrs: float) -> float:
    """② 한도소진율 증가 (25점). 1%p 이상 → 만점."""
    normalized = min(abs(exh_rt_incrs) / 1.0, 1.0)
    return normalized * 25


def calc_consecutive_score(consecutive_days: int) -> float:
    """③ 연속매수일 (20점). 5일 이상 → 만점."""
    return min(consecutive_days / 5, 1.0) * 20


def calc_ranking_score(rank_in_top: int, total_ranked: int = 30) -> float:
    """④ 순매수 금액 순위 (15점). 1위→15점, 30위→0.5점."""
    if rank_in_top <= 0 or rank_in_top > total_ranked:
        return 0
    return (1 - (rank_in_top - 1) / total_ranked) * 15


def calc_volume_dominance_score(chg_qty: float, trde_qty: float) -> float:
    """⑤ 거래량 대비 매수비중 (10점). 30% 이상 → 만점."""
    if trde_qty <= 0:
        return 0
    ratio = abs(chg_qty) / trde_qty
    return min(ratio / 0.3, 1.0) * 10


def get_grade(score: float) -> str:
    for grade, threshold in GRADE_THRESHOLDS.items():
        if score >= threshold:
            return grade
    return "D"


# ═══════════════════════════════════════════════════════════════════
#  AccumulationEngine
# ═══════════════════════════════════════════════════════════════════

class AccumulationEngine:
    """외국인 스텔스 축적 분석 엔진."""

    CANDIDATE_LIMIT = 30  # 상세 조회 최대 종목 수

    def __init__(self, kiwoom_logic):
        """
        Args:
            kiwoom_logic: KiwoomLogic 인스턴스 (기존 modules/kiwoom.py)
        """
        self.logic = kiwoom_logic
        self.api = kiwoom_logic._api

    # ── Parsing helper ──

    @staticmethod
    def _pn(val) -> float:
        """키움 API 숫자 파싱: '+26.10' → 26.10, '-3441' → -3441.0"""
        if not val:
            return 0.0
        try:
            return float(str(val).replace("+", "").replace(",", "").strip())
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _clean_code(code: str) -> str:
        return str(code).replace("_NX", "").replace("_AL", "").strip()

    # ── 1차 스크리닝: ka10036 한도소진율증가상위 ──

    def get_exhaustion_surge_stocks(self, market: str = "000", period: str = "5") -> list:
        body = {"mrkt_tp": market, "dt": period, "stex_tp": "1"}
        result = self.api.call("ka10036", "/api/dostk/rkinfo", body)
        items = result.get("for_limit_exh_rt_incrs_upper", [])
        if not items:
            for k, v in result.items():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    items = v
                    break
        return self._parse_exhaustion_items(items)

    # ── 2차 상세: ka10008 외국인종목별매매동향 ──

    def get_foreign_weight_history(self, stk_cd: str) -> list:
        body = {"stk_cd": stk_cd}
        result = self.api.call("ka10008", "/api/dostk/frgnistt", body)
        items = result.get("stk_frgnr", [])
        if not items:
            for k, v in result.items():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    items = v
                    break
        return self._parse_weight_items(items)

    # ── 3차 보조: ka10034 외인기간별매매상위 ──

    def get_foreign_period_top(self, market: str = "001", period: str = "5") -> list:
        body = {"mrkt_tp": market, "trde_tp": "2", "dt": period, "stex_tp": "1"}
        result = self.api.call("ka10034", "/api/dostk/rkinfo", body)
        items = result.get("for_dt_trde_upper", [])
        if not items:
            for k, v in result.items():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    items = v
                    break
        return items

    # ── 종합 분석 파이프라인 ──

    def analyze(self, top_n: int = 15) -> list:
        results = []

        # Step 1: 1차 스크리닝 — 5일 + 20일 한도소진율 증가 종목 합집합
        try:
            surge_5d = self.get_exhaustion_surge_stocks(market="000", period="5")
        except Exception as e:
            logger.warning(f"ka10036 5d error: {e}")
            surge_5d = []

        time.sleep(0.3)

        try:
            surge_20d = self.get_exhaustion_surge_stocks(market="000", period="20")
        except Exception as e:
            logger.warning(f"ka10036 20d error: {e}")
            surge_20d = []

        # 합집합 (5일 데이터 우선)
        candidates = {}
        for item in surge_20d + surge_5d:
            cd = item["stk_cd"]
            if cd and len(cd) == 6:
                if cd not in candidates:
                    candidates[cd] = item
                else:
                    candidates[cd].update(item)

        if not candidates:
            logger.warning("Accumulation: no candidates from screening")
            return []

        # Step 2: 기간별 순매수 TOP 매핑
        time.sleep(0.3)
        period_top_map = {}
        try:
            period_top_5d = self.get_foreign_period_top(market="001", period="5")
            for item in period_top_5d:
                cd = self._clean_code(item.get("stk_cd", ""))
                rank = int(item.get("rank", 0)) if item.get("rank") else 0
                if cd and len(cd) == 6 and rank > 0:
                    period_top_map[cd] = rank
        except Exception as e:
            logger.warning(f"ka10034 error: {e}")

        # Step 3: 각 후보 종목 상세 분석 (최대 CANDIDATE_LIMIT개)
        candidate_list = list(candidates.items())[:self.CANDIDATE_LIMIT]

        for stk_cd, screening_data in candidate_list:
            time.sleep(0.3)

            try:
                weight_history = self.get_foreign_weight_history(stk_cd)
            except Exception as e:
                logger.debug(f"ka10008 [{stk_cd}] error: {e}")
                continue

            if not weight_history or len(weight_history) < 2:
                continue

            # 비중 시계열에서 5일전, 20일전 추출
            wght_now = weight_history[0]["wght"]
            wght_5d = weight_history[min(4, len(weight_history) - 1)]["wght"]
            wght_20d = weight_history[min(19, len(weight_history) - 1)]["wght"]

            # 스파크라인용 최근 비중 추이 (오래된 것부터)
            sparkline = [h["wght"] for h in reversed(weight_history[:20])]

            # 거래량 대비 매수비중 (최근 1일)
            latest = weight_history[0]
            vol_dominance = (
                abs(latest["chg_qty"]) / latest["trde_qty"]
                if latest["trde_qty"] > 0
                else 0
            )

            # 연속매수일 추정: weight_history에서 chg_qty > 0인 연속일 수
            consecutive_days = 0
            for h in weight_history:
                if h["chg_qty"] > 0:
                    consecutive_days += 1
                else:
                    break

            # 순매수 순위
            period_rank = period_top_map.get(stk_cd, 0)

            # Score 계산
            s1 = calc_weight_change_score(wght_now, wght_5d, wght_20d)
            s2 = calc_exhaustion_score(screening_data["exh_rt_incrs"])
            s3 = calc_consecutive_score(consecutive_days)
            s4 = calc_ranking_score(period_rank)
            s5 = calc_volume_dominance_score(latest["chg_qty"], latest["trde_qty"])

            total_score = s1 + s2 + s3 + s4 + s5
            grade = get_grade(total_score)
            signal = SIGNAL_MAP.get(grade, "WATCHING")

            results.append({
                "stk_cd": stk_cd,
                "stk_nm": screening_data["stk_nm"],
                "cur_prc": screening_data["cur_prc"],
                "pred_pre": screening_data["pred_pre"],
                "pred_pre_sig": screening_data["pred_pre_sig"],
                "accumulation_score": round(total_score, 1),
                "grade": grade,
                "wght_now": round(wght_now, 2),
                "wght_5d_ago": round(wght_5d, 2),
                "wght_20d_ago": round(wght_20d, 2),
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

        logger.info(f"Accumulation analysis complete: {len(results[:top_n])} stocks")
        return results[:top_n]

    # ── 내부 파서 ──

    def _parse_exhaustion_items(self, items: list) -> list:
        parsed = []
        for item in items:
            cd = self._clean_code(item.get("stk_cd", ""))
            if not cd or len(cd) != 6:
                continue
            parsed.append({
                "rank": int(item.get("rank", 0)) if item.get("rank") else 0,
                "stk_cd": cd,
                "stk_nm": str(item.get("stk_nm", "")).strip(),
                "cur_prc": str(item.get("cur_prc", "0")),
                "pred_pre_sig": str(item.get("pred_pre_sig", "3")),
                "pred_pre": str(item.get("pred_pre", "0")),
                "poss_stkcnt": self._pn(item.get("poss_stkcnt", "0")),
                "base_limit_exh_rt": self._pn(item.get("base_limit_exh_rt", "0")),
                "limit_exh_rt": self._pn(item.get("limit_exh_rt", "0")),
                "exh_rt_incrs": self._pn(item.get("exh_rt_incrs", "0")),
            })
        return parsed

    def _parse_weight_items(self, items: list) -> list:
        parsed = []
        for item in items:
            parsed.append({
                "dt": item.get("dt", ""),
                "close_pric": self._pn(item.get("close_pric", "0")),
                "chg_qty": self._pn(item.get("chg_qty", "0")),
                "trde_qty": self._pn(item.get("trde_qty", "0")),
                "poss_stkcnt": self._pn(item.get("poss_stkcnt", "0")),
                "wght": self._pn(item.get("wght", "0")),
                "limit_exh_rt": self._pn(item.get("limit_exh_rt", "0")),
            })
        return parsed
