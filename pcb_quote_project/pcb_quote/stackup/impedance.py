from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class TraceGeometry:
    width_mm: float
    thickness_mm: float
    height_mm: float
    er: float


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def microstrip_z0(g: TraceGeometry) -> float:
    w = max(float(g.width_mm), 1e-6)
    h = max(float(g.height_mm), 1e-6)
    t = max(float(g.thickness_mm), 0.0)
    er = max(float(g.er), 1.0)

    if t > 0:
        we = w + (t / math.pi) * (1.0 + math.log(4.0 * math.e / (t / h + (1.0 / math.pi) ** 2)))
    else:
        we = w

    u = max(we / h, 1e-9)
    eeff = (er + 1.0) / 2.0 + (er - 1.0) / 2.0 * (1.0 / math.sqrt(1.0 + 12.0 / u))

    if u <= 1.0:
        z0 = (60.0 / math.sqrt(eeff)) * math.log(8.0 / u + 0.25 * u)
    else:
        z0 = (120.0 * math.pi) / (math.sqrt(eeff) * (u + 1.393 + 0.667 * math.log(u + 1.444)))

    return float(z0)


def stripline_z0(width_mm: float, height_mm: float, er: float, thickness_mm: float = 0.035) -> float:
    w = max(float(width_mm), 1e-6)
    b = max(float(height_mm), 1e-6)
    t = max(float(thickness_mm), 0.0)
    er = max(float(er), 1.0)

    if t > 0:
        we = w + (t / math.pi) * (1.0 + math.log(4.0 * math.e / (t / b + (1.0 / math.pi) ** 2)))
    else:
        we = w

    u = max(we / b, 1e-9)
    z0 = (30.0 * math.pi / math.sqrt(er)) / (u + 0.441)
    return float(z0)


def solve_microstrip_width(
    *,
    target_ohm: float,
    height_mm: float,
    er: float,
    thickness_mm: float = 0.035,
    w_min_mm: float = 0.03,
    w_max_mm: float = 3.0,
    tol_ohm: float = 0.25,
    max_iter: int = 70,
) -> float:
    target = float(target_ohm)
    lo, hi = float(w_min_mm), float(w_max_mm)

    def f(w: float) -> float:
        return microstrip_z0(TraceGeometry(width_mm=w, thickness_mm=thickness_mm, height_mm=height_mm, er=er))

    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        z = f(mid)
        if abs(z - target) <= tol_ohm:
            return mid
        if z > target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def solve_stripline_width(
    *,
    target_ohm: float,
    height_mm: float,
    er: float,
    thickness_mm: float = 0.035,
    w_min_mm: float = 0.03,
    w_max_mm: float = 3.0,
    tol_ohm: float = 0.25,
    max_iter: int = 70,
) -> float:
    target = float(target_ohm)
    lo, hi = float(w_min_mm), float(w_max_mm)

    def f(w: float) -> float:
        return stripline_z0(width_mm=w, height_mm=height_mm, er=er, thickness_mm=thickness_mm)

    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        z = f(mid)
        if abs(z - target) <= tol_ohm:
            return mid
        if z > target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _k_coupling(spacing_mm: float, height_mm: float, *, stripline: bool) -> float:
    s = max(float(spacing_mm), 1e-6)
    h = max(float(height_mm), 1e-6)
    x = s / h
    if stripline:
        k = 0.50 * math.exp(-1.05 * x)
        return float(_clamp(k, 0.0, 0.50))
    k = 0.40 * math.exp(-1.20 * x)
    return float(_clamp(k, 0.0, 0.40))


def _zodd_zeven_from_z0(z0: float, k: float) -> tuple[float, float]:
    """
    Stable approximation:
      Zodd  ≈ Z0 * (1 - k)
      Zeven ≈ Z0 * (1 + k)
    """
    zodd = float(z0) * (1.0 - float(k))
    zeven = float(z0) * (1.0 + float(k))
    return zodd, zeven


def diffpair_zdiff(z0_single: float, k: float) -> float:
    zodd, _zeven = _zodd_zeven_from_z0(z0_single, k)
    return float(2.0 * zodd)


def solve_diffpair_microstrip(
    *,
    target_zdiff: float,
    height_mm: float,
    er: float,
    thickness_mm: float,
    w_min_mm: float = 0.03,
    w_max_mm: float = 3.0,
    s_min_mm: float = 0.03,
    s_max_mm: float = 3.0,
    tol_ohm: float = 0.75,
) -> tuple[float, float, float]:
    target = float(target_zdiff)

    def zdiff_for(w: float, s: float) -> float:
        z0 = microstrip_z0(TraceGeometry(width_mm=w, thickness_mm=thickness_mm, height_mm=height_mm, er=er))
        k = _k_coupling(s, height_mm, stripline=False)
        return diffpair_zdiff(z0, k)

    slo, shi = float(s_min_mm), float(s_max_mm)
    best_w, best_s, best_err = 0.2, 0.2, 1e9

    for _ in range(45):
        s_mid = 0.5 * (slo + shi)

        wlo, whi = float(w_min_mm), float(w_max_mm)
        for _ in range(60):
            w_mid = 0.5 * (wlo + whi)
            z = zdiff_for(w_mid, s_mid)
            err = z - target
            if abs(err) < abs(best_err):
                best_w, best_s, best_err = w_mid, s_mid, err
            if abs(err) <= tol_ohm:
                break
            # wider -> lower z0 -> lower zdiff
            if z > target:
                wlo = w_mid
            else:
                whi = w_mid

        z_here = zdiff_for(best_w, s_mid)
        # spacing larger -> coupling smaller -> zdiff larger
        if z_here > target:
            shi = s_mid
        else:
            slo = s_mid

    achieved = zdiff_for(best_w, best_s)
    return float(best_w), float(best_s), float(achieved)


def solve_diffpair_stripline(
    *,
    target_zdiff: float,
    height_mm: float,
    er: float,
    thickness_mm: float,
    w_min_mm: float = 0.03,
    w_max_mm: float = 3.0,
    s_min_mm: float = 0.03,
    s_max_mm: float = 3.0,
    tol_ohm: float = 0.75,
) -> tuple[float, float, float]:
    target = float(target_zdiff)

    def zdiff_for(w: float, s: float) -> float:
        z0 = stripline_z0(width_mm=w, height_mm=height_mm, er=er, thickness_mm=thickness_mm)
        k = _k_coupling(s, height_mm, stripline=True)
        return diffpair_zdiff(z0, k)

    slo, shi = float(s_min_mm), float(s_max_mm)
    best_w, best_s, best_err = 0.2, 0.2, 1e9

    for _ in range(45):
        s_mid = 0.5 * (slo + shi)

        wlo, whi = float(w_min_mm), float(w_max_mm)
        for _ in range(60):
            w_mid = 0.5 * (wlo + whi)
            z = zdiff_for(w_mid, s_mid)
            err = z - target
            if abs(err) < abs(best_err):
                best_w, best_s, best_err = w_mid, s_mid, err
            if abs(err) <= tol_ohm:
                break
            if z > target:
                wlo = w_mid
            else:
                whi = w_mid

        z_here = zdiff_for(best_w, s_mid)
        if z_here > target:
            shi = s_mid
        else:
            slo = s_mid

    achieved = zdiff_for(best_w, best_s)
    return float(best_w), float(best_s), float(achieved)