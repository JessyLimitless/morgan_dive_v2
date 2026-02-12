"""
AX RADAR v5.3 - Flask Application
Summary + Market Pulse + Foreign + Sector + Institution + Accumulation + Program
"""
import logging
import os
import time
from flask import Flask, render_template, jsonify, request

from config import DEBUG, SECRET_KEY, REFRESH_INTERVAL
from modules.kiwoom import KiwoomLogic
from modules.content import ContentManager
from modules.hong_signal import HongSignalScanner
from modules.accumulation import AccumulationEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("ax_radar")

app = Flask(__name__)
app.secret_key = SECRET_KEY

kiwoom = KiwoomLogic()
content = ContentManager()
hong_scanner = HongSignalScanner(kiwoom)
accumulation_engine = AccumulationEngine(kiwoom)

logger.info(f"AX RADAR v5.3 | Kiwoom: {'LIVE' if kiwoom.connected else 'DISCONNECTED'}")

# ═══════════════════════════════════════════════════════════════════
#  Main Page
# ═══════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template(
        "index.html",
        refresh_interval=REFRESH_INTERVAL,
        mode="LIVE" if kiwoom.connected else "DISCONNECTED",
    )


# ═══════════════════════════════════════════════════════════════════
#  Article API — serves article JSON for AJAX loading
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/v3/article/<category>")
def api_v3_article(category):
    """Article content API: returns meta + body HTML + sidebar list."""
    if category not in ("wsj", "radar", "etf", "column"):
        return jsonify({"status": "error", "message": "Invalid category"}), 400
    date = request.args.get("date")
    article = content.get_article(category, date)
    if article is None:
        return jsonify({"status": "error", "message": "Article not found"}), 404
    sidebar = content.list_articles(category, limit=7)
    return jsonify({
        "status": "ok",
        "data": {
            "meta": article["meta"],
            "body": article["body"],
            "date_slug": article["date_slug"],
            "sidebar": sidebar,
        }
    })


# ═══════════════════════════════════════════════════════════════════
#  API Endpoints
# ═══════════════════════════════════════════════════════════════════

def _cached_api(cache_key, fetch_fn, label):
    """Cache wrapper: API call -> cache on success, serve cache on failure"""
    try:
        data = fetch_fn()
        kiwoom._set_cache(cache_key, data)
        return jsonify({"status": "ok", "data": data})
    except Exception as e:
        logger.error(f"{label} error: {e}")
        cached = kiwoom._get_cache(cache_key)
        if cached is not None:
            logger.info(f"{label}: serving cached data")
            return jsonify({"status": "ok", "data": cached, "cached": True})
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/v3/indices")
def api_v3_indices():
    """KOSPI / KOSDAQ / NASDAQ 지수 현황"""
    def fetch():
        indices = kiwoom.get_market_indices()
        nasdaq = kiwoom.get_nasdaq_index()
        indices["NASDAQ"] = nasdaq
        return indices
    return _cached_api("indices", fetch, "Indices API")


@app.route("/api/v3/institutions")
def api_v3_institutions():
    """3사 순매수/순매도 TOP 5 · 5영업일 누적 (ka10039 dt=5)"""
    def fetch():
        result = {}
        for inst in ("MS", "JP", "GS"):
            inst_name = {"MS": "Morgan Stanley", "JP": "JP Morgan", "GS": "Goldman Sachs"}[inst]
            try:
                buy_top = kiwoom.get_institution_top(inst, trade_type="1", days="5")[:5]
                sell_top = kiwoom.get_institution_top(inst, trade_type="2", days="5")[:5]
            except Exception as e:
                logger.warning(f"Institution [{inst}] data error: {e}")
                buy_top = []
                sell_top = []
            result[inst] = {"name": inst_name, "buyTop": buy_top, "sellTop": sell_top}
        has_data = any(result[i]["buyTop"] or result[i]["sellTop"] for i in result)
        if not has_data:
            raise Exception("All institution data empty")
        return result
    return _cached_api("institutions", fetch, "Institutions API")


@app.route("/api/v3/stock/<code>")
def api_v3_stock_detail(code):
    """종목 상세 팝업 (ka10001)"""
    cache_key = f"stock_{code}"
    return _cached_api(cache_key, lambda: kiwoom.get_stock_info(code), f"Stock detail [{code}]")


@app.route("/api/v3/foreign-top")
def api_v3_foreign_top():
    """외국인 순매수/순매도 TOP 20 (최근 5영업일, pykrx)"""
    return _cached_api("foreign_top20", kiwoom.get_foreign_top20, "Foreign Top API")


@app.route("/api/v3/foreign-sector")
def api_v3_foreign_sector():
    """업종별 외국인+기관 순매수/순매도 (ka10051, 18개 KOSPI 업종)"""
    return _cached_api("foreign_sector", kiwoom.get_foreign_sector_flow, "Foreign Sector API")


@app.route("/api/v3/ib-sector")
def api_v3_ib_sector():
    """기관별(MS/JP/GS) 업종별 순매수/순매도"""
    return _cached_api("ib_sector", kiwoom.get_ib_sector_flow, "IB Sector API")


# ═══════════════════════════════════════════════════════════════════
#  Hong Signal API — 홍인기 대왕개미 매수 신호 스캐너
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/v3/hong-signal")
def api_v3_hong_signal():
    """
    홍인기 전략 매수 신호 스캔.

    Query params:
        codes  — 종목코드 (콤마 구분, 예: "005930,000660,035420")
                 미지정 시 ax_universe + 외국인/기관 상위 종목 자동 구성
        market — "0"=KOSPI(기본), "1"=KOSDAQ
    """
    codes_param = request.args.get("codes", "")
    mrkt_tp = request.args.get("market", "0")

    if codes_param:
        stock_codes = [c.strip() for c in codes_param.split(",") if c.strip()]
    else:
        # 기본 유니버스: ax_universe.json + 기존 캐시된 외국인/기관 종목
        stock_codes = list(kiwoom.ax_universe.keys()) if kiwoom.ax_universe else []
        foreign_cache = kiwoom._get_cache("foreign_top20_data")
        if foreign_cache:
            for side in ("buy", "sell"):
                for item in foreign_cache.get(side, []):
                    if item["code"] not in stock_codes:
                        stock_codes.append(item["code"])
        if not stock_codes:
            return jsonify({"status": "error", "message": "No stock universe. Pass ?codes=005930,000660,..."}), 400

    try:
        result = hong_scanner.scan(stock_codes, mrkt_tp)
        return jsonify({"status": "ok", "data": result})
    except Exception as e:
        logger.error(f"Hong signal scan error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/v3/program-slope")
def api_v3_program_slope():
    """프로그램 매수 기울기 단독 조회 (ka90005)"""
    mrkt_tp = request.args.get("market", "0")
    try:
        result = hong_scanner.get_program_slope(mrkt_tp)
        return jsonify({"status": "ok", "data": result})
    except Exception as e:
        logger.error(f"Program slope error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════
#  Strategy API — 홍인기 수급 주도주 전략
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/v4/strategy/signals")
def api_v4_strategy_signals():
    """홍인기 수급 주도주 전략 — 실시간 시그널"""
    mrkt_tp = request.args.get("market", "0")
    return _cached_api(
        f"strategy_signals_{mrkt_tp}",
        lambda: hong_scanner.scan_strategy(mrkt_tp),
        "Strategy Signal",
    )


# ═══════════════════════════════════════════════════════════════════
#  Foreign Accumulation Radar API
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/v3/accumulation")
def api_v3_accumulation():
    """Foreign Accumulation Radar — 외국인 스텔스 축적 TOP 15"""
    cache_key = "accumulation_radar"
    try:
        cached = kiwoom._get_cache(cache_key, ttl=120)
        if cached is not None:
            return jsonify({"status": "ok", "data": cached, "cached": True})
        data = accumulation_engine.analyze(top_n=15)
        kiwoom._set_cache(cache_key, data)
        return jsonify({"status": "ok", "data": data})
    except Exception as e:
        logger.error(f"Accumulation API error: {e}")
        cached = kiwoom._get_cache(cache_key)
        if cached is not None:
            return jsonify({"status": "ok", "data": cached, "cached": True})
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/v3/accumulation/<stk_cd>")
def api_v3_accumulation_detail(stk_cd):
    """종목별 외국인 비중 시계열 상세"""
    try:
        history = accumulation_engine.get_foreign_weight_history(stk_cd)
        return jsonify({"status": "ok", "data": history})
    except Exception as e:
        logger.error(f"Accumulation detail [{stk_cd}] error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════
#  Program Trading TOP 50 API
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/v3/program-top")
def api_v3_program_top():
    """당일 프로그램 순매수 TOP 50 (코스피+코스닥 통합)"""

    def fetch():
        pn = kiwoom._parse_float

        # 코스피
        kospi = kiwoom._api.call("ka90003", "/api/dostk/stkinfo", {
            "trde_upper_tp": "2", "amt_qty_tp": "1",
            "mrkt_tp": "P00101", "stex_tp": "1",
        })
        time.sleep(0.3)

        # 코스닥
        kosdaq = kiwoom._api.call("ka90003", "/api/dostk/stkinfo", {
            "trde_upper_tp": "2", "amt_qty_tp": "1",
            "mrkt_tp": "P10102", "stex_tp": "1",
        })

        def extract(data):
            items = data.get("prm_netprps_upper_50", [])
            if not items:
                for k, v in data.items():
                    if isinstance(v, list) and v and isinstance(v[0], dict):
                        items = v
                        break
            return items

        kospi_items = extract(kospi)
        kosdaq_items = extract(kosdaq)

        for item in kospi_items:
            item["_market"] = "KOSPI"
        for item in kosdaq_items:
            item["_market"] = "KOSDAQ"

        combined = kospi_items + kosdaq_items
        combined.sort(key=lambda x: abs(pn(x.get("prm_netprps_amt", "0"))), reverse=True)

        result = []
        for i, item in enumerate(combined[:50]):
            cd = str(item.get("stk_cd", "")).replace("_NX", "").replace("_AL", "").strip()
            if not cd or len(cd) != 6:
                continue
            net = pn(item.get("prm_netprps_amt", "0"))
            result.append({
                "rank": i + 1,
                "stk_cd": cd,
                "stk_nm": str(item.get("stk_nm", "")).strip(),
                "market": item.get("_market", ""),
                "cur_prc": abs(kiwoom._parse_int(item.get("cur_prc", "0"))),
                "flu_rt": pn(item.get("flu_rt", "0")),
                "prm_netprps_amt": net,
            })
        return result

    return _cached_api("program_top", fetch, "Program TOP API")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=DEBUG)

