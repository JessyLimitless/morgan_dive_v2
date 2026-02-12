"""
AX RADAR v3.2 - Configuration
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Flask ──
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
SECRET_KEY = os.getenv("SECRET_KEY", "ax-radar-v3.2-secret")
REFRESH_INTERVAL = int(os.getenv("REFRESH_INTERVAL", "30000"))

# ── Kiwoom REST API ──
KIWOOM_BASE_URL = os.getenv("KIWOOM_BASE_URL", "https://api.kiwoom.com")
KIWOOM_APPKEY = os.getenv("KIWOOM_APPKEY", "")
KIWOOM_SECRETKEY = os.getenv("KIWOOM_SECRETKEY", "")

# ── Institution Member Codes (ka10102 confirmed) ──
INSTITUTION_CODES = {
    "MS": {"code": "036", "name": "Morgan Stanley"},
    "JP": {"code": "033", "name": "JP Morgan"},
    "GS": {"code": "045", "name": "Goldman Sachs"},
}

# ── Sector Map (KOSPI sector index codes for ka20003) ──
SECTOR_MAP = {
    "002": "대형주",
    "003": "중형주",
    "004": "소형주",
    "005": "음식료품",
    "006": "섬유의복",
    "007": "종이목재",
    "008": "화학",
    "009": "의약품",
    "010": "비금속광물",
    "011": "철강금속",
    "012": "기계",
    "013": "전기전자",
    "014": "의료정밀",
    "015": "운수장비",
    "016": "유통업",
    "017": "전기가스업",
    "018": "건설업",
    "019": "운수창고업",
    "020": "통신업",
    "021": "금융업",
    "022": "은행",
    "024": "증권",
    "025": "보험",
    "026": "서비스업",
    "027": "제조업",
}

# ── Industry Sectors (18 pure-industry groups from SECTOR_MAP) ──
# Excludes: 대형주/중형주/소형주 (size), 제조업 (umbrella), 은행/증권/보험 (sub of 금융업)
INDUSTRY_SECTORS = {
    k: v for k, v in SECTOR_MAP.items()
    if v not in ("대형주", "중형주", "소형주", "제조업", "은행", "증권", "보험")
}

# ka10051 응답의 inds_nm 기준 필터링용
INDUSTRY_SECTOR_NAMES = set(INDUSTRY_SECTORS.values())

# ka10051 inds_nm → 표준 업종명 매핑 (ka10051은 ka20003과 다른 표기 사용)
KA10051_SECTOR_MAP = {
    "음식료/담배": "음식료품",
    "섬유/의류": "섬유의복",
    "종이/목재": "종이목재",
    "화학": "화학",
    "제약": "의약품",
    "비금속": "비금속광물",
    "금속": "철강금속",
    "기계/장비": "기계",
    "전기/전자": "전기전자",
    "의료/정밀기기": "의료정밀",
    "운송장비/부품": "운수장비",
    "유통": "유통업",
    "전기/가스": "전기가스업",
    "건설": "건설업",
    "운송/창고": "운수창고업",
    "통신": "통신업",
    "금융": "금융업",
    "일반서비스": "서비스업",
}
