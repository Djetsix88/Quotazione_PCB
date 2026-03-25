from __future__ import annotations
from dataclasses import dataclass, field
from typing import List


@dataclass
class Tariffs:
    layout_eur_per_h: float = 75.0
    si_pi_eur_per_h: float = 90.0


@dataclass
class HoleType:
    diameter_mm: float
    metallization_mm: float = 0.0  # nuovo campo: spessore metallizzazione (radiale) in mm
    count: int = 1

    @property
    def effective_diameter_mm(self) -> float:
        # la metallizzazione viene considerata come spessore radiale su entrambi i lati del foro
        return float(self.diameter_mm) + 2.0 * float(self.metallization_mm)

    @property
    def area_mm2(self) -> float:
        r = self.effective_diameter_mm / 2.0
        return 3.141592653589793 * r * r * float(self.count)


@dataclass
class KeepoutRect:
    side: str  # "TOP" | "BOTTOM"
    width_mm: float
    height_mm: float
    count: int = 1

    @property
    def area_mm2(self) -> float:
        return float(self.width_mm) * float(self.height_mm) * float(self.count)


@dataclass
class BoardConstraints:
    width_mm: float = 180.0
    height_mm: float = 140.0
    holes: List[HoleType] = field(default_factory=list)
    keepouts: List[KeepoutRect] = field(default_factory=list)

    @property
    def gross_mm2(self) -> float:
        return self.width_mm * self.height_mm

    @property
    def gross_cm2(self) -> float:
        return self.gross_mm2 / 100.0

    @property
    def holes_area_mm2(self) -> float:
        return sum(h.area_mm2 for h in self.holes)

    def keepout_area_mm2(self, side: str) -> float:
        side = side.upper()
        return sum(k.area_mm2 for k in self.keepouts if k.side.upper() == side)

    @property
    def keepout_top_mm2(self) -> float:
        return self.keepout_area_mm2("TOP")

    @property
    def keepout_bottom_mm2(self) -> float:
        return self.keepout_area_mm2("BOTTOM")

    @property
    def usable_top_mm2(self) -> float:
        return max(self.gross_mm2 - self.holes_area_mm2 - self.keepout_top_mm2, 0.0)

    @property
    def usable_bottom_mm2(self) -> float:
        return max(self.gross_mm2 - self.holes_area_mm2 - self.keepout_bottom_mm2, 0.0)

    @property
    def usable_top_cm2(self) -> float:
        return self.usable_top_mm2 / 100.0

    @property
    def usable_bottom_cm2(self) -> float:
        return self.usable_bottom_mm2 / 100.0

    @property
    def occupied_top_pct(self) -> float:
        if self.gross_mm2 <= 0:
            return 0.0
        occ = self.holes_area_mm2 + self.keepout_top_mm2
        return max(min(100.0 * occ / self.gross_mm2, 100.0), 0.0)

    @property
    def occupied_bottom_pct(self) -> float:
        if self.gross_mm2 <= 0:
            return 0.0
        occ = self.holes_area_mm2 + self.keepout_bottom_mm2
        return max(min(100.0 * occ / self.gross_mm2, 100.0), 0.0)

    @property
    def free_top_pct(self) -> float:
        return max(100.0 - self.occupied_top_pct, 0.0)

    @property
    def free_bottom_pct(self) -> float:
        return max(100.0 - self.occupied_bottom_pct, 0.0)


@dataclass
class ComponentsInputs:
    bga_count: int = 0
    bga_total_pins_effective: int = 0
    min_bga_pitch_mm: float = 0.8

    passives: int = 0
    actives: int = 0
    critical: int = 0
    connectors: int = 0

    layers: int = 12
    hdi: bool = True
    tht: bool = False


@dataclass
class HighSpeedInterface:
    name: str = "JESD204"
    data_rate_gbps: float = 10.0
    diff_pairs: int = 0
    se_lines: int = 0
    match_ps: float = 10.0


@dataclass
class HighSpeedInputs:
    interfaces: List[HighSpeedInterface] = field(default_factory=list)


@dataclass
class LayoutQuoteInputs:
    board: BoardConstraints = field(default_factory=BoardConstraints)
    components: ComponentsInputs = field(default_factory=ComponentsInputs)
    highspeed: HighSpeedInputs = field(default_factory=HighSpeedInputs)

    buffer_pct: float = 0.25
    week_hours: float = 40.0
    tariffs: Tariffs = field(default_factory=Tariffs)