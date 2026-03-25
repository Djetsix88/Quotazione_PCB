from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .models import (
    LayoutQuoteInputs, BoardConstraints, HoleType, KeepoutRect,
    ComponentsInputs, HighSpeedInputs, HighSpeedInterface, Tariffs
)
from .calculations import QuoteCoeffs, DEFAULT_COEFFS


def save_json(path: str | Path, data: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_json(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def inputs_to_dict(inp: LayoutQuoteInputs, coeffs: QuoteCoeffs) -> Dict[str, Any]:
    # compat: schema v1
    return {"schema_version": 1, "inputs": asdict(inp), "coeffs": asdict(coeffs)}


def project_to_dict(inp: LayoutQuoteInputs, coeffs: QuoteCoeffs, ui: Dict[str, Any]) -> Dict[str, Any]:
    # schema v2: salva tutto
    return {"schema_version": 2, "inputs": asdict(inp), "coeffs": asdict(coeffs), "ui": ui}


def _to_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)


def _to_int(x: Any, default: int = 0) -> int:
    try:
        return int(float(x))
    except Exception:
        return int(default)


def dict_to_inputs(d: Dict[str, Any]) -> Tuple[LayoutQuoteInputs, QuoteCoeffs]:
    coeffs = DEFAULT_COEFFS
    coeffs_d = d.get("coeffs")
    if isinstance(coeffs_d, dict):
        try:
            coeffs = QuoteCoeffs(**coeffs_d)
        except Exception:
            coeffs = DEFAULT_COEFFS

    inputs_d = d.get("inputs", d)
    if not isinstance(inputs_d, dict):
        return LayoutQuoteInputs(), coeffs

    tariffs_d = inputs_d.get("tariffs", {}) or {}
    tariffs = Tariffs(
        layout_eur_per_h=_to_float(tariffs_d.get("layout_eur_per_h", 75.0), 75.0),
        si_pi_eur_per_h=_to_float(tariffs_d.get("si_pi_eur_per_h", 90.0), 90.0),
    )

    board_d = inputs_d.get("board", {}) or {}
    holes_list = board_d.get("holes", []) or []
    keepouts_list = board_d.get("keepouts", []) or []

    holes: List[HoleType] = []
    for h in holes_list:
        if isinstance(h, HoleType):
            holes.append(h)
            continue
        if not isinstance(h, dict):
            continue
        holes.append(
            HoleType(
                diameter_mm=_to_float(h.get("diameter_mm", 0.0), 0.0),
                metallization_mm=_to_float(h.get("metallization_mm", 0.0), 0.0),
                count=_to_int(h.get("count", 0), 0),
            )
        )

    keepouts: List[KeepoutRect] = []
    for k in keepouts_list:
        if isinstance(k, KeepoutRect):
            keepouts.append(k)
            continue
        if not isinstance(k, dict):
            continue
        keepouts.append(
            KeepoutRect(
                side=str(k.get("side", "TOP")).upper(),
                width_mm=_to_float(k.get("width_mm", 0.0), 0.0),
                height_mm=_to_float(k.get("height_mm", 0.0), 0.0),
                count=_to_int(k.get("count", 1), 1),
            )
        )

    board = BoardConstraints(
        width_mm=_to_float(board_d.get("width_mm", 180.0), 180.0),
        height_mm=_to_float(board_d.get("height_mm", 140.0), 140.0),
        holes=[h for h in holes if h.diameter_mm > 0 and h.count > 0],
        keepouts=[k for k in keepouts if k.width_mm > 0 and k.height_mm > 0 and k.count > 0],
    )

    comps_d = inputs_d.get("components", {}) or {}
    components = ComponentsInputs(
        bga_count=_to_int(comps_d.get("bga_count", 0), 0),
        bga_total_pins_effective=_to_int(comps_d.get("bga_total_pins_effective", 0), 0),
        min_bga_pitch_mm=_to_float(comps_d.get("min_bga_pitch_mm", 0.8), 0.8),
        passives=_to_int(comps_d.get("passives", 0), 0),
        actives=_to_int(comps_d.get("actives", 0), 0),
        critical=_to_int(comps_d.get("critical", 0), 0),
        connectors=_to_int(comps_d.get("connectors", 0), 0),
        layers=_to_int(comps_d.get("layers", 12), 12),
        hdi=bool(comps_d.get("hdi", True)),
        tht=bool(comps_d.get("tht", False)),
    )

    hs_d = inputs_d.get("highspeed", {}) or {}
    itfs = hs_d.get("interfaces", []) or []
    interfaces: List[HighSpeedInterface] = []
    for it in itfs:
        if isinstance(it, HighSpeedInterface):
            interfaces.append(it)
            continue
        if not isinstance(it, dict):
            continue
        interfaces.append(
            HighSpeedInterface(
                name=str(it.get("name", "Interface")),
                data_rate_gbps=_to_float(it.get("data_rate_gbps", 0.0), 0.0),
                diff_pairs=_to_int(it.get("diff_pairs", 0), 0),
                se_lines=_to_int(it.get("se_lines", 0), 0),
                match_ps=_to_float(it.get("match_ps", 10.0), 10.0),
            )
        )

    highspeed = HighSpeedInputs(interfaces=interfaces)

    buffer_pct = _to_float(inputs_d.get("buffer_pct", 0.25), 0.25)
    week_hours = _to_float(inputs_d.get("week_hours", 40.0), 40.0)

    inp = LayoutQuoteInputs(
        board=board,
        components=components,
        highspeed=highspeed,
        buffer_pct=buffer_pct,
        week_hours=week_hours,
        tariffs=tariffs,
    )
    return inp, coeffs


def dict_to_project(d: Dict[str, Any]) -> Tuple[LayoutQuoteInputs, QuoteCoeffs, Dict[str, Any]]:
    """
    Ritorna (inputs, coeffs, ui_state).
    - Se schema v2: ui_state valorizzato.
    - Se schema v1/legacy: ui_state vuoto.
    """
    inp, coeffs = dict_to_inputs(d)
    ui = d.get("ui", {}) if isinstance(d.get("ui", {}), dict) else {}
    return inp, coeffs, ui