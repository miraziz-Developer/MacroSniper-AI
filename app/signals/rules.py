"""Which USD releases we plan, and which way a higher-than-expected number pushes the dollar."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EventKind:
    key: str
    name_uz: str
    usd_up_when_higher: bool  # True: higher actual -> stronger USD -> weaker gold


# Order matters: more specific phrases first ("unemployment claims" before "employment").
_KINDS = [
    (("unemployment claims", "jobless claims"), EventKind("claims", "Ishsizlik nafaqasi arizalari", False)),
    (("unemployment rate",), EventKind("unemployment", "Ishsizlik darajasi", False)),
    (("adp",), EventKind("adp", "ADP ish o'rinlari", True)),
    (("non-farm", "nonfarm", "nfp"), EventKind("nfp", "Qishloq xo'jaligidan tashqari ish o'rinlari (NFP)", True)),
    (("core pce", "pce price"), EventKind("pce", "PCE inflyatsiyasi", True)),
    (("cpi",), EventKind("cpi", "Iste'mol narxlari indeksi (CPI)", True)),
    (("ppi",), EventKind("ppi", "Ishlab chiqaruvchi narxlari (PPI)", True)),
    (("federal funds rate", "fomc statement", "interest rate"), EventKind("rate", "FED foiz stavkasi", True)),
    (("retail sales",), EventKind("retail", "Chakana savdo", True)),
    (("gdp",), EventKind("gdp", "YaIM (GDP)", True)),
    (("ism manufacturing pmi", "ism services pmi", "flash manufacturing pmi", "flash services pmi"),
     EventKind("pmi", "Biznes faolligi (PMI)", True)),
    (("jolts",), EventKind("jolts", "JOLTS bo'sh ish o'rinlari", True)),
    (("average hourly earnings",), EventKind("wages", "O'rtacha soatlik ish haqi", True)),
]


def classify(title: str) -> Optional[EventKind]:
    """Returns the kind for numeric releases we can plan; None for speeches, auctions and unknowns."""
    lower = title.lower()
    if "speaks" in lower or "testifies" in lower or "minutes" in lower or "press conference" in lower:
        return None
    for phrases, kind in _KINDS:
        if any(p in lower for p in phrases):
            return kind
    return None


def gold_direction_for_usd(usd_up: bool) -> str:
    return "SELL" if usd_up else "BUY"
