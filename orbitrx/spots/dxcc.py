"""DXCC-style callsign entity resolution helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DxccEntity:
    prefix: str
    name: str


DXCC_PREFIXES: tuple[DxccEntity, ...] = tuple(
    sorted(
        [
            DxccEntity("CT3", "Madeira"),
            DxccEntity("EA8", "Canary Islands"),
            DxccEntity("UA9", "Asiatic Russia"),
            DxccEntity("3DA", "Eswatini"),
            DxccEntity("2E", "United Kingdom"),
            DxccEntity("9A", "Croatia"),
            DxccEntity("4X", "Israel"),
            DxccEntity("4S", "Sri Lanka"),
            DxccEntity("3B", "Mauritius"),
            DxccEntity("5R", "Madagascar"),
            DxccEntity("5H", "Tanzania"),
            DxccEntity("5X", "Uganda"),
            DxccEntity("5Z", "Kenya"),
            DxccEntity("7Q", "Malawi"),
            DxccEntity("7P", "Lesotho"),
            DxccEntity("9K", "Kuwait"),
            DxccEntity("9M", "Malaysia"),
            DxccEntity("9J", "Zambia"),
            DxccEntity("A2", "Botswana"),
            DxccEntity("A4", "Oman"),
            DxccEntity("A6", "United Arab Emirates"),
            DxccEntity("BV", "Taiwan"),
            DxccEntity("BY", "China"),
            DxccEntity("C6", "Bahamas"),
            DxccEntity("CE", "Chile"),
            DxccEntity("CO", "Cuba"),
            DxccEntity("CP", "Bolivia"),
            DxccEntity("CT", "Portugal"),
            DxccEntity("CU", "Azores"),
            DxccEntity("CX", "Uruguay"),
            DxccEntity("DL", "Germany"),
            DxccEntity("DU", "Philippines"),
            DxccEntity("EA", "Spain"),
            DxccEntity("EI", "Ireland"),
            DxccEntity("EP", "Iran"),
            DxccEntity("ER", "Moldova"),
            DxccEntity("ES", "Estonia"),
            DxccEntity("F", "France"),
            DxccEntity("G", "United Kingdom"),
            DxccEntity("HB", "Switzerland"),
            DxccEntity("HC", "Ecuador"),
            DxccEntity("HI", "Dominican Republic"),
            DxccEntity("HK", "Colombia"),
            DxccEntity("HL", "South Korea"),
            DxccEntity("HP", "Panama"),
            DxccEntity("HS", "Thailand"),
            DxccEntity("HZ", "Saudi Arabia"),
            DxccEntity("I", "Italy"),
            DxccEntity("JA", "Japan"),
            DxccEntity("JE", "Japan"),
            DxccEntity("JF", "Japan"),
            DxccEntity("JG", "Japan"),
            DxccEntity("JH", "Japan"),
            DxccEntity("JR", "Japan"),
            DxccEntity("J6", "St Lucia"),
            DxccEntity("K", "United States"),
            DxccEntity("LA", "Norway"),
            DxccEntity("LU", "Argentina"),
            DxccEntity("LY", "Lithuania"),
            DxccEntity("LZ", "Bulgaria"),
            DxccEntity("M", "United Kingdom"),
            DxccEntity("N", "United States"),
            DxccEntity("OA", "Peru"),
            DxccEntity("OE", "Austria"),
            DxccEntity("OH", "Finland"),
            DxccEntity("OK", "Czech Republic"),
            DxccEntity("OM", "Slovakia"),
            DxccEntity("ON", "Belgium"),
            DxccEntity("OZ", "Denmark"),
            DxccEntity("PA", "Netherlands"),
            DxccEntity("PJ", "Caribbean Netherlands"),
            DxccEntity("PY", "Brazil"),
            DxccEntity("R", "Russia"),
            DxccEntity("S5", "Slovenia"),
            DxccEntity("SM", "Sweden"),
            DxccEntity("SP", "Poland"),
            DxccEntity("SV", "Greece"),
            DxccEntity("TA", "Turkey"),
            DxccEntity("TF", "Iceland"),
            DxccEntity("TG", "Guatemala"),
            DxccEntity("TI", "Costa Rica"),
            DxccEntity("UA", "Russia"),
            DxccEntity("VE", "Canada"),
            DxccEntity("VK", "Australia"),
            DxccEntity("V5", "Namibia"),
            DxccEntity("VU", "India"),
            DxccEntity("W", "United States"),
            DxccEntity("XE", "Mexico"),
            DxccEntity("YB", "Indonesia"),
            DxccEntity("YI", "Iraq"),
            DxccEntity("YL", "Latvia"),
            DxccEntity("YO", "Romania"),
            DxccEntity("YU", "Serbia"),
            DxccEntity("YV", "Venezuela"),
            DxccEntity("ZL", "New Zealand"),
            DxccEntity("ZP", "Paraguay"),
            DxccEntity("ZS", "South Africa"),
            DxccEntity("AA", "United States"),
            DxccEntity("AB", "United States"),
            DxccEntity("AC", "United States"),
            DxccEntity("AD", "United States"),
            DxccEntity("AE", "United States"),
            DxccEntity("AF", "United States"),
            DxccEntity("AG", "United States"),
            DxccEntity("AI", "United States"),
            DxccEntity("AJ", "United States"),
            DxccEntity("AL", "United States"),
            DxccEntity("VA", "Canada"),
        ],
        key=lambda item: len(item.prefix),
        reverse=True,
    )
)


def normalize_callsign(callsign: str) -> str:
    return (callsign or "").strip().upper()


def resolve_dxcc_entity(callsign: str) -> DxccEntity:
    normalized = normalize_callsign(callsign)
    if not normalized:
        return DxccEntity("", "Unknown")

    for entity in DXCC_PREFIXES:
        if normalized.startswith(entity.prefix):
            return entity

    prefix_chars: list[str] = []
    for char in normalized:
        if char.isalpha():
            prefix_chars.append(char)
            if len(prefix_chars) == 2:
                break
        elif char.isdigit():
            break
    fallback_prefix = "".join(prefix_chars)
    if fallback_prefix:
        return DxccEntity(fallback_prefix, f"Prefix {fallback_prefix}")
    return DxccEntity("", "Unknown")


def callsign_country(callsign: str) -> str:
    return resolve_dxcc_entity(callsign).name