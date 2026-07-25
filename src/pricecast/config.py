"""Paths, pilot scope, and tunable constants.

Every path is resolved relative to the project root so the package behaves the
same whether it is imported from a script, a test, or the API process.
"""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
REGISTRY_DIR = DATA_DIR / "registry"
OUTPUT_DIR = PROJECT_ROOT / "output"
DB_PATH = DATA_DIR / "kamis.db"
ALIASES_PATH = PROJECT_ROOT / "market_aliases.csv"

# --- Data hygiene -----------------------------------------------------------
ROW_CAP = 3000            # KAMIS "Export to Excel" truncates here
JUNK_MARKETS = {"test market", "test", "testing", "demo market"}

# --- Modelling --------------------------------------------------------------
MIN_OBS_MODEL = 26        # weekly observations required for the LightGBM tier
MIN_OBS_SEASONAL = 8      # below this a series is insufficient_data
MAX_STALE_WEEKS = 8       # last observation older than this -> insufficient_data
HORIZONS = (1, 2, 4)
QUANTILES = (0.1, 0.5, 0.9)

# --- Netback ----------------------------------------------------------------
# Reference pump price the transport rate card is calibrated against. Update
# from the EPRA monthly gazette (data/registry/fuel_prices.csv).
DEFAULT_DIESEL_KES_PER_LITRE = 165.0
FUEL_SHARE_OF_TRUCK_COST = 0.38   # CAK (2019) East Africa trucking cost study
HANDLING_PCT_LOW = 0.03           # loading, offloading, market-level brokerage
HANDLING_PCT_HIGH = 0.06
UTILISATION_HIGH = 0.90           # best case payload utilisation -> cheaper per kg
UTILISATION_LOW = 0.60            # worst case -> dearer per kg

# --- Pilot scope ------------------------------------------------------------
# Ranked by feasibility: current KAMIS coverage x broker-exploitation pain.
PILOT_CROPS = [
    {
        "commodity": "Dry Maize",
        "rank": 1,
        "counties": ["Uasin Gishu", "Trans Nzoia"],
        "terminal_markets": ["Eldoret", "Kitale", "Nairobi Wakulima"],
        "cluster": "cereal",
        "packaging": "bag_90kg",
        "rationale": "Current KAMIS coverage in-repo (2024-09 to 2026-07, 80 markets).",
    },
    {
        "commodity": "Red Irish potato",
        "rank": 2,
        "counties": ["Nyandarua", "Nakuru"],
        "terminal_markets": ["Nairobi Wakulima", "Nakuru Wakulima"],
        "cluster": "root_tuber",
        "packaging": "bag_90kg",
        "rationale": "Extended-bag exploitation is the flagship national broker issue.",
    },
    {
        "commodity": "Dry Onions",
        "rank": 3,
        "counties": ["Kajiado", "Bungoma"],
        "terminal_markets": ["Nairobi Wakulima", "Nakuru Wakulima"],
        "cluster": "cereal",
        "packaging": "net_15kg",
        "rationale": "195 markets in-repo; Tegemeo TR31 gives a netback calibration benchmark.",
    },
    {
        "commodity": "Tomatoes",
        "rank": 4,
        "counties": ["Kirinyaga", "Kajiado"],
        "terminal_markets": ["Nairobi Wakulima"],
        "cluster": "perishable_hort",
        "packaging": "crate_64kg",
        "rationale": "Perishability makes price information urgent; honest fallback tier showcase.",
    },
    {
        "commodity": "Cabbages",
        "rank": 5,
        "counties": ["Nyandarua", "Meru"],
        "terminal_markets": ["Nairobi Wakulima", "Kongowea"],
        "cluster": "perishable_hort",
        "packaging": "bag_90kg",
        "rationale": "Perishable, parser proven, strong Nyandarua->Nairobi corridor story.",
    },
]

PILOT_COMMODITIES = [c["commodity"] for c in PILOT_CROPS]


def crop_config(commodity: str) -> dict | None:
    for c in PILOT_CROPS:
        if c["commodity"].lower() == commodity.lower():
            return c
    return None
