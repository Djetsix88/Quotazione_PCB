from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Tuple


Complexity = Literal["Bassa", "Media", "Alta"]
SectionName = Literal["Segnale", "Power", "RF", "High speed"]

CATEGORIES: Tuple[str, ...] = ("BGA", "Passivi", "Attivi", "Critici", "Connettori")


def complexity_factor(c: str) -> float:
    c = (c or "").strip().lower()
    if c.startswith("bassa"):
        return 1.0
    if c.startswith("alta"):
        return 1.8
    return 1.3  # media


def complexity_class_from_score(score: float) -> Complexity:
    """
    Converte lo score (somma(qty * fattore)) in una classe leggibile.
    Soglie semplici (per sezione):
      - <= 25  -> Bassa
      - <= 60  -> Media
      - >  60  -> Alta
    """
    s = float(score or 0.0)
    if s <= 25.0:
        return "Bassa"
    if s <= 60.0:
        return "Media"
    return "Alta"


@dataclass
class ComponentRow:
    categoria: str
    quantita: int = 0
    pin: int = 0
    pitch_min_mm: float = 0.0  # usato solo per BGA
    complessita: Complexity = "Media"
    note: str = ""

    @property
    def pin_totali(self) -> int:
        q = max(0, int(self.quantita))
        p = max(0, int(self.pin))
        return q * p


@dataclass
class ComponentsSectionModel:
    name: SectionName
    rows: List[ComponentRow] = field(default_factory=list)

    def ensure_default_rows(self) -> None:
        if self.rows:
            return
        for cat in CATEGORIES:
            self.rows.append(
                ComponentRow(
                    categoria=cat,
                    quantita=0,
                    pin=0,
                    pitch_min_mm=(0.80 if cat == "BGA" else 0.0),
                    complessita=("Media" if cat in ("BGA", "Attivi") else "Bassa"),
                    note="",
                )
            )

    def totals(self) -> Dict[str, float]:
        qty = sum(max(0, int(r.quantita)) for r in self.rows)
        pins = sum(max(0, int(r.pin_totali)) for r in self.rows)
        score = 0.0
        for r in self.rows:
            score += complexity_factor(r.complessita) * float(max(0, int(r.quantita)))
        pitch = 0.0
        for r in self.rows:
            if r.categoria == "BGA":
                pitch = float(r.pitch_min_mm or 0.0)
        return {"qty": float(qty), "pins": float(pins), "score": float(score), "pitch_bga_mm": float(pitch)}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "rows": [
                {
                    "categoria": r.categoria,
                    "quantita": int(r.quantita),
                    "pin": int(r.pin),
                    "pitch_min_mm": float(r.pitch_min_mm),
                    "complessita": r.complessita,
                    "note": r.note,
                }
                for r in self.rows
            ],
        }

    @staticmethod
    def from_dict(d: dict) -> "ComponentsSectionModel":
        name = d.get("name", "Segnale")
        m = ComponentsSectionModel(name=name)  # type: ignore[arg-type]
        rows = d.get("rows", []) or []
        if isinstance(rows, list):
            for rr in rows:
                if not isinstance(rr, dict):
                    continue
                m.rows.append(
                    ComponentRow(
                        categoria=str(rr.get("categoria", "")),
                        quantita=int(rr.get("quantita", 0) or 0),
                        pin=int(rr.get("pin", 0) or 0),
                        pitch_min_mm=float(rr.get("pitch_min_mm", 0.0) or 0.0),
                        complessita=str(rr.get("complessita", "Media")) if rr.get("complessita") else "Media",  # type: ignore[assignment]
                        note=str(rr.get("note", "")),
                    )
                )
        m._normalize()
        return m

    def _normalize(self) -> None:
        by_cat = {r.categoria: r for r in self.rows}
        self.rows = []
        for cat in CATEGORIES:
            if cat in by_cat:
                self.rows.append(by_cat[cat])
            else:
                self.rows.append(ComponentRow(categoria=cat))
        for r in self.rows:
            if r.categoria == "BGA" and (r.pitch_min_mm is None):
                r.pitch_min_mm = 0.80


@dataclass
class ComponentsModel:
    sections: Dict[SectionName, ComponentsSectionModel] = field(default_factory=dict)

    def ensure_defaults(self) -> None:
        for sec in ("Segnale", "Power", "RF", "High speed"):
            s = self.sections.get(sec)  # type: ignore[index]
            if s is None:
                s = ComponentsSectionModel(name=sec)  # type: ignore[arg-type]
                self.sections[sec] = s  # type: ignore[index]
            s.ensure_default_rows()

    def to_dict(self) -> dict:
        self.ensure_defaults()
        return {"sections": {k: v.to_dict() for k, v in self.sections.items()}}

    @staticmethod
    def from_dict(d: dict) -> "ComponentsModel":
        m = ComponentsModel()
        sec_d = d.get("sections", {}) or {}
        if isinstance(sec_d, dict):
            for _k, v in sec_d.items():
                if isinstance(v, dict):
                    try:
                        sec = ComponentsSectionModel.from_dict(v)
                        m.sections[sec.name] = sec
                    except Exception:
                        pass
        m.ensure_defaults()
        return m