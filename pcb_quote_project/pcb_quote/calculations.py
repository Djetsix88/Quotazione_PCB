from __future__ import annotations

from dataclasses import dataclass, asdict, is_dataclass
from typing import Any, Dict, List, Tuple

from .models import LayoutQuoteInputs


# -----------------------------
# Complexity rules (robust)
# -----------------------------
@dataclass(frozen=True)
class SectionComplexityRules:
    w_qty: float = 1.0
    w_pins_per_k: float = 1.0
    w_bga_qty: float = 2.0
    w_pitch: float = 12.0
    w_critical_qty: float = 4.0
    w_connectors_qty: float = 2.0
    thr_low: float = 120.0
    thr_med: float = 260.0


def _rules_from_any(rules: SectionComplexityRules | Dict[str, Any] | None) -> SectionComplexityRules:
    if rules is None:
        return SectionComplexityRules()
    if isinstance(rules, SectionComplexityRules):
        return rules
    if isinstance(rules, dict):
        return SectionComplexityRules(
            w_qty=float(rules.get("w_qty", 1.0)),
            w_pins_per_k=float(rules.get("w_pins_per_k", 1.0)),
            w_bga_qty=float(rules.get("w_bga_qty", 2.0)),
            w_pitch=float(rules.get("w_pitch", 12.0)),
            w_critical_qty=float(rules.get("w_critical_qty", 4.0)),
            w_connectors_qty=float(rules.get("w_connectors_qty", 2.0)),
            thr_low=float(rules.get("thr_low", 120.0)),
            thr_med=float(rules.get("thr_med", 260.0)),
        )
    return SectionComplexityRules()


def section_complexity_score(
    *,
    qty_total: int,
    pins_total: int,
    bga_qty: int,
    pitch_bga_mm: float,
    critical_qty: int,
    connectors_qty: int,
    rules: SectionComplexityRules | Dict[str, Any] | None = None,
) -> float:
    r = _rules_from_any(rules)

    score = 0.0
    score += float(r.w_qty) * float(max(0, qty_total))
    score += float(r.w_pins_per_k) * float(max(0, pins_total)) / 1000.0
    score += float(r.w_bga_qty) * float(max(0, bga_qty))
    score += float(r.w_critical_qty) * float(max(0, critical_qty))
    score += float(r.w_connectors_qty) * float(max(0, connectors_qty))

    p = float(pitch_bga_mm) if pitch_bga_mm else 0.0
    if p > 0:
        pitch_factor = max(0.5, min(2.5, 0.8 / p))
        score += float(r.w_pitch) * float(pitch_factor)

    return float(score)


def section_complexity_class(score: float, rules: SectionComplexityRules | Dict[str, Any] | None = None) -> str:
    r = _rules_from_any(rules)
    if float(score) < float(r.thr_low):
        return "Low"
    if float(score) < float(r.thr_med):
        return "Med"
    return "High"


# -----------------------------
# Main model coeffs
# -----------------------------
@dataclass
class QuoteCoeffs:
    # --- Coefficienti di sistema ---
    sys_study_system_h: float = 8.0
    sys_setup_pcb_h: float = 4.0
    sys_mech_study_h: float = 6.0
    sys_dfm_documentation_h: float = 4.0

    # --- Placement ---
    k_place_bga_base_h: float = 6.0
    k_place_per_bga_h: float = 2.0
    k_place_pins_per_100_min: float = 60.0

    k_place_passive_min: float = 0.12
    k_place_active_min: float = 1.8
    k_place_critical_min: float = 12.0
    k_place_connector_min: float = 6.0

    k_hdi_multiplier: float = 1.15

    # --- Routing standard ---
    k_route_std_base_h: float = 20.0
    k_route_density_scale_h: float = 18.0
    k_route_trace_min: float = 0.6

    # --- Routing High-speed ---
    k_route_diff_pair_min: float = 33.0
    k_route_se_min: float = 10.8

    # --- SI/PI ---
    k_si_base_h: float = 12.0
    k_si_per_interface_min: float = 240.0
    k_si_rate_multiplier: float = 1.0

    # --- Cleanup ---
    k_cleanup_pct: float = 0.12

    # --- Section rules (can be dict if loaded from JSON; scorer handles it) ---
    rules_signal: SectionComplexityRules | Dict[str, Any] = SectionComplexityRules()
    rules_power: SectionComplexityRules | Dict[str, Any] = SectionComplexityRules()
    rules_rf: SectionComplexityRules | Dict[str, Any] = SectionComplexityRules()
    rules_highspeed: SectionComplexityRules | Dict[str, Any] = SectionComplexityRules()

    # Optional extras (GUI might reference these)
    feas_base_h: float = 0.0
    feas_per_interface_min: float = 0.0
    feas_stackup_base_h: float = 0.0
    feas_stackup_tech_mult_hdi: float = 1.0
    feas_stackup_tech_mult_adv: float = 1.0

    crit_extra_power_h: float = 0.0
    crit_extra_rf_h: float = 0.0
    crit_extra_highspeed_h: float = 0.0

    cplx_mult_low: float = 1.0
    cplx_mult_med: float = 1.0
    cplx_mult_high: float = 1.0


DEFAULT_COEFFS = QuoteCoeffs()


def _safe_div(n: float, d: float) -> float:
    if d <= 0:
        return 0.0
    return n / d


def _density_pin_per_cm2_layer_sides(inp: LayoutQuoteInputs) -> Tuple[float, float]:
    layers = max(inp.components.layers, 1)
    pins = float(inp.components.bga_total_pins_effective)
    dens_top = _safe_div(pins, float(inp.board.usable_top_cm2) * float(layers))
    dens_bottom = _safe_div(pins, float(inp.board.usable_bottom_cm2) * float(layers))
    return dens_top, dens_bottom


def _density_effective(dens_top: float, dens_bottom: float) -> float:
    return max(float(dens_top), float(dens_bottom))


def _f_pitch(pitch_mm: float) -> float:
    if pitch_mm >= 0.8:
        return 1.0
    if pitch_mm >= 0.65:
        return 1.2
    return 1.4


def _f_density(dens: float) -> float:
    if dens < 10:
        return 1.0
    if dens < 16:
        return 1.25
    return 1.55


def _f_hdi(inp: LayoutQuoteInputs, coeffs: QuoteCoeffs) -> float:
    return float(coeffs.k_hdi_multiplier) if inp.components.hdi else 1.0


def _severity_from_match_ps(match_ps: float) -> float:
    ps = float(match_ps)
    if ps >= 50:
        return 1.0
    if ps >= 20:
        return 1.2
    if ps >= 10:
        return 1.35
    if ps >= 5:
        return 1.55
    return 1.8


def _severity_from_data_rate(data_rate_gbps: float) -> float:
    gbps = float(data_rate_gbps)
    if gbps <= 2.5:
        return 1.0
    if gbps <= 6:
        return 1.15
    if gbps <= 10:
        return 1.30
    if gbps <= 16:
        return 1.50
    return 1.70


def _system_scaling_factor(inp: LayoutQuoteInputs, dens_eff: float, coeffs: QuoteCoeffs) -> float:
    layers = float(max(inp.components.layers, 1))
    n_hs = len(inp.highspeed.interfaces)
    scale = 1.0
    scale += 0.05 * max(0.0, (layers - 4.0) / 4.0)
    scale += 0.10 * max(0.0, (dens_eff - 10.0) / 10.0)
    scale += 0.05 * float(n_hs)
    if inp.components.hdi:
        scale *= float(coeffs.k_hdi_multiplier)
    return scale


def estimate_layout_quote(
    inp: LayoutQuoteInputs,
    coeffs: QuoteCoeffs | None = None,
    *,
    ui_complexity: Dict[str, str] | None = None,
    ui_stackup: Dict[str, Any] | None = None,
    ui_signals_count: int | None = None,
) -> Dict[str, Any]:
    coeffs = coeffs or DEFAULT_COEFFS

    dens_top, dens_bottom = _density_pin_per_cm2_layer_sides(inp)
    dens_eff = _density_effective(dens_top, dens_bottom)

    f_pitch = _f_pitch(inp.components.min_bga_pitch_mm)
    f_density = _f_density(dens_eff)
    f_hdi = _f_hdi(inp, coeffs)

    # --- Placement ---
    place_pins_h = (float(coeffs.k_place_pins_per_100_min) / 60.0) * (float(inp.components.bga_total_pins_effective) / 100.0)
    place_passives_h = (float(coeffs.k_place_passive_min) / 60.0) * float(inp.components.passives)
    place_actives_h = (float(coeffs.k_place_active_min) / 60.0) * float(inp.components.actives)
    place_critical_h = (float(coeffs.k_place_critical_min) / 60.0) * float(inp.components.critical)
    place_connectors_h = (float(coeffs.k_place_connector_min) / 60.0) * float(inp.components.connectors)

    t_place = (
        (coeffs.k_place_bga_base_h + coeffs.k_place_per_bga_h * float(inp.components.bga_count))
        + place_pins_h
        + place_passives_h
        + place_actives_h
        + place_critical_h
        + place_connectors_h
    ) * f_pitch * f_density * f_hdi

    # --- Routing HS ---
    t_route_hs = 0.0
    hs_breakdown: List[Dict[str, Any]] = []
    for itf in inp.highspeed.interfaces:
        sev = _severity_from_match_ps(itf.match_ps) * _severity_from_data_rate(itf.data_rate_gbps)
        t_diff = (float(coeffs.k_route_diff_pair_min) / 60.0) * float(itf.diff_pairs) * sev
        t_se = (float(coeffs.k_route_se_min) / 60.0) * float(itf.se_lines) * sev
        t_route_hs += (t_diff + t_se)
        hs_breakdown.append({
            "name": itf.name,
            "data_rate_gbps": itf.data_rate_gbps,
            "match_ps": itf.match_ps,
            "diff_pairs": itf.diff_pairs,
            "se_lines": itf.se_lines,
            "severity": sev,
            "hours_total": t_diff + t_se,
        })

    # --- Routing STD ---
    traces_stand = float(inp.components.passives) * 2.0 + float(inp.components.actives) * 10.0 + float(inp.components.connectors) * 10.0
    t_route_traces = (float(coeffs.k_route_trace_min) / 60.0) * traces_stand * f_density
    t_route_std = float(coeffs.k_route_std_base_h) * f_density + (float(coeffs.k_route_density_scale_h) * dens_eff / 10.0) + t_route_traces

    # --- SI/PI ---
    t_si = float(coeffs.k_si_base_h) * (1.0 + 0.15 * (f_density - 1.0))
    for itf in inp.highspeed.interfaces:
        rate_sev = _severity_from_data_rate(itf.data_rate_gbps)
        t_si += (float(coeffs.k_si_per_interface_min) / 60.0) * float(coeffs.k_si_rate_multiplier) * rate_sev

    # --- DFM/Cleanup ---
    t_route_total = t_route_hs + t_route_std
    t_cleanup_prop = float(coeffs.k_cleanup_pct) * (t_place + t_route_total)
    t_dfm_doc_fixed = float(coeffs.sys_dfm_documentation_h)

    # --- System scaling ---
    sys_fixed = float(coeffs.sys_study_system_h) + float(coeffs.sys_setup_pcb_h) + float(coeffs.sys_mech_study_h)
    sys_scale = _system_scaling_factor(inp, dens_eff, coeffs)
    t_system = sys_fixed * sys_scale

    buffer_factor = 1.0 + float(inp.buffer_pct)

    # Labels compatible with GUI ResultsTab
    hours = {
        "Constraint": float(coeffs.sys_setup_pcb_h),
        "Fattibilità": float(coeffs.feas_base_h),
        "Piazzamento": t_place,
        "Routing Critico": t_route_hs,
        "Routing Standard": t_route_std,
        "SI/PI": t_si,
        "Cleanup": t_cleanup_prop,
        "Documentazione": t_dfm_doc_fixed,
    }

    hours_buf = {k: v * buffer_factor for k, v in hours.items()}
    total_h = sum(hours_buf.values())

    week_hours = float(inp.week_hours) if inp.week_hours else 40.0
    weeks_buf = {k: (v / week_hours) for k, v in hours_buf.items()}
    total_w = total_h / week_hours

    layout_rate = float(inp.tariffs.layout_eur_per_h)
    si_rate = float(inp.tariffs.si_pi_eur_per_h)

    costs_buf = {}
    for k, hbuf in hours_buf.items():
        rate = si_rate if k == "SI/PI" else layout_rate
        costs_buf[k] = hbuf * rate

    total_cost = sum(costs_buf.values())

    return {
        "coeffs": asdict(coeffs) if is_dataclass(coeffs) else coeffs,
        "inputs": asdict(inp) if is_dataclass(inp) else inp,
        "routing_critico": {"interfaces": hs_breakdown},
        "factors": {
            "density_top_pin_per_cm2_layer": dens_top,
            "density_bottom_pin_per_cm2_layer": dens_bottom,
            "density_effective": dens_eff,
            "f_pitch": f_pitch,
            "f_density": f_density,
            "f_hdi": f_hdi,
            "traces_stand": traces_stand,
            "t_route_traces": t_route_traces,
            "sys_scale": sys_scale,
        },
        "breakdown": {
            "hours_with_buffer": hours_buf,
            "weeks_with_buffer": weeks_buf,
            "costs_with_buffer": costs_buf,
            "rates": {"layout": layout_rate, "si_pi": si_rate},
            "totals": {"hours": total_h, "weeks": total_w, "cost": total_cost},
        }
    }