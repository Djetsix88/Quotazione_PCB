from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Iterable, Any


@dataclass(frozen=True)
class PrepregStyle:
    style: str
    thickness_mm: float
    resin_content_pct: float | None = None
    note: str = ""


@dataclass(frozen=True)
class Material:
    name: str
    pcb_types: tuple[str, ...]
    dk_nominal_1ghz: float | None = None
    df_nominal_1ghz: float | None = None
    tg_c: float | None = None
    td_c: float | None = None
    z_cte_ppm_c: float | None = None
    copper_foils: tuple[str, ...] = ("ED",)
    prepreg_default_plies: int = 2
    prepreg_styles: tuple[PrepregStyle, ...] = ()
    core_options_mm: tuple[float, ...] = ()
    notes: str = ""


def _default_catalog_path() -> Path:
    return Path(__file__).resolve().with_name("materials_catalog.json")


def _inch_to_mm(x_in: float) -> float:
    return float(x_in) * 25.4


def _mil_to_mm(x_mil: float) -> float:
    # 1 mil = 0.001 inch
    return _inch_to_mm(float(x_mil) * 0.001)


def _ensure_it180a_in_catalog(data: dict[str, Any]) -> dict[str, Any]:
    """
    Ensure ITEQ IT-180A exists and matches the user-provided thickness tables.

    Stored units in JSON are mm.
      - Core thickness source: inches -> mm
      - Prepreg thickness source: mil -> mm
    """
    mats = data.get("materials", [])
    if not isinstance(mats, list):
        mats = []
        data["materials"] = mats

    # --- Core IT-180A (inch -> mm) ---
    core_in = [
        0.0020, 0.0025, 0.0030, 0.0040, 0.0050, 0.0060, 0.0070,
        0.0080, 0.0100, 0.0120, 0.0140, 0.0210, 0.0280, 0.0370,
    ]
    core_mm = [round(_inch_to_mm(x), 4) for x in core_in]

    # --- Prepreg IT-180A (mil -> mm) ---
    prepregs = [
        {"style": "106", "thickness_mm": round(_mil_to_mm(2.0), 4), "resin_content_pct": 72, "note": "ITEQ IT-180A prepreg"},
        {"style": "1067", "thickness_mm": round(_mil_to_mm(2.4), 4), "resin_content_pct": 71, "note": "ITEQ IT-180A prepreg"},
        {"style": "1080", "thickness_mm": round(_mil_to_mm(2.8), 4), "resin_content_pct": 62, "note": "ITEQ IT-180A prepreg"},
        {"style": "1086", "thickness_mm": round(_mil_to_mm(3.0), 4), "resin_content_pct": 62, "note": "ITEQ IT-180A prepreg"},
        {"style": "2113", "thickness_mm": round(_mil_to_mm(3.8), 4), "resin_content_pct": 56, "note": "ITEQ IT-180A prepreg"},
        {"style": "2116", "thickness_mm": round(_mil_to_mm(4.6), 4), "resin_content_pct": 53, "note": "ITEQ IT-180A prepreg"},
        {"style": "1506", "thickness_mm": round(_mil_to_mm(6.4), 4), "resin_content_pct": 48, "note": "ITEQ IT-180A prepreg"},
        {"style": "7628", "thickness_mm": round(_mil_to_mm(7.4), 4), "resin_content_pct": 43, "note": "ITEQ IT-180A prepreg"},
        {"style": "7628HR", "thickness_mm": round(_mil_to_mm(8.2), 4), "resin_content_pct": 50, "note": "ITEQ IT-180A prepreg"},
    ]

    # find material
    idx = None
    for i, m in enumerate(mats):
        if isinstance(m, dict) and str(m.get("name", "")).strip().lower() in ("it-180a", "it 180a", "iteq it-180a"):
            idx = i
            break

    if idx is None:
        it180a: dict[str, Any] = {
            "name": "IT-180A",
            "pcb_types": ["Rigid", "Rigid-Flex", "RF"],
            "dk_nominal_1ghz": 4.10,
            "df_nominal_1ghz": 0.0140,
            "tg_c": None,
            "td_c": None,
            "z_cte_ppm_c": None,
            "copper_foils": ["ED"],
            "prepreg_default_plies": 2,
            "prepreg_styles": prepregs,
            "core_options_mm": core_mm,
            "notes": "ITEQ IT-180A (core inches->mm; prepreg mil->mm).",
        }
        mats.append(it180a)
    else:
        it180a = mats[idx]
        if isinstance(it180a, dict):
            it180a["core_options_mm"] = core_mm
            it180a["prepreg_styles"] = prepregs
            it180a.setdefault("pcb_types", ["Rigid", "Rigid-Flex", "RF"])
            it180a.setdefault("dk_nominal_1ghz", 4.10)
            it180a.setdefault("df_nominal_1ghz", 0.0140)
            it180a.setdefault("copper_foils", ["ED"])
            it180a.setdefault("prepreg_default_plies", 2)
            it180a.setdefault("notes", "ITEQ IT-180A (core inches->mm; prepreg mil->mm).")

    data["materials"] = mats
    return data


def load_catalog(path: str | Path | None = None) -> list[Material]:
    p = Path(path) if path is not None else _default_catalog_path()
    data = json.loads(p.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        data = {"schema_version": 2, "materials": []}

    # patch IT-180A
    data = _ensure_it180a_in_catalog(data)

    out: list[Material] = []
    for m in data.get("materials", []):
        if not isinstance(m, dict):
            continue

        prepregs: list[PrepregStyle] = []
        for pp in m.get("prepreg_styles", []) or []:
            if not isinstance(pp, dict):
                continue
            prepregs.append(
                PrepregStyle(
                    style=str(pp.get("style", "")),
                    thickness_mm=float(pp.get("thickness_mm", 0.0)),
                    resin_content_pct=(None if pp.get("resin_content_pct", None) is None else float(pp.get("resin_content_pct"))),
                    note=str(pp.get("note", "")),
                )
            )

        out.append(
            Material(
                name=str(m.get("name", "")),
                pcb_types=tuple(str(x) for x in (m.get("pcb_types", []) or [])),
                dk_nominal_1ghz=(None if m.get("dk_nominal_1ghz", None) is None else float(m.get("dk_nominal_1ghz"))),
                df_nominal_1ghz=(None if m.get("df_nominal_1ghz", None) is None else float(m.get("df_nominal_1ghz"))),
                tg_c=(None if m.get("tg_c", None) is None else float(m.get("tg_c"))),
                td_c=(None if m.get("td_c", None) is None else float(m.get("td_c"))),
                z_cte_ppm_c=(None if m.get("z_cte_ppm_c", None) is None else float(m.get("z_cte_ppm_c"))),
                copper_foils=tuple(str(x) for x in (m.get("copper_foils", []) or [])) or ("ED",),
                prepreg_default_plies=int(m.get("prepreg_default_plies", 2) or 2),
                prepreg_styles=tuple(prepregs),
                core_options_mm=tuple(float(x) for x in (m.get("core_options_mm", []) or [])),
                notes=str(m.get("notes", "")),
            )
        )

    return out


def get_materials(pcb_type: str = "Rigid", *, catalog: Iterable[Material] | None = None) -> list[Material]:
    cat = list(catalog) if catalog is not None else load_catalog()
    pt = str(pcb_type)
    return [m for m in cat if pt in m.pcb_types]