from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal


RowType = Literal["Copper", "Dielectric"]


@dataclass
class StackupRow:
    row_type: RowType
    voce: str

    # Copper
    layer_kind: str = ""
    copper_label: str = ""
    thickness_mm: float = 0.0

    # Dielectric
    dielectric_kind: str = ""
    material: str = ""
    style: str = ""
    plies: int = 1


@dataclass
class StackupSettings:
    pcb_type: str = "Rigid"
    layers: int = 12
    tech: str = "Standard (PTH only)"
    copper_outer: str = "1 oz (35µm)"
    copper_inner: str = "1 oz (35µm)"
    outer_material: str = "FR-4 (generic)"
    inner_material: str = "FR-4 (generic)"
    keep_symmetry: bool = True


@dataclass
class StackupModel:
    settings: StackupSettings = field(default_factory=StackupSettings)
    rows: List[StackupRow] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "settings": {
                "pcb_type": self.settings.pcb_type,
                "layers": int(self.settings.layers),
                "tech": self.settings.tech,
                "copper_outer": self.settings.copper_outer,
                "copper_inner": self.settings.copper_inner,
                "outer_material": self.settings.outer_material,
                "inner_material": self.settings.inner_material,
                "keep_symmetry": bool(self.settings.keep_symmetry),
            },
            "rows": [
                {
                    "row_type": r.row_type,
                    "voce": r.voce,
                    "layer_kind": r.layer_kind,
                    "copper_label": r.copper_label,
                    "thickness_mm": float(r.thickness_mm),
                    "dielectric_kind": r.dielectric_kind,
                    "material": r.material,
                    "style": r.style,
                    "plies": int(r.plies),
                }
                for r in self.rows
            ],
        }

    @staticmethod
    def from_dict(d: dict) -> "StackupModel":
        m = StackupModel()
        s = d.get("settings", {}) or {}
        if isinstance(s, dict):
            m.settings = StackupSettings(
                pcb_type=str(s.get("pcb_type", "Rigid")),
                layers=int(s.get("layers", 12) or 12),
                tech=str(s.get("tech", "Standard (PTH only)")),
                copper_outer=str(s.get("copper_outer", "1 oz (35µm)")),
                copper_inner=str(s.get("copper_inner", "1 oz (35µm)")),
                outer_material=str(s.get("outer_material", "FR-4 (generic)")),
                inner_material=str(s.get("inner_material", "FR-4 (generic)")),
                keep_symmetry=bool(s.get("keep_symmetry", True)),
            )
        rows = d.get("rows", []) or []
        if isinstance(rows, list):
            for rr in rows:
                if not isinstance(rr, dict):
                    continue
                m.rows.append(
                    StackupRow(
                        row_type=str(rr.get("row_type", "Copper")),  # type: ignore[arg-type]
                        voce=str(rr.get("voce", "")),
                        layer_kind=str(rr.get("layer_kind", "")),
                        copper_label=str(rr.get("copper_label", "")),
                        thickness_mm=float(rr.get("thickness_mm", 0.0) or 0.0),
                        dielectric_kind=str(rr.get("dielectric_kind", "")),
                        material=str(rr.get("material", "")),
                        style=str(rr.get("style", "")),
                        plies=int(rr.get("plies", 1) or 1),
                    )
                )
        return m