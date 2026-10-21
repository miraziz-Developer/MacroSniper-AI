import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class AssetSpecs:
    symbol: str
    name: str
    category: str              # "METALS", "FOREX", "INDICES", "ENERGY"
    point_value_per_lot: float # USD per 1.0 lot per point
    typical_atr_m15: float     # Average volatility in points
    typical_news_spread: float # Buffer needed during high-impact news
    max_safe_spread: float     # If spread exceeds this, PAUSE order to prevent slippage!
    target_pips: int           # Typical news breakout move
    usd_correlation: float     # -1.0 (inverse to USD like Gold/EUR) to +1.0 (aligned with USD like USDJPY)


# Institutional asset specification matrix for high-impact news trading
ASSET_REGISTRY: Dict[str, AssetSpecs] = {
    "XAUUSD": AssetSpecs(
        symbol="XAUUSD",
        name="Spot Gold",
        category="METALS",
        point_value_per_lot=1.0,   # $1 per 0.01 move on standard 100oz lot
        typical_atr_m15=4.50,      # $4.50 = 45 pips
        typical_news_spread=1.80,  # $1.80 news spread buffer
        max_safe_spread=4.00,
        target_pips=1200,          # 120 pips ($12 move)
        usd_correlation=-0.92,     # Strong inverse correlation to USD
    ),
    "EURUSD": AssetSpecs(
        symbol="EURUSD",
        name="Euro / US Dollar",
        category="FOREX",
        point_value_per_lot=10.0,
        typical_atr_m15=0.0022,    # 22 pips
        typical_news_spread=0.0006,# 6 pips buffer
        max_safe_spread=0.0015,
        target_pips=800,           # 80 pips
        usd_correlation=-0.95,
    ),
    "GBPUSD": AssetSpecs(
        symbol="GBPUSD",
        name="British Pound / US Dollar",
        category="FOREX",
        point_value_per_lot=10.0,
        typical_atr_m15=0.0035,    # 35 pips (more volatile than EUR)
        typical_news_spread=0.0008,
        max_safe_spread=0.0020,
        target_pips=1100,          # 110 pips
        usd_correlation=-0.90,
    ),
    "USDJPY": AssetSpecs(
        symbol="USDJPY",
        name="US Dollar / Japanese Yen",
        category="FOREX",
        point_value_per_lot=6.80,
        typical_atr_m15=0.45,      # 45 pips
        typical_news_spread=0.12,
        max_safe_spread=0.30,
        target_pips=1000,
        usd_correlation=0.94,      # Direct positive correlation to USD & US Yields!
    ),
    "US30": AssetSpecs(
        symbol="US30",
        name="Dow Jones Industrial Average",
        category="INDICES",
        point_value_per_lot=1.0,   # $1 per index point
        typical_atr_m15=120.0,     # 120 points
        typical_news_spread=8.0,
        max_safe_spread=25.0,
        target_pips=4500,          # 450 points
        usd_correlation=-0.75,     # High inflation / hawkish Fed dumps equities
    ),
    "NAS100": AssetSpecs(
        symbol="NAS100",
        name="Nasdaq 100 Tech Index",
        category="INDICES",
        point_value_per_lot=1.0,
        typical_atr_m15=85.0,      # 85 points
        typical_news_spread=6.0,
        max_safe_spread=18.0,
        target_pips=3500,          # 350 points
        usd_correlation=-0.85,     # Highly sensitive to Fed interest rates
    ),
    "USOIL": AssetSpecs(
        symbol="USOIL",
        name="WTI Crude Oil",
        category="ENERGY",
        point_value_per_lot=10.0,  # $10 per $0.01 per 1000 barrel contract
        typical_atr_m15=0.65,      # $0.65
        typical_news_spread=0.15,
        max_safe_spread=0.40,
        target_pips=1500,
        usd_correlation=-0.70,
    ),
}


class MultiAssetEngine:
    """
    Manages multi-pair news execution across Metals, Forex, Indices, and Energy.
    """

    def get_specs(self, symbol: str) -> AssetSpecs:
        clean_symbol = symbol.upper().replace("/", "").replace("-", "")
        if clean_symbol in ASSET_REGISTRY:
            return ASSET_REGISTRY[clean_symbol]
        # Default fallback to Gold specs
        return ASSET_REGISTRY["XAUUSD"]

    def calculate_asset_bias(self, symbol: str, score: float) -> str:
        """
        score > 0 means Bullish/BUY for the target symbol.
        score < 0 means Bearish/SELL for the target symbol.
        """
        return "BULLISH (BUY)" if score > 0 else "BEARISH (SELL)"


multi_asset_engine = MultiAssetEngine()
