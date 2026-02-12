"""
AX RADAR v5.3 - Kiwoom REST API Module
TokenManager + KiwoomAPI + KiwoomLogic
"""
import json
import logging
import os
import time
from datetime import datetime, timedelta

import requests

from config import (
    INDUSTRY_SECTORS,
    INDUSTRY_SECTOR_NAMES,
    INSTITUTION_CODES,
    KA10051_SECTOR_MAP,
    KIWOOM_APPKEY,
    KIWOOM_BASE_URL,
    KIWOOM_SECRETKEY,
)

logger = logging.getLogger("kiwoom")


# ═══════════════════════════════════════════════════════════════════
#  TokenManager — au10001 token lifecycle
# ═══════════════════════════════════════════════════════════════════

class TokenManager:
    """Kiwoom REST API OAuth2 token manager (au10001)."""

    def __init__(self):
        self.token: str = ""
        self.expires_at: datetime = datetime.min

    @property
    def is_valid(self) -> bool:
        return bool(self.token) and datetime.now() < self.expires_at

    def get_token(self) -> str:
        if self.is_valid:
            return self.token
        return self._issue_token()

    def _issue_token(self) -> str:
        url = f"{KIWOOM_BASE_URL}/oauth2/token"
        headers = {"api-id": "au10001", "Content-Type": "application/json;charset=UTF-8"}
        body = {
            "grant_type": "client_credentials",
            "appkey": KIWOOM_APPKEY,
            "secretkey": KIWOOM_SECRETKEY,
        }

        try:
            resp = requests.post(url, headers=headers, json=body, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            self.token = data.get("token", "")
            expires_dt = data.get("expires_dt", "")

            if expires_dt:
                self.expires_at = datetime.strptime(expires_dt, "%Y%m%d%H%M%S") - timedelta(minutes=5)
            else:
                self.expires_at = datetime.now() + timedelta(hours=23)

            logger.info(f"Token issued, expires {self.expires_at:%Y-%m-%d %H:%M}")
            return self.token

        except Exception as e:
            logger.error(f"Token issue failed: {e}")
            self.token = ""
            return ""


# ═══════════════════════════════════════════════════════════════════
#  KiwoomAPI — low-level REST wrapper
# ═══════════════════════════════════════════════════════════════════

class KiwoomAPI:
    """Kiwoom REST API POST wrapper with auto-token."""

    def __init__(self, token_mgr: TokenManager):
        self.token_mgr = token_mgr

    def call(self, api_id: str, path: str, body: dict, cont_key: str = "") -> dict:
        token = self.token_mgr.get_token()
        if not token:
            raise ConnectionError("No valid token")

        url = f"{KIWOOM_BASE_URL}{path}"
        headers = {
            "api-id": api_id,
            "authorization": f"Bearer {token}",
            "Content-Type": "application/json;charset=UTF-8",
        }
        if cont_key:
            headers["next-key"] = cont_key

        resp = requests.post(url, headers=headers, json=body, timeout=15)
        resp.raise_for_status()
        return resp.json()


# ═══════════════════════════════════════════════════════════════════
#  KiwoomLogic — business logic
# ═══════════════════════════════════════════════════════════════════

class KiwoomLogic:
    """High-level business logic for AX RADAR dashboard."""

    def __init__(self):
        self._tm = TokenManager()
        self._api = KiwoomAPI(self._tm)
        self._cache: dict = {}
        self._cache_ts: dict = {}
        self._cache_ttl = 60  # seconds

        # ax_universe.json
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        universe_path = os.path.join(base, "data", "ax_universe.json")
        try:
            with open(universe_path, "r", encoding="utf-8") as f:
                self.ax_universe = json.load(f)
        except Exception:
            self.ax_universe = {}

    @property
    def connected(self) -> bool:
        try:
            return bool(self._tm.get_token())
        except Exception:
            return False

    # ── Cache helpers ──

    def _set_cache(self, key: str, data):
        self._cache[key] = data
        self._cache_ts[key] = time.time()

    def _get_cache(self, key: str, ttl: int | None = None):
        if key not in self._cache:
            return None
        ts = self._cache_ts.get(key, 0)
        age = time.time() - ts
        if ttl and age > ttl:
            return None
        return self._cache[key]

    # ── Parsing helpers ──

    @staticmethod
    def _parse_int(val) -> int:
        if not val:
            return 0
        try:
            s = str(val).replace(",", "").replace("+", "").strip()
            neg = s.startswith("-")
            s = s.replace("-", "")
            if not s:
                return 0
            return -int(s) if neg else int(s)
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _parse_float(val) -> float:
        if not val:
            return 0.0
        try:
            return float(str(val).replace(",", "").replace("+", "").strip())
        except (ValueError, TypeError):
            return 0.0

    # ═══════════════ Institution Top (ka10039) ═══════════════

    def get_institution_top(self, inst_key: str, trade_type: str = "1", days: str = "5") -> list:
        """
        ka10039: Institution buy/sell top stocks.
        trade_type: "1"=buy, "2"=sell
        days: "1"=당일, "5"=5영업일 누적
        """
        inst = INSTITUTION_CODES.get(inst_key)
        if not inst:
            return []

        body = {
            "mmcm_cd": inst["code"],
            "trde_qty_tp": "0",
            "trde_tp": trade_type,
            "dt": days,
            "stex_tp": "3",
        }

        data = self._api.call("ka10039", "/api/dostk/rkinfo", body)
        items = data.get("sec_trde_upper", [])

        if not items:
            for k, v in data.items():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    items = v
                    break

        result = []
        for item in items[:20]:
            code = str(item.get("stk_cd", "")).replace("_AL", "").replace("_NX", "").strip()
            if not code or len(code) != 6:
                continue

            amt_raw = self._parse_int(item.get("netprps_amt", "0"))
            # netprps_amt 원본 단위: 천원(1,000원)
            # 천원 → 억원 변환: ÷100,000 (1억 = 100,000천원)
            amt_eok = round(amt_raw / 100_000, 1)
            flu = self._parse_float(item.get("flu_rt", "0"))

            result.append({
                "code": code,
                "name": str(item.get("stk_nm", "")).strip(),
                "amount": amt_eok,
                "changePct": flu,
            })

        # Sort by absolute amount descending
        result.sort(key=lambda x: abs(x["amount"]), reverse=True)
        return result

    # ═══════════════ Stock Info (ka10001) ═══════════════

    def get_stock_info(self, code: str) -> dict:
        """ka10001: Stock basic info for popup."""
        body = {"stk_cd": code}
        data = self._api.call("ka10001", "/api/dostk/stkinfo", body)

        sig = str(data.get("pred_pre_sig", "3"))
        cur = abs(self._parse_int(data.get("cur_prc", "0")))
        change = abs(self._parse_int(data.get("pred_pre", "0")))
        if sig in ("4", "5"):
            change = -change

        return {
            "code": code,
            "name": str(data.get("stk_nm", "")).strip(),
            "curPrc": cur,
            "change": change,
            "changePct": self._parse_float(data.get("flu_rt", "0")),
            "signal": sig,
            "open": abs(self._parse_int(data.get("open_pric", "0"))),
            "high": abs(self._parse_int(data.get("high_pric", "0"))),
            "low": abs(self._parse_int(data.get("low_pric", "0"))),
            "volume": self._parse_int(data.get("trde_qty", "0")),
            "marketCap": self._parse_int(data.get("mac", "0")),
            "per": self._parse_float(data.get("per", "0")),
            "pbr": self._parse_float(data.get("pbr", "0")),
            "foreignRate": self._parse_float(data.get("for_exh_rt", "0")),
        }

    # ═══════════════ Foreign Net Buy/Sell TOP 20 (pykrx) ═══════════════

    def get_foreign_top20(self) -> dict:
        """외국인 순매수/순매도 TOP 20 (최근 5영업일, pykrx 기반) + 당일 등락률"""
        cached = self._get_cache("foreign_top20_data", ttl=300)
        if cached:
            return cached

        from pykrx import stock as pykrx_stock

        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")

        df = pykrx_stock.get_market_net_purchases_of_equities_by_ticker(
            start, end, market="KOSPI", investor="외국인"
        )

        if df.empty:
            return {"buy": [], "sell": []}

        # 최근 거래일 등락률 가져오기 (주말/공휴일 대비 최근 7일 탐색)
        chg_map = {}
        try:
            for offset in range(0, 7):
                d = (datetime.now() - timedelta(days=offset)).strftime("%Y%m%d")
                ohlcv = pykrx_stock.get_market_ohlcv_by_ticker(d, market="KOSPI")
                if not ohlcv.empty and "등락률" in ohlcv.columns:
                    vol_col = [c for c in ohlcv.columns if "거래량" in c]
                    if vol_col and ohlcv[vol_col[0]].sum() > 0:
                        for code in ohlcv.index:
                            chg_map[str(code)] = round(float(ohlcv.at[code, "등락률"]), 2)
                        break
        except Exception as e:
            logger.warning(f"Foreign top20 changePct fetch error: {e}")

        amt_col = "순매수거래대금"
        name_col = "종목명"

        buy_df = df[df[amt_col] > 0].nlargest(20, amt_col)
        sell_df = df[df[amt_col] < 0].nsmallest(20, amt_col)

        def build_list(sub_df):
            items = []
            for code in sub_df.index:
                amt_won = int(sub_df.at[code, amt_col])
                amt_eok = round(amt_won / 100_000_000)
                name = str(sub_df.at[code, name_col]) if name_col in sub_df.columns else str(code)
                items.append({
                    "code": str(code),
                    "name": name,
                    "amount": amt_eok,
                    "changePct": chg_map.get(str(code), 0),
                })
            return items

        result = {"buy": build_list(buy_df), "sell": build_list(sell_df)}
        self._set_cache("foreign_top20_data", result)
        return result

    # ═══════════════ Sector Map (ka20002) ═══════════════

    def _get_sector_map(self) -> dict:
        """ka20002: 업종별 종목 리스트로 종목코드→업종명 매핑. 24h cache."""
        cached = self._get_cache("sector_map_kiwoom", ttl=86400)
        if cached:
            return cached

        sector_map = {}
        for inds_code, sector_name in INDUSTRY_SECTORS.items():
            try:
                body = {"mrkt_tp": "0", "inds_cd": inds_code, "stex_tp": "3"}
                data = self._api.call("ka20002", "/api/dostk/sect", body)
                items = data.get("inds_stkpc", [])
                for item in items:
                    stk_cd = str(item.get("stk_cd", "")).replace("_AL", "").replace("_NX", "").strip()
                    if len(stk_cd) == 6:
                        sector_map[stk_cd] = sector_name
            except Exception as e:
                logger.warning(f"Sector map [{inds_code}:{sector_name}] error: {e}")

        if sector_map:
            self._set_cache("sector_map_kiwoom", sector_map)
            logger.info(f"Sector map built: {len(sector_map)} stocks across {len(INDUSTRY_SECTORS)} sectors")
        return sector_map

    # ═══════════════ Sector Flow (ka10051) ═══════════════

    def get_foreign_sector_flow(self) -> list:
        """ka10051: 업종별 외국인+기관 순매수. [{sector, foreignAmt, instAmt}]"""
        cached = self._get_cache("foreign_sector_flow", ttl=600)
        if cached:
            return cached

        body = {"mrkt_tp": "0", "amt_qty_tp": "0", "stex_tp": "3"}
        data = self._api.call("ka10051", "/api/dostk/sect", body)
        items = data.get("inds_netprps", [])

        result = []
        for item in items:
            raw_nm = str(item.get("inds_nm", "")).strip()
            sector_nm = KA10051_SECTOR_MAP.get(raw_nm)
            if not sector_nm:
                continue
            frgnr = self._parse_int(item.get("frgnr_netprps", "0"))
            orgn = self._parse_int(item.get("orgn_netprps", "0"))
            result.append({"sector": sector_nm, "foreignAmt": frgnr, "instAmt": orgn})

        result.sort(key=lambda x: -x["foreignAmt"])
        self._set_cache("foreign_sector_flow", result)
        return result

    # ═══════════════ IB Sector Flow (ka10039 + sector_map) ═══════════════

    def get_ib_sector_flow(self) -> dict:
        """ka10039 + sector_map: 기관별(MS/JP/GS) 종목 매매를 업종별로 합산"""
        cached = self._get_cache("ib_sector_flow", ttl=600)
        if cached:
            return cached

        sector_map = self._get_sector_map()
        result = {}

        for inst_key in ("MS", "JP", "GS"):
            try:
                buy_stocks = self.get_institution_top(inst_key, trade_type="1", days="5")[:20]
                sell_stocks = self.get_institution_top(inst_key, trade_type="2", days="5")[:20]
            except Exception:
                buy_stocks, sell_stocks = [], []

            sector_totals = {}
            for s in buy_stocks:
                sec = sector_map.get(s["code"], "기타")
                sector_totals[sec] = sector_totals.get(sec, 0) + s["amount"]
            for s in sell_stocks:
                sec = sector_map.get(s["code"], "기타")
                sector_totals[sec] = sector_totals.get(sec, 0) - abs(s["amount"])

            items = [{"sector": k, "amount": round(v, 1)} for k, v in sector_totals.items()]
            items.sort(key=lambda x: -x["amount"])
            result[inst_key] = items

        self._set_cache("ib_sector_flow", result)
        return result

    # ═══════════════ Market Indices (yfinance) ═══════════════

    def get_market_indices(self) -> dict:
        """KOSPI / KOSDAQ 현재 지수 (yfinance)."""
        cached = self._get_cache("market_indices", ttl=60)
        if cached:
            return cached

        import yfinance as yf

        indices = {}
        for ticker_sym, idx_name in [("^KS11", "KOSPI"), ("^KQ11", "KOSDAQ")]:
            try:
                ticker = yf.Ticker(ticker_sym)
                hist = ticker.history(period="2d")
                if hist.empty or len(hist) < 1:
                    indices[idx_name] = {"name": idx_name, "value": 0, "change": 0, "changePct": 0, "signal": "3"}
                    continue

                cur = float(hist["Close"].iloc[-1])
                prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else cur
                change = round(cur - prev, 2)
                pct = round(change / prev * 100, 2) if prev else 0
                sig = "2" if change > 0 else ("5" if change < 0 else "3")

                indices[idx_name] = {
                    "name": idx_name,
                    "value": round(cur, 2),
                    "change": change,
                    "changePct": pct,
                    "signal": sig,
                }
            except Exception as e:
                logger.warning(f"Index [{idx_name}] fetch failed: {e}")
                indices[idx_name] = {"name": idx_name, "value": 0, "change": 0, "changePct": 0, "signal": "3"}

        self._set_cache("market_indices", indices)
        return indices

    # ═══════════════ Program Trading Trend (ka90005) ═══════════════

    def get_program_trend(self, mrkt_tp: str = "0") -> list:
        """
        ka90005: 프로그램매매추이 — 시간대별 프로그램 순매수 데이터
        mrkt_tp: "0"=KOSPI, "1"=KOSDAQ

        Returns: [{time, buy, sell, net, cumNet}, ...]  (시간순 정렬)

        NOTE: 응답 필드명은 키움 REST API 문서 확인 후 조정 필요.
              아래는 키움 공통 네이밍 컨벤션 기반 추정치.
        """
        body = {"mrkt_tp": mrkt_tp}
        data = self._api.call("ka90005", "/api/dostk/stkinfo", body)

        # ── 응답에서 배열 데이터 자동 탐색 ──
        items = []
        for key, val in data.items():
            if isinstance(val, list) and val and isinstance(val[0], dict):
                items = val
                break

        result = []
        running_cum = 0
        for row in items:
            # 시간 필드: cntr_tm / tm / time 등 다양한 키 대응
            tm = str(
                row.get("cntr_tm", row.get("tm", row.get("time", "")))
            ).strip()

            buy = self._parse_int(
                row.get("prog_buy_amt", row.get("pgm_buy", row.get("pgm_buy_amt", "0")))
            )
            sell = self._parse_int(
                row.get("prog_sell_amt", row.get("pgm_sell", row.get("pgm_sell_amt", "0")))
            )
            net = self._parse_int(
                row.get("prog_netprps_amt", row.get("pgm_netprps", row.get("netprps", "0")))
            )
            # 누적 순매수: 응답에 있으면 사용, 없으면 직접 누적
            cum_raw = row.get("prog_acml_netprps", row.get("pgm_acml_netprps", None))
            if cum_raw is not None:
                cum_net = self._parse_int(cum_raw)
            else:
                running_cum += net
                cum_net = running_cum

            result.append({
                "time": tm,
                "buy": buy,
                "sell": sell,
                "net": net,
                "cumNet": cum_net,
            })

        return result

    # ═══════════════ Investor Provisional Tally (ka10065) ═══════════════

    def get_inst_provisional(self, stk_cd: str) -> dict:
        """
        ka10065: 투자자별 가집계 — 종목별 투자자 유형 잠정 순매수
        stk_cd: 종목코드 (예: "005930")

        Returns: {code, instNet, foreignNet, personalNet, programNet}

        NOTE: 응답이 단일 dict 또는 투자자별 배열일 수 있음. 두 경우 모두 처리.
        """
        body = {"stk_cd": stk_cd}
        data = self._api.call("ka10065", "/api/dostk/stkinfo", body)

        # Case 1: 투자자 유형별 배열 응답
        inv_array = None
        for key, val in data.items():
            if isinstance(val, list) and val and isinstance(val[0], dict):
                inv_array = val
                break

        if inv_array:
            mapping = {"instNet": 0, "foreignNet": 0, "personalNet": 0, "programNet": 0}
            for row in inv_array:
                name = str(row.get("invst_tp_nm", row.get("invst_nm", ""))).strip()
                net_qty = self._parse_int(
                    row.get("netprps_qty", row.get("netprps_amt", row.get("netprps", "0")))
                )
                if "기관" in name:
                    mapping["instNet"] = net_qty
                elif "외국" in name or "외인" in name:
                    mapping["foreignNet"] = net_qty
                elif "개인" in name:
                    mapping["personalNet"] = net_qty
                elif "프로그램" in name or "프로" in name:
                    mapping["programNet"] = net_qty
            return {"code": stk_cd, **mapping}

        # Case 2: 단일 dict 응답 (필드명으로 직접 매핑)
        return {
            "code": stk_cd,
            "instNet": self._parse_int(
                data.get("orgn_netprps_qty", data.get("orgn_netprps", "0"))
            ),
            "foreignNet": self._parse_int(
                data.get("frgnr_netprps_qty", data.get("frgnr_netprps", "0"))
            ),
            "personalNet": self._parse_int(
                data.get("prsn_netprps_qty", data.get("prsn_netprps", "0"))
            ),
            "programNet": self._parse_int(
                data.get("pgm_netprps_qty", data.get("pgm_netprps", "0"))
            ),
        }

    # ═══════════════ Provisional Ranking (ka10065) ═══════════════

    def get_provisional_ranking(self, orgn_tp: str = "9100", trde_tp: str = "1", mrkt_tp: str = "0") -> list:
        """
        ka10065: 투자자별 가집계 순매수 상위 랭킹.
        orgn_tp: "9000"=프로그램, "9100"=기관, "9200"=외국인
        trde_tp: "0"=전체, "1"=순매수상위
        mrkt_tp: "0"=KOSPI, "1"=KOSDAQ

        Returns: [{code, name, buyQty, sellQty, netQty}, ...]
        """
        cache_key = f"prov_rank_{orgn_tp}_{trde_tp}_{mrkt_tp}"
        cached = self._get_cache(cache_key, ttl=25)
        if cached:
            return cached

        body = {"orgn_tp": orgn_tp, "trde_tp": trde_tp, "mrkt_tp": mrkt_tp}
        data = self._api.call("ka10065", "/api/dostk/rkinfo", body)
        items = data.get("opmr_invsr_trde_upper", [])

        result = []
        for item in items:
            code = str(item.get("stk_cd", "")).replace("_AL", "").replace("_NX", "").strip()
            if not code or len(code) != 6:
                continue

            result.append({
                "code": code,
                "name": str(item.get("stk_nm", "")).strip(),
                "buyQty": self._parse_int(item.get("buy_qty", "0")),
                "sellQty": self._parse_int(item.get("sel_qty", "0")),
                "netQty": self._parse_int(item.get("netslmt", "0")),
            })

        if result:
            self._set_cache(cache_key, result)
        return result

    # ═══════════════ Top Trading Volume (ka10032) ═══════════════

    def get_top_volume_stocks(self, mrkt_tp: str = "0", count: int = 50) -> list:
        """
        ka10032: 거래대금상위 — 장중 거래대금 기준 상위 종목.
        mrkt_tp: "0"=KOSPI, "1"=KOSDAQ

        Returns: [{code, name, tradeAmt, curPrc, changePct}, ...]
        """
        cached = self._get_cache(f"top_volume_{mrkt_tp}", ttl=60)
        if cached:
            return cached

        body = {"mrkt_tp": mrkt_tp, "vol_qty_tp": "0", "stex_tp": "3", "mang_stk_incls": "0"}
        data = self._api.call("ka10032", "/api/dostk/rkinfo", body)

        items = data.get("trde_prica_upper", [])
        if not items:
            for key, val in data.items():
                if isinstance(val, list) and val and isinstance(val[0], dict):
                    items = val
                    break

        result = []
        for item in items[:count]:
            code = str(item.get("stk_cd", "")).replace("_AL", "").replace("_NX", "").strip()
            if not code or len(code) != 6:
                continue

            trade_amt = self._parse_int(
                item.get("trde_prica", item.get("trde_amt", item.get("trde_val", "0")))
            )
            cur_prc = abs(self._parse_int(item.get("cur_prc", item.get("prc", "0"))))
            flu_rt = self._parse_float(item.get("flu_rt", "0"))

            result.append({
                "code": code,
                "name": str(item.get("stk_nm", "")).strip(),
                "tradeAmt": trade_amt,
                "curPrc": cur_prc,
                "changePct": flu_rt,
            })

        if result:
            self._set_cache(f"top_volume_{mrkt_tp}", result)
        return result

    # ═══════════════ Market Indices (yfinance) ═══════════════

    def get_nasdaq_index(self) -> dict:
        """NASDAQ Composite via yfinance."""
        cached = self._get_cache("nasdaq_index", ttl=120)
        if cached:
            return cached

        try:
            import yfinance as yf
            ticker = yf.Ticker("^IXIC")
            hist = ticker.history(period="2d")
            if hist.empty or len(hist) < 1:
                return {"name": "NASDAQ", "value": 0, "change": 0, "changePct": 0, "signal": "3"}

            cur = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else cur
            change = round(cur - prev, 2)
            pct = round(change / prev * 100, 2) if prev else 0
            sig = "2" if change > 0 else ("5" if change < 0 else "3")

            result = {
                "name": "NASDAQ",
                "value": round(cur, 2),
                "change": change,
                "changePct": pct,
                "signal": sig,
            }
            self._set_cache("nasdaq_index", result)
            return result
        except Exception as e:
            logger.warning(f"NASDAQ fetch failed: {e}")
            return {"name": "NASDAQ", "value": 0, "change": 0, "changePct": 0, "signal": "3"}
