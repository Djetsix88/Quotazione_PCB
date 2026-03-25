from __future__ import annotations

from typing import Any, Dict, List

from PySide6.QtCore import Qt, Signal, QTimer, QObject, QEvent
from PySide6.QtGui import QColor, QBrush, QFont
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QDoubleSpinBox, QSpinBox, QVBoxLayout,
    QPushButton, QTabWidget, QHBoxLayout, QGroupBox, QLabel,
    QTableWidget, QTableWidgetItem, QDialog, QDialogButtonBox, QGridLayout,
    QHeaderView, QSizePolicy, QAbstractItemView, QComboBox, QCheckBox
)

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from pcb_quote.models import (
    LayoutQuoteInputs, BoardConstraints, HoleType, KeepoutRect,
    ComponentsInputs, HighSpeedInputs, HighSpeedInterface, Tariffs
)
from pcb_quote.calculations import (
    estimate_layout_quote, QuoteCoeffs, DEFAULT_COEFFS,
    SectionComplexityRules, section_complexity_score, section_complexity_class
)
from pcb_quote import io_utils


class _ClearSelectionFilter(QObject):
    def __init__(self, tables: list[QTableWidget]):
        super().__init__()
        self._tables = tables

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.MouseButtonPress:
            for t in self._tables:
                if t is None:
                    continue
                if t.viewport().underMouse() or t.underMouse():
                    return False
            for t in self._tables:
                if t is None:
                    continue
                t.clearSelection()
                t.setCurrentCell(-1, -1)
        return False


def groupbox(title: str, layout) -> QGroupBox:
    b = QGroupBox(title)
    b.setLayout(layout)
    return b


def _note_label(text: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color: #5a6b7b; font-size: 9pt;")
    return lbl


def _ro_item(s: str) -> QTableWidgetItem:
    it = QTableWidgetItem(str(s))
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    it.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
    it.setData(Qt.TextAlignmentRole, int(Qt.AlignVCenter | Qt.AlignLeft))
    return it


def _num_item(val: str) -> QTableWidgetItem:
    it = QTableWidgetItem(val)
    it.setTextAlignment(Qt.AlignVCenter | Qt.AlignRight)
    it.setData(Qt.TextAlignmentRole, int(Qt.AlignVCenter | Qt.AlignRight))
    return it


def _text_item(val: str) -> QTableWidgetItem:
    it = QTableWidgetItem(val)
    it.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
    it.setData(Qt.TextAlignmentRole, int(Qt.AlignVCenter | Qt.AlignLeft))
    return it


def _configure_table(
    tbl: QTableWidget,
    *,
    stretch_last: bool = True,
    editable: bool = True,
    selection_rows: bool = True,
    header_h: int = 40,
    row_h: int = 36,
):
    tbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    tbl.setAlternatingRowColors(True)
    tbl.setShowGrid(True)
    tbl.setWordWrap(False)
    tbl.setTextElideMode(Qt.ElideNone)

    if editable:
        tbl.setEditTriggers(
            QAbstractItemView.DoubleClicked |
            QAbstractItemView.EditKeyPressed |
            QAbstractItemView.AnyKeyPressed |
            QAbstractItemView.SelectedClicked
        )
    else:
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)

    tbl.setSelectionBehavior(QAbstractItemView.SelectRows if selection_rows else QAbstractItemView.SelectItems)
    tbl.setSelectionMode(QAbstractItemView.SingleSelection)
    tbl.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    tbl.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    vh = tbl.verticalHeader()
    vh.setVisible(True)
    vh.setDefaultSectionSize(row_h)
    vh.setMinimumSectionSize(max(28, row_h - 6))
    vh.setSectionResizeMode(QHeaderView.Fixed)
    vh.setSectionsMovable(False)

    hh = tbl.horizontalHeader()
    hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    hh.setSectionsMovable(False)
    hh.setSectionResizeMode(QHeaderView.Interactive)
    hh.setStretchLastSection(stretch_last)
    hh.setFixedHeight(header_h)


def _autosize_table(tbl: QTableWidget, max_visible_rows: int = 12):
    rows = max(1, min(tbl.rowCount(), max_visible_rows))
    row_h = max(28, tbl.verticalHeader().defaultSectionSize())
    header_h = tbl.horizontalHeader().height()
    frame = tbl.frameWidth() * 2
    total_h = header_h + rows * row_h + frame + 18
    tbl.setMinimumHeight(total_h)


def _parse_hole_entry(h: Any):
    try:
        if isinstance(h, HoleType):
            return h
        if isinstance(h, dict):
            return HoleType(
                diameter_mm=float(h.get("diameter_mm", 0.0)),
                metallization_mm=float(h.get("metallization_mm", 0.0)),
                count=int(h.get("count", 1)),
            )
    except Exception:
        pass
    return None


def _parse_keepout_entry(k: Any):
    try:
        if isinstance(k, KeepoutRect):
            return k
        if isinstance(k, dict):
            return KeepoutRect(
                side=str(k.get("side", "TOP")).upper(),
                width_mm=float(k.get("width_mm", 0.0)),
                height_mm=float(k.get("height_mm", 0.0)),
                count=int(k.get("count", 1)),
            )
    except Exception:
        pass
    return None


def _parse_hs_entry(it: Any):
    try:
        if isinstance(it, HighSpeedInterface):
            return it
        if isinstance(it, dict):
            return HighSpeedInterface(
                name=str(it.get("name", "IF")),
                data_rate_gbps=float(it.get("data_rate_gbps", 0.0)),
                diff_pairs=int(it.get("diff_pairs", 0)),
                se_lines=int(it.get("se_lines", 0)),
                match_ps=float(it.get("match_ps", 50.0)),
            )
    except Exception:
        pass
    return None


# =========================
# CoeffsDialog
# =========================
class CoeffsDialog(QDialog):
    def __init__(self, coeffs: QuoteCoeffs, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Coefficienti di stima")
        self.coeffs = coeffs
        outer = QVBoxLayout(self)
        outer.addWidget(_note_label("Coefficienti del modello + regole complessità per sezione (configurabili)."))
        grid = QGridLayout()
        outer.addLayout(grid)
        self._num: dict[str, QDoubleSpinBox] = {}
        self._rules: dict[str, dict[str, QDoubleSpinBox]] = {}

        def add_num(r: int, key: str, label: str, value: float, minv=0.0, maxv=1e6, step=0.1, decimals=3):
            lab = QLabel(label); lab.setStyleSheet("font-weight: 600;")
            sp = QDoubleSpinBox()
            sp.setRange(minv, maxv)
            sp.setDecimals(decimals)
            sp.setSingleStep(step)
            sp.setValue(float(value))
            grid.addWidget(lab, r, 0)
            grid.addWidget(sp, r, 1)
            self._num[key] = sp

        def add_rules_block(start_r: int, title: str, rules: SectionComplexityRules, key_prefix: str):
            hdr = QLabel(title)
            hdr.setStyleSheet("font-weight:800; padding-top:10px;")
            grid.addWidget(hdr, start_r, 0, 1, 3)

            fields: dict[str, QDoubleSpinBox] = {}
            rr = start_r + 1

            def add(k: str, label: str, val: float, minv=0.0, maxv=1e6, step=0.05, decimals=3):
                nonlocal rr
                lab = QLabel(label)
                sp = QDoubleSpinBox()
                sp.setRange(minv, maxv)
                sp.setDecimals(decimals)
                sp.setSingleStep(step)
                sp.setValue(float(val))
                grid.addWidget(lab, rr, 0)
                grid.addWidget(sp, rr, 1)
                fields[k] = sp
                rr += 1

            add("w_qty", "Peso Qty", rules.w_qty)
            add("w_pins_per_k", "Peso Pins/1000", rules.w_pins_per_k)
            add("w_bga_qty", "Peso BGA Qty", rules.w_bga_qty)
            add("w_pitch", "Peso Pitch", rules.w_pitch)
            add("w_critical_qty", "Peso Critici Qty", rules.w_critical_qty)
            add("w_connectors_qty", "Peso Connettori Qty", rules.w_connectors_qty)

            add("thr_low", "Soglia Bassa", rules.thr_low, 0.0, 1e6, 0.5, 2)
            add("thr_med", "Soglia Media", rules.thr_med, 0.0, 1e6, 0.5, 2)

            self._rules[key_prefix] = fields
            return rr

        c = coeffs
        r = 0
        add_num(r, "sys_setup_pcb_h", "Constraint (ore)", c.sys_setup_pcb_h, 0, 200, 0.5, 2); r += 1
        add_num(r, "feas_base_h", "Fattibilità base (ore)", c.feas_base_h, 0, 200, 0.5, 2); r += 1
        add_num(r, "feas_per_interface_min", "Fattibilità per interfaccia (min)", c.feas_per_interface_min, 0, 600, 5, 1); r += 1
        add_num(r, "feas_stackup_base_h", "Fattibilità stack-up base (ore)", c.feas_stackup_base_h, 0, 50, 0.25, 2); r += 1
        add_num(r, "feas_stackup_tech_mult_hdi", "Moltiplicatore tech HDI", c.feas_stackup_tech_mult_hdi, 1.0, 5.0, 0.05, 2); r += 1
        add_num(r, "feas_stackup_tech_mult_adv", "Moltiplicatore tech Advanced", c.feas_stackup_tech_mult_adv, 1.0, 5.0, 0.05, 2); r += 1

        add_num(r, "crit_extra_power_h", "Extra Routing Critico - Power (ore)", c.crit_extra_power_h, 0, 200, 0.5, 2); r += 1
        add_num(r, "crit_extra_rf_h", "Extra Routing Critico - RF (ore)", c.crit_extra_rf_h, 0, 200, 0.5, 2); r += 1
        add_num(r, "crit_extra_highspeed_h", "Extra Routing Critico - High speed (ore)", c.crit_extra_highspeed_h, 0, 200, 0.5, 2); r += 1

        add_num(r, "cplx_mult_low", "Moltiplicatore complessità Bassa", c.cplx_mult_low, 0.1, 10.0, 0.05, 2); r += 1
        add_num(r, "cplx_mult_med", "Moltiplicatore complessità Media", c.cplx_mult_med, 0.1, 10.0, 0.05, 2); r += 1
        add_num(r, "cplx_mult_high", "Moltiplicatore complessità Alta", c.cplx_mult_high, 0.1, 10.0, 0.05, 2); r += 1

        r += 1
        r = add_rules_block(r, "Regole complessità - Segnale", c.rules_signal, "rules_signal")
        r += 1
        r = add_rules_block(r, "Regole complessità - Power", c.rules_power, "rules_power")
        r += 1
        r = add_rules_block(r, "Regole complessità - RF", c.rules_rf, "rules_rf")
        r += 1
        r = add_rules_block(r, "Regole complessità - High speed", c.rules_highspeed, "rules_highspeed")
        r += 1

        add_num(r, "k_place_bga_base_h", "Placement base BGA (ore)", c.k_place_bga_base_h, 0, 500, 0.5, 2); r += 1
        add_num(r, "k_place_per_bga_h", "Placement per BGA (ore)", c.k_place_per_bga_h, 0, 100, 0.25, 2); r += 1
        add_num(r, "k_place_pins_per_100_min", "Placement per 100 pin BGA (min)", c.k_place_pins_per_100_min, 0, 600, 5, 1); r += 1

        add_num(r, "k_place_passive_min", "Placement passivo (min/pezzo)", c.k_place_passive_min, 0, 10, 0.01, 3); r += 1
        add_num(r, "k_place_active_min", "Placement attivo (min/pezzo)", c.k_place_active_min, 0, 60, 0.1, 2); r += 1
        add_num(r, "k_place_critical_min", "Placement critico (min/pezzo)", c.k_place_critical_min, 0, 300, 0.5, 1); r += 1
        add_num(r, "k_place_connector_min", "Placement connettore (min/pezzo)", c.k_place_connector_min, 0, 120, 0.5, 1); r += 1

        add_num(r, "k_hdi_multiplier", "Moltiplicatore HDI", c.k_hdi_multiplier, 1.0, 5.0, 0.05, 2); r += 1

        add_num(r, "k_route_std_base_h", "Routing Standard base (ore)", c.k_route_std_base_h, 0, 2000, 1.0, 1); r += 1
        add_num(r, "k_route_density_scale_h", "Routing Standard per densità (ore)", c.k_route_density_scale_h, 0, 2000, 1.0, 1); r += 1
        add_num(r, "k_route_trace_min", "Routing per traccia (min/traccia)", c.k_route_trace_min, 0.01, 10.0, 0.01, 3); r += 1

        add_num(r, "k_route_diff_pair_min", "Routing Critico: diff pair (min/coppia)", c.k_route_diff_pair_min, 0, 1000, 1.0, 1); r += 1
        add_num(r, "k_route_se_min", "Routing Critico: SE (min/linea)", c.k_route_se_min, 0, 500, 0.5, 1); r += 1

        add_num(r, "k_si_base_h", "SI/PI base (ore)", c.k_si_base_h, 0, 2000, 1.0, 1); r += 1
        add_num(r, "k_si_per_interface_min", "SI per interfaccia (min)", c.k_si_per_interface_min, 0, 5000, 10.0, 0); r += 1
        add_num(r, "k_si_rate_multiplier", "Moltiplicatore SI", c.k_si_rate_multiplier, 0.0, 10.0, 0.05, 2); r += 1

        add_num(r, "k_cleanup_pct", "Cleanup (%)", c.k_cleanup_pct, 0.0, 1.0, 0.01, 4); r += 1

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _get_rules(self, prefix: str) -> SectionComplexityRules:
        f = self._rules[prefix]
        return SectionComplexityRules(
            w_qty=float(f["w_qty"].value()),
            w_pins_per_k=float(f["w_pins_per_k"].value()),
            w_bga_qty=float(f["w_bga_qty"].value()),
            w_pitch=float(f["w_pitch"].value()),
            w_critical_qty=float(f["w_critical_qty"].value()),
            w_connectors_qty=float(f["w_connectors_qty"].value()),
            thr_low=float(f["thr_low"].value()),
            thr_med=float(f["thr_med"].value()),
        )

    def get_coeffs(self) -> QuoteCoeffs:
        d = {k: float(w.value()) for k, w in self._num.items()}
        d["rules_signal"] = self._get_rules("rules_signal")
        d["rules_power"] = self._get_rules("rules_power")
        d["rules_rf"] = self._get_rules("rules_rf")
        d["rules_highspeed"] = self._get_rules("rules_highspeed")
        return QuoteCoeffs(**d)


# =========================
# TAB: Meccanica
# =========================
class MechTab(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)

        dim_form = QFormLayout()
        dim_form.setLabelAlignment(Qt.AlignRight)
        dim_form.setFormAlignment(Qt.AlignTop)
        self.w_mm = QDoubleSpinBox(); self.w_mm.setRange(1, 5000); self.w_mm.setValue(180); self.w_mm.setSuffix(" mm")
        self.h_mm = QDoubleSpinBox(); self.h_mm.setRange(1, 5000); self.h_mm.setValue(140); self.h_mm.setSuffix(" mm")
        self.t_mm = QDoubleSpinBox(); self.t_mm.setRange(0.20, 10.0); self.t_mm.setDecimals(3); self.t_mm.setValue(1.600); self.t_mm.setSuffix(" mm")
        dim_form.addRow("PCB Width", self.w_mm)
        dim_form.addRow("PCB Height", self.h_mm)
        dim_form.addRow("PCB Thickness", self.t_mm)
        outer.addWidget(groupbox("Dimensioni", dim_form))

        top_row = QHBoxLayout(); top_row.setSpacing(12)

        holes_box = QGroupBox("Fori"); holes_v = QVBoxLayout(holes_box)
        holes_btn = QHBoxLayout(); self.hole_add = QPushButton("Aggiungi"); self.hole_del = QPushButton("Rimuovi")
        holes_btn.addWidget(self.hole_add); holes_btn.addWidget(self.hole_del); holes_btn.addStretch()
        self.holes_table = QTableWidget(0, 3); self.holes_table.setHorizontalHeaderLabels(["Diametro (mm)", "Metallizzazione (mm)", "Quantità"])
        _configure_table(self.holes_table, editable=True, header_h=36, row_h=34)
        holes_v.addLayout(holes_btn); holes_v.addWidget(self.holes_table)

        keep_box = QGroupBox("Keep-out"); keep_v = QVBoxLayout(keep_box)
        keep_btn = QHBoxLayout(); self.keep_add = QPushButton("Aggiungi"); self.keep_del = QPushButton("Rimuovi")
        keep_btn.addWidget(self.keep_add); keep_btn.addWidget(self.keep_del); keep_btn.addStretch()
        self.keep_table = QTableWidget(0, 4); self.keep_table.setHorizontalHeaderLabels(["Lato", "W (mm)", "H (mm)", "Qty"])
        _configure_table(self.keep_table, editable=True, header_h=36, row_h=34)
        keep_v.addLayout(keep_btn); keep_v.addWidget(self.keep_table)

        top_row.addWidget(holes_box, 1)
        top_row.addWidget(keep_box, 1)
        outer.addLayout(top_row)

        bottom_row = QHBoxLayout()
        summary_box = QGroupBox("Riepilogo Area")
        summary_layout = QVBoxLayout(summary_box)
        self.summary_table = QTableWidget(6, 3); self.summary_table.setHorizontalHeaderLabels(["Voce", "TOP", "BOTTOM"])
        self.summary_table.verticalHeader().setVisible(False)
        _configure_table(self.summary_table, editable=False, header_h=36, row_h=30, selection_rows=False)
        self.summary_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        summary_layout.addWidget(self.summary_table)
        bottom_row.addWidget(summary_box, 1)
        bottom_row.addStretch(1)
        outer.addLayout(bottom_row)

        self.hole_add.clicked.connect(lambda: self.add_hole_row(3.2, 0.0, 1)); self.hole_del.clicked.connect(self.del_hole_row)
        self.keep_add.clicked.connect(lambda: self.add_keepout_row("TOP", 10, 10, 1)); self.keep_del.clicked.connect(self.del_keepout_row)

        self._debounce = QTimer(self); self._debounce.setSingleShot(True); self._debounce.setInterval(200); self._debounce.timeout.connect(self.update_area_summary)
        self.w_mm.valueChanged.connect(self._schedule_update); self.h_mm.valueChanged.connect(self._schedule_update)
        self.holes_table.itemChanged.connect(self._schedule_update); self.keep_table.itemChanged.connect(self._schedule_update)

        self.add_hole_row(3.2, 0.0, 4)
        self.update_area_summary()

        _autosize_table(self.holes_table, max_visible_rows=10)
        _autosize_table(self.summary_table, max_visible_rows=10)

    def _schedule_update(self): self._debounce.start()

    def add_hole_row(self, diameter: float = 3.2, metall: float = 0.0, count: int = 1):
        r = self.holes_table.rowCount(); self.holes_table.insertRow(r)
        self.holes_table.setItem(r, 0, _num_item(f"{float(diameter):.2f}"))
        self.holes_table.setItem(r, 1, _num_item(f"{float(metall):.3f}"))
        self.holes_table.setItem(r, 2, _num_item(str(int(count))))
        _autosize_table(self.holes_table, max_visible_rows=10)

    def del_hole_row(self):
        r = self.holes_table.currentRow()
        if r >= 0:
            self.holes_table.removeRow(r)
            self._schedule_update()

    def add_keepout_row(self, side: str = "TOP", w: float = 10.0, h: float = 10.0, count: int = 1):
        r = self.keep_table.rowCount(); self.keep_table.insertRow(r)
        self.keep_table.setItem(r, 0, _text_item(side))
        self.keep_table.setItem(r, 1, _num_item(f"{float(w):.2f}"))
        self.keep_table.setItem(r, 2, _num_item(f"{float(h):.2f}"))
        self.keep_table.setItem(r, 3, _num_item(str(int(count))))
        _autosize_table(self.keep_table, max_visible_rows=10)

    def del_keepout_row(self):
        r = self.keep_table.currentRow()
        if r >= 0:
            self.keep_table.removeRow(r)
            self._schedule_update()

    def collect_holes(self):
        holes = []
        for r in range(self.holes_table.rowCount()):
            d_txt = self.holes_table.item(r, 0).text().strip() if self.holes_table.item(r, 0) else "0"
            m_txt = self.holes_table.item(r, 1).text().strip() if self.holes_table.item(r, 1) else "0"
            c_txt = self.holes_table.item(r, 2).text().strip() if self.holes_table.item(r, 2) else "0"
            try:
                d = float(d_txt); m = float(m_txt); c = int(float(c_txt))
            except Exception:
                continue
            if d > 0 and c > 0:
                holes.append(HoleType(diameter_mm=d, metallization_mm=m, count=c))
        return holes

    def collect_keepouts(self):
        keepouts = []
        for r in range(self.keep_table.rowCount()):
            s = (self.keep_table.item(r, 0).text().strip() if self.keep_table.item(r, 0) else "TOP").upper()
            w_txt = self.keep_table.item(r, 1).text().strip() if self.keep_table.item(r, 1) else "0"
            h_txt = self.keep_table.item(r, 2).text().strip() if self.keep_table.item(r, 2) else "0"
            c_txt = self.keep_table.item(r, 3).text().strip() if self.keep_table.item(r, 3) else "1"
            try:
                w = float(w_txt); h = float(h_txt); c = int(float(c_txt))
            except Exception:
                continue
            if w > 0 and h > 0 and c > 0:
                keepouts.append(KeepoutRect(side=s, width_mm=w, height_mm=h, count=c))
        return keepouts

    def update_area_summary(self):
        board = BoardConstraints(
            width_mm=float(self.w_mm.value()),
            height_mm=float(self.h_mm.value()),
            holes=self.collect_holes(),
            keepouts=self.collect_keepouts(),
        )

        def set_row(row: int, label: str, top: str, bottom: str):
            self.summary_table.setItem(row, 0, _ro_item(label))
            self.summary_table.setItem(row, 1, _ro_item(top))
            self.summary_table.setItem(row, 2, _ro_item(bottom))

        holes_cm2 = board.holes_area_mm2 / 100.0
        set_row(0, "Area lorda (cm²)", f"{board.gross_cm2:.1f}", f"{board.gross_cm2:.1f}")
        set_row(1, "Area fori (cm²)", f"{holes_cm2:.1f}", f"{holes_cm2:.1f}")
        set_row(2, "Keep-out (cm²)", f"{board.keepout_top_mm2/100.0:.1f}", f"{board.keepout_bottom_mm2/100.0:.1f}")
        set_row(3, "Superficie utile (cm²)", f"{board.usable_top_cm2:.1f}", f"{board.usable_bottom_cm2:.1f}")
        set_row(4, "Occupazione %", f"{board.occupied_top_pct:.1f}%", f"{board.occupied_bottom_pct:.1f}%")
        set_row(5, "Spazio libero %", f"{board.free_top_pct:.1f}%", f"{board.free_bottom_pct:.1f}%")
        _autosize_table(self.summary_table, max_visible_rows=10)


# =========================
# TAB: Componenti (come da tua richiesta)
# =========================
class ComponentsTab(QWidget):
    sections = ("Segnale", "Power", "RF", "High speed")
    categories = ("BGA", "Passivi", "Attivi", "Critici", "Connettori")

    def __init__(self, coeffs_provider):
        super().__init__()
        self._coeffs_provider = coeffs_provider
        self.tables: dict[str, QTableWidget] = {}
        self._updating = False

        outer = QVBoxLayout(self)
        grid = QGridLayout()
        grid.setSpacing(12)
        outer.addLayout(grid)

        for idx, sec in enumerate(self.sections):
            box = QGroupBox(f"Componenti - {sec}")
            v = QVBoxLayout(box)

            tbl = QTableWidget(6, 6)
            tbl.setHorizontalHeaderLabels(["Categoria", "Quantità", "Pin", "Pin totali", "Pitch min (mm)", "Note"])
            _configure_table(tbl, editable=True, selection_rows=False, header_h=38, row_h=34)
            tbl.verticalHeader().setVisible(False)

            for r, cat in enumerate(self.categories):
                tbl.setItem(r, 0, _ro_item(cat))
                tbl.setItem(r, 1, _num_item("0"))
                tbl.setItem(r, 2, _num_item("0"))
                tbl.setItem(r, 3, _ro_item("0"))
                tbl.setItem(r, 4, _num_item("0.80" if cat == "BGA" else ""))
                tbl.setItem(r, 5, _text_item(""))

            sum_r = 5
            tbl.setItem(sum_r, 0, _ro_item("RIEPILOGO"))
            for c in range(1, 6):
                tbl.setItem(sum_r, c, _ro_item(""))

            red = QBrush(QColor("#c0392b"))
            bold = QFont(); bold.setBold(True)
            for c in range(0, 6):
                it = tbl.item(sum_r, c)
                if it:
                    it.setFont(bold)
                    it.setForeground(red)

            tbl.itemChanged.connect(lambda _=None, s=sec: self._recalc_section(s))
            self.tables[sec] = tbl
            v.addWidget(tbl)

            grid.addWidget(box, idx // 2, idx % 2)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        for s in self.sections:
            self._recalc_section(s)
        QTimer.singleShot(0, self._uniform_columns)

    def _uniform_columns(self):
        maxw = [0] * 6
        for sec in self.sections:
            t = self.tables[sec]
            t.resizeColumnsToContents()
            for c in range(6):
                maxw[c] = max(maxw[c], t.columnWidth(c))
        for sec in self.sections:
            t = self.tables[sec]
            for c in range(6):
                t.setColumnWidth(c, maxw[c])
            _autosize_table(t, max_visible_rows=9)

    def _int_cell(self, tbl: QTableWidget, r: int, c: int) -> int:
        try:
            t = tbl.item(r, c).text().strip() if tbl.item(r, c) else "0"
            return int(float(t or 0))
        except Exception:
            return 0

    def _float_cell(self, tbl: QTableWidget, r: int, c: int) -> float:
        try:
            t = tbl.item(r, c).text().strip() if tbl.item(r, c) else "0"
            return float(t or 0.0)
        except Exception:
            return 0.0

    def _section_totals(self, section: str) -> Dict[str, Any]:
        tbl = self.tables[section]
        qty_total = 0
        pins_total = 0

        bga_qty = self._int_cell(tbl, 0, 1)
        pitch = self._float_cell(tbl, 0, 4)
        critical_qty = self._int_cell(tbl, 3, 1)
        connectors_qty = self._int_cell(tbl, 4, 1)

        for r in range(5):
            qty = self._int_cell(tbl, r, 1)
            pin = self._int_cell(tbl, r, 2)
            pt = max(0, qty) * max(0, pin)
            qty_total += max(0, qty)
            pins_total += max(0, pt)

        return {
            "qty_total": qty_total,
            "pins_total": pins_total,
            "bga_qty": bga_qty,
            "pitch_bga_mm": pitch,
            "critical_qty": critical_qty,
            "connectors_qty": connectors_qty,
        }

    def _rules_for_section(self, section: str) -> SectionComplexityRules:
        c = self._coeffs_provider()
        if section == "Segnale":
            return c.rules_signal
        if section == "Power":
            return c.rules_power
        if section == "RF":
            return c.rules_rf
        return c.rules_highspeed

    def _recalc_section(self, section: str):
        if self._updating:
            return
        self._updating = True
        try:
            tbl = self.tables[section]
            for r in range(5):
                qty = self._int_cell(tbl, r, 1)
                pin = self._int_cell(tbl, r, 2)
                pt = max(0, qty) * max(0, pin)
                it = tbl.item(r, 3)
                if it is None:
                    it = _ro_item(str(int(pt)))
                    tbl.setItem(r, 3, it)
                it.setText(str(int(pt)))

            tot = self._section_totals(section)
            rules = self._rules_for_section(section)
            score = section_complexity_score(
                qty_total=tot["qty_total"],
                pins_total=tot["pins_total"],
                bga_qty=tot["bga_qty"],
                pitch_bga_mm=tot["pitch_bga_mm"],
                critical_qty=tot["critical_qty"],
                connectors_qty=tot["connectors_qty"],
                rules=rules,
            )
            cplx = section_complexity_class(score, rules)

            sum_r = 5
            tbl.item(sum_r, 1).setText(str(int(tot["qty_total"])))
            tbl.item(sum_r, 3).setText(str(int(tot["pins_total"])))
            tbl.item(sum_r, 4).setText(f'{float(tot["pitch_bga_mm"]):.2f}')
            tbl.item(sum_r, 5).setText(f"Complessità: {cplx}  (score {score:.1f})")

            _autosize_table(tbl, max_visible_rows=9)
        finally:
            self._updating = False

    def section_complexity(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for sec in self.sections:
            tot = self._section_totals(sec)
            rules = self._rules_for_section(sec)
            score = section_complexity_score(
                qty_total=tot["qty_total"],
                pins_total=tot["pins_total"],
                bga_qty=tot["bga_qty"],
                pitch_bga_mm=tot["pitch_bga_mm"],
                critical_qty=tot["critical_qty"],
                connectors_qty=tot["connectors_qty"],
                rules=rules,
            )
            out[sec] = section_complexity_class(score, rules)
        return out

    def get_signal_legacy(self) -> dict[str, float]:
        tbl = self.tables["Segnale"]
        bga_qty = self._int_cell(tbl, 0, 1)
        bga_pin = self._int_cell(tbl, 0, 2)
        pitch = self._float_cell(tbl, 0, 4)
        return {
            "bga_count": float(bga_qty),
            "bga_pins_total": float(max(0, bga_qty) * max(0, bga_pin)),
            "pitch_mm": float(pitch),
            "passives": float(self._int_cell(tbl, 1, 1)),
            "actives": float(self._int_cell(tbl, 2, 1)),
            "critical": float(self._int_cell(tbl, 3, 1)),
            "connectors": float(self._int_cell(tbl, 4, 1)),
        }

    def ui_to_dict(self) -> Dict[str, Any]:
        sections: Dict[str, Any] = {}
        for sec in self.sections:
            tbl = self.tables[sec]
            rows: List[Dict[str, Any]] = []
            for r, cat in enumerate(self.categories):
                rows.append({
                    "categoria": cat,
                    "qty": self._int_cell(tbl, r, 1),
                    "pin": self._int_cell(tbl, r, 2),
                    "pitch": self._float_cell(tbl, r, 4) if cat == "BGA" else 0.0,
                    "note": (tbl.item(r, 5).text() if tbl.item(r, 5) else ""),
                })
            sections[sec] = {"rows": rows}
        return {"sections": sections}

    def ui_from_dict(self, d: Dict[str, Any]) -> None:
        if not isinstance(d, dict):
            return
        sec_d = d.get("sections", {})
        if not isinstance(sec_d, dict):
            return
        for sec in self.sections:
            sd = sec_d.get(sec, {})
            if not isinstance(sd, dict):
                continue
            rows = sd.get("rows", [])
            if not isinstance(rows, list):
                continue
            tbl = self.tables[sec]
            for r, row in enumerate(rows):
                if r >= 5 or not isinstance(row, dict):
                    continue
                tbl.item(r, 1).setText(str(int(row.get("qty", 0) or 0)))
                tbl.item(r, 2).setText(str(int(row.get("pin", 0) or 0)))
                if r == 0:
                    tbl.item(r, 4).setText(f"{float(row.get('pitch', 0.8) or 0.8):.2f}")
                tbl.item(r, 5).setText(str(row.get("note", "")))
            self._recalc_section(sec)


# =========================
# TAB: Segnali
# =========================
class SignalsTab(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("Aggiungi")
        self.del_btn = QPushButton("Rimuovi")
        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.del_btn)
        btn_row.addStretch()
        outer.addLayout(btn_row)

        grid = QGridLayout()
        grid.setSpacing(12)
        outer.addLayout(grid)

        left_box = QGroupBox("Interfacce (Routing Critico)")
        left_layout = QVBoxLayout(left_box)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "Nome",
            "Data Rate (Gbps)",
            "Differential Pair",
            "Single Ended",
            "Match Group (ps)",
            "Ore stimate",
        ])
        _configure_table(self.table, editable=True, stretch_last=True, selection_rows=True, header_h=38, row_h=34)
        self.table.setMinimumHeight(520)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        left_layout.addWidget(self.table)
        grid.addWidget(left_box, 0, 0)

        right_box = QGroupBox("Ore per interfaccia")
        right_layout = QVBoxLayout(right_box)
        self.fig = Figure(figsize=(5, 4))
        self.canvas = FigureCanvas(self.fig)
        right_layout.addWidget(self.canvas)
        grid.addWidget(right_box, 0, 1)

        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 1)

        self.add_btn.clicked.connect(lambda: self.add_row(("Interface", 10.0, 0, 0, 50.0)))
        self.del_btn.clicked.connect(self.del_row)
        self.table.itemChanged.connect(self._on_item_changed)

        self.add_row(("JESD204", 10.0, 32, 0, 10.0))
        self._render_chart()

    def _row_values(self, r: int):
        def cell(c: int) -> str:
            return self.table.item(r, c).text().strip() if self.table.item(r, c) else ""
        name = cell(0) or f"IF{r+1}"
        gbps = float(cell(1) or 0.0)
        dp = int(float(cell(2) or 0))
        se = int(float(cell(3) or 0))
        ps = float(cell(4) or 50.0)
        return name, gbps, dp, se, ps

    def add_row(self, defaults=("Interface", 10.0, 0, 0, 10.0)):
        r = self.table.rowCount()
        self.table.insertRow(r)
        name, gbps, dp, se, ps = defaults
        self.table.setItem(r, 0, _text_item(str(name)))
        self.table.setItem(r, 1, _num_item(f"{float(gbps):.2f}"))
        self.table.setItem(r, 2, _num_item(str(int(dp))))
        self.table.setItem(r, 3, _num_item(str(int(se))))
        self.table.setItem(r, 4, _num_item(f"{float(ps):.2f}"))
        self.table.setItem(r, 5, _ro_item("0.0"))
        self._render_chart()

    def del_row(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)
            self._render_chart()

    def _on_item_changed(self, item: QTableWidgetItem):
        if item is None or item.column() == 5:
            return
        self._render_chart()

    def collect_interfaces(self):
        itfs = []
        for r in range(self.table.rowCount()):
            try:
                name, gbps, dp, se, ps = self._row_values(r)
            except Exception:
                continue
            itfs.append(HighSpeedInterface(name=name, data_rate_gbps=gbps, diff_pairs=dp, se_lines=se, match_ps=ps))
        return itfs

    def update_from_results(self, res: dict):
        hs = res.get("routing_critico", {}).get("interfaces", [])
        for r, it in enumerate(hs):
            if r >= self.table.rowCount():
                break
            hrs = float(it.get("hours_total", 0.0))
            cell = self.table.item(r, 5)
            if cell is None:
                cell = _ro_item("0.0")
                self.table.setItem(r, 5, cell)
            cell.setText(f"{hrs:.1f}")
        self._render_chart(from_results=hs)

    def _render_chart(self, from_results: list[dict] | None = None):
        labels: list[str] = []
        values: list[float] = []

        if from_results is not None:
            for it in from_results:
                labels.append(str(it.get("name", "")))
                values.append(max(0.0, float(it.get("hours_total", 0.0))))
        else:
            for r in range(self.table.rowCount()):
                name = self.table.item(r, 0).text().strip() if self.table.item(r, 0) else f"IF{r+1}"
                try:
                    hrs = float((self.table.item(r, 5).text().strip() if self.table.item(r, 5) else "0") or 0.0)
                except Exception:
                    hrs = 0.0
                labels.append(name)
                values.append(max(0.0, hrs))

        fig = self.fig
        fig.clear()
        ax = fig.add_subplot(111)

        if sum(values) <= 0 or not values:
            ax.text(0.5, 0.5, "Nessuna ora calcolata", ha="center", va="center")
            ax.set_title("Ore per interfaccia")
            fig.tight_layout()
            self.canvas.draw()
            return

        pairs = sorted(zip(labels, values), key=lambda x: x[1], reverse=True)
        labels_s = [p[0] for p in pairs]
        values_s = [p[1] for p in pairs]

        ax.barh(labels_s, values_s)
        ax.invert_yaxis()
        ax.set_xlabel("Ore")
        ax.set_title("Ore per interfaccia")
        fig.tight_layout()
        self.canvas.draw()

    def ui_to_dict(self) -> Dict[str, Any]:
        itfs: List[Dict[str, Any]] = []
        for r in range(self.table.rowCount()):
            name, gbps, dp, se, ps = self._row_values(r)
            itfs.append({"name": name, "data_rate_gbps": gbps, "diff_pairs": dp, "se_lines": se, "match_ps": ps})
        return {"interfaces": itfs}

    def ui_from_dict(self, d: Dict[str, Any]) -> None:
        if not isinstance(d, dict):
            return
        itfs = d.get("interfaces", [])
        if not isinstance(itfs, list):
            return
        self.table.setRowCount(0)
        for it in itfs:
            if not isinstance(it, dict):
                continue
            self.add_row((
                str(it.get("name", "IF")),
                float(it.get("data_rate_gbps", 0.0)),
                int(it.get("diff_pairs", 0)),
                int(it.get("se_lines", 0)),
                float(it.get("match_ps", 50.0)),
            ))


# =========================
# TAB: Stack-up
# =========================
class StackupTab(QWidget):
    def __init__(self, mech: MechTab, comps: ComponentsTab, sigs: SignalsTab):
        super().__init__()
        from pcb_quote.stackup.materials import load_catalog

        self._catalog = load_catalog()
        self._mech = mech

        self._building = False
        self._mirroring = False

        root = QHBoxLayout(self)
        root.setSpacing(12)

        left = QVBoxLayout()
        root.addLayout(left, 4)

        self.stack_table = QTableWidget(0, 9)
        self.stack_table.setHorizontalHeaderLabels([
            "Voce",
            "RowType",
            "Tipo layer",
            "Rame",
            "Tipo dielettrico",
            "Materiale",
            "Style",
            "Plies",
            "Spessore (mm)",
        ])
        _configure_table(self.stack_table, editable=True, stretch_last=True, selection_rows=True, header_h=38, row_h=38)
        left.addWidget(self.stack_table, 2)

        self.stack_table.setColumnWidth(0, 120)
        self.stack_table.setColumnWidth(1, 95)
        self.stack_table.setColumnWidth(2, 120)
        self.stack_table.setColumnWidth(3, 130)
        self.stack_table.setColumnWidth(4, 160)
        self.stack_table.setColumnWidth(5, 240)
        self.stack_table.setColumnWidth(6, 180)
        self.stack_table.setColumnWidth(7, 90)
        self.stack_table.setColumnWidth(8, 120)

        right_box = QGroupBox("Selezione stack-up")
        right = QFormLayout(right_box)
        right.setLabelAlignment(Qt.AlignRight)
        right.setFormAlignment(Qt.AlignTop)
        root.addWidget(right_box, 1)

        self.keep_sym = QCheckBox("Mantieni simmetria dielettrici")
        self.keep_sym.setChecked(True)

        self.pcb_type = QComboBox()
        self.pcb_type.addItems(["Rigid", "Rigid-Flex", "RF"])

        self.layers = QSpinBox()
        self.layers.setRange(2, 20)
        self.layers.setValue(12)

        self.tech = QComboBox()
        self.tech.addItems([
            "Standard (PTH only)",
            "Advanced (Mechanical blind/buried)",
            "HDI (IPC-2226 microvia)",
        ])

        self.outer_material = QComboBox()
        self.inner_material = QComboBox()

        self.copper_outer = QComboBox()
        self.copper_inner = QComboBox()
        for cb in (self.copper_outer, self.copper_inner):
            cb.addItems(["0.5 oz (18µm)", "1 oz (35µm)", "2 oz (70µm)"])
        self.copper_outer.setCurrentIndex(1)
        self.copper_inner.setCurrentIndex(1)

        self._reload_materials()

        self.total_thickness_view = QLabel("")
        self.total_thickness_view.setWordWrap(True)
        self.warn_thickness = QLabel("")
        self.warn_thickness.setWordWrap(True)
        self.warn_thickness.setStyleSheet("color:#c0392b; font-weight:600;")

        right.addRow("", self.keep_sym)
        right.addRow("PCB type", self.pcb_type)
        right.addRow("Layers", self.layers)
        right.addRow("Tecnologia", self.tech)
        right.addRow("Rame esterni", self.copper_outer)
        right.addRow("Rame interni", self.copper_inner)
        right.addRow("Materiale (Top/Bottom)", self.outer_material)
        right.addRow("Materiale (Inner)", self.inner_material)
        right.addRow("Spessore totale", self.total_thickness_view)
        right.addRow("", self.warn_thickness)

        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.setInterval(250)
        self._auto_timer.timeout.connect(self._auto_recompute_stack)

        self.keep_sym.stateChanged.connect(lambda *_: self._schedule_auto())

        self._mech.t_mm.valueChanged.connect(lambda *_: self._schedule_auto())
        self.layers.valueChanged.connect(lambda *_: self._schedule_auto())
        for cb in (self.tech, self.copper_outer, self.copper_inner, self.outer_material, self.inner_material, self.pcb_type):
            cb.currentIndexChanged.connect(lambda *_: self._schedule_auto())

        self._auto_recompute_stack()

    def _schedule_auto(self):
        self._auto_timer.start()

    def _reload_materials(self):
        pt = self.pcb_type.currentText().strip()
        mats = [m.name for m in self._catalog if pt in m.pcb_types]
        if not mats:
            mats = [m.name for m in self._catalog]

        def refill(cb: QComboBox, prefer: str):
            cb.blockSignals(True)
            cur = cb.currentText()
            cb.clear()
            cb.addItems(mats)
            if cur and cb.findText(cur) >= 0:
                cb.setCurrentText(cur)
            elif cb.findText(prefer) >= 0:
                cb.setCurrentText(prefer)
            cb.blockSignals(False)

        refill(self.outer_material, "FR-4 (generic)")
        refill(self.inner_material, "FR-4 (generic)")

    def _copper_t_mm_from_text(self, txt: str) -> float:
        if "0.5" in txt:
            return 0.018
        if "2 oz" in txt:
            return 0.070
        return 0.035

    def _copper_label_for_layer(self, layer_index_1based: int, n_layers: int) -> str:
        if layer_index_1based == 1 or layer_index_1based == n_layers:
            return self.copper_outer.currentText()
        return self.copper_inner.currentText()

    def _copper_t_for_layer(self, layer_index_1based: int, n_layers: int) -> float:
        return self._copper_t_mm_from_text(self._copper_label_for_layer(layer_index_1based, n_layers))

    def _get_mat(self, name: str):
        for m in self._catalog:
            if m.name == name:
                return m
        return None

    def _prepreg_styles(self, mat) -> list[tuple[str, float]]:
        if mat and mat.prepreg_styles:
            return [(pp.style, float(pp.thickness_mm)) for pp in mat.prepreg_styles]
        return [("1080", 0.10), ("2116", 0.18), ("7628", 0.25)]

    def _core_styles(self, mat) -> list[tuple[str, float]]:
        if mat and mat.core_options_mm:
            return [(f"Core {x:.2f}", float(x)) for x in mat.core_options_mm]
        return [("Core 0.20", 0.20), ("Core 0.30", 0.30), ("Core 0.50", 0.50), ("Core 0.80", 0.80)]

    def _layer_label(self, idx_1based: int, layers: int) -> str:
        if idx_1based == 1:
            return "Top"
        if idx_1based == layers:
            return "Bottom"
        return f"Inner{idx_1based-1}"

    def _default_layer_type(self, i: int, n: int) -> str:
        if i == 1 or i == n:
            return "Signal"
        if i == 2 or i == n - 1:
            return "GND"
        if i % 4 == 0:
            return "PWR"
        if i % 4 == 2:
            return "GND"
        return "Signal"

    def _dielectric_thickness(self, mat, kind: str, style: str, plies: int) -> float:
        if kind == "Prepreg":
            mp = dict(self._prepreg_styles(mat))
            t_per = float(mp.get(style, 0.18))
            return float(max(0.01, t_per * max(1, int(plies))))
        mc = dict(self._core_styles(mat))
        return float(max(0.01, mc.get(style, 0.20)))

    def _mirror_row(self, row: int) -> int:
        n = self.stack_table.rowCount()
        return n - 1 - row

    def _auto_recompute_stack(self):
        if self._building:
            return
        self._build_stack()

    def _plies_value(self, cb: QComboBox) -> int:
        try:
            t = str(cb.currentText()).strip().lower().replace("x", "")
            v = int(float(t))
            return max(1, v)
        except Exception:
            return 1

    def _build_stack(self):
        n = int(self.layers.value())
        if n % 2 == 1:
            n += 1
            self.layers.setValue(n)

        self._building = True
        try:
            mats = [m.name for m in self._catalog if self.pcb_type.currentText().strip() in m.pcb_types] or [m.name for m in self._catalog]
            outer_mat = self._get_mat(self.outer_material.currentText().strip())
            inner_mat = self._get_mat(self.inner_material.currentText().strip())

            pp_outer = self._prepreg_styles(outer_mat)[0][0]
            pp_inner = self._prepreg_styles(inner_mat)[0][0]
            core_inner = self._core_styles(inner_mat)[0][0]

            self.stack_table.blockSignals(True)
            self.stack_table.setRowCount(0)

            for i in range(1, n + 1):
                r = self.stack_table.rowCount()
                self.stack_table.insertRow(r)
                self.stack_table.setItem(r, 0, _ro_item(self._layer_label(i, n)))
                self.stack_table.setItem(r, 1, _ro_item("Copper"))

                cb_layer_type = QComboBox()
                cb_layer_type.addItems(["Signal", "GND", "PWR", "Mixed"])
                cb_layer_type.setCurrentText(self._default_layer_type(i, n))
                self.stack_table.setCellWidget(r, 2, cb_layer_type)
                cb_layer_type.currentTextChanged.connect(lambda _=None, row=r: self._on_user_change(row, "layer_type"))

                copper_label = self._copper_label_for_layer(i, n)
                self.stack_table.setItem(r, 3, _ro_item(copper_label))
                self.stack_table.setItem(r, 4, _ro_item(""))
                self.stack_table.setItem(r, 5, _ro_item(""))
                self.stack_table.setItem(r, 6, _ro_item(""))
                self.stack_table.setItem(r, 7, _ro_item(""))
                self.stack_table.setItem(r, 8, _ro_item(f"{self._copper_t_for_layer(i, n):.3f}"))

                if i < n:
                    rr = self.stack_table.rowCount()
                    self.stack_table.insertRow(rr)
                    self.stack_table.setItem(rr, 0, _ro_item("Dielettrico"))
                    self.stack_table.setItem(rr, 1, _ro_item("Dielectric"))
                    self.stack_table.setItem(rr, 2, _ro_item(""))
                    self.stack_table.setItem(rr, 3, _ro_item(""))

                    cb_kind = QComboBox()
                    cb_kind.addItems(["Prepreg", "Core"])
                    cb_kind.setCurrentText("Core" if i == n // 2 else "Prepreg")
                    self.stack_table.setCellWidget(rr, 4, cb_kind)

                    cb_mat = QComboBox()
                    cb_mat.addItems(mats)
                    is_outer_zone = (i == 1) or (i == n - 1)
                    cb_mat.setCurrentText(self.outer_material.currentText().strip() if is_outer_zone else self.inner_material.currentText().strip())
                    self.stack_table.setCellWidget(rr, 5, cb_mat)

                    cb_style = QComboBox()
                    self.stack_table.setCellWidget(rr, 6, cb_style)

                    cb_plies = QComboBox()
                    cb_plies.addItems([f"x{p}" for p in range(1, 9)])
                    cb_plies.setCurrentText("x2")
                    cb_plies.setProperty("last_prepreg_plies", 2)
                    self.stack_table.setCellWidget(rr, 7, cb_plies)

                    self.stack_table.setItem(rr, 8, _ro_item("0.00"))

                    cb_kind.currentTextChanged.connect(lambda _=None, row=rr: self._on_user_change(row, "kind"))
                    cb_mat.currentTextChanged.connect(lambda _=None, row=rr: self._on_user_change(row, "material"))
                    cb_style.currentTextChanged.connect(lambda _=None, row=rr: self._on_user_change(row, "style"))
                    cb_plies.currentTextChanged.connect(lambda _=None, row=rr: self._on_user_change(row, "plies"))

                    self._refresh_dielectric_row(rr, pref_prepreg=(pp_outer if is_outer_zone else pp_inner), pref_core=core_inner)

            self.stack_table.blockSignals(False)

            self._update_thickness_views()
            _autosize_table(self.stack_table, max_visible_rows=16)
        finally:
            self._building = False

    def _refresh_dielectric_row(self, row: int, *, pref_prepreg: str | None = None, pref_core: str | None = None):
        kind = self.stack_table.cellWidget(row, 4)
        mat_cb = self.stack_table.cellWidget(row, 5)
        style = self.stack_table.cellWidget(row, 6)
        plies_cb = self.stack_table.cellWidget(row, 7)
        if not isinstance(kind, QComboBox) or not isinstance(mat_cb, QComboBox) or not isinstance(style, QComboBox) or not isinstance(plies_cb, QComboBox):
            return

        mat = self._get_mat(mat_cb.currentText().strip())
        is_prepreg = (kind.currentText() == "Prepreg")

        # refresh style list
        style.blockSignals(True)
        cur_style = style.currentText()
        style.clear()
        if is_prepreg:
            style.addItems([s for s, _t in self._prepreg_styles(mat)])
            if cur_style and style.findText(cur_style) >= 0:
                style.setCurrentText(cur_style)
            elif pref_prepreg and style.findText(pref_prepreg) >= 0:
                style.setCurrentText(pref_prepreg)
            else:
                style.setCurrentIndex(0)
        else:
            style.addItems([s for s, _t in self._core_styles(mat)])
            if cur_style and style.findText(cur_style) >= 0:
                style.setCurrentText(cur_style)
            elif pref_core and style.findText(pref_core) >= 0:
                style.setCurrentText(pref_core)
            else:
                style.setCurrentIndex(0)
        style.blockSignals(False)

        # plies enable/disable (do NOT force x2)
        if is_prepreg:
            plies_cb.setEnabled(True)
            # do not touch currentText unless invalid
            if self._plies_value(plies_cb) < 1:
                last = plies_cb.property("last_prepreg_plies")
                try:
                    last_i = int(last) if last is not None else 1
                except Exception:
                    last_i = 1
                plies_cb.setCurrentText(f"x{max(1, last_i)}")
        else:
            # remember last prepreg value (do not overwrite on each refresh)
            try:
                if plies_cb.isEnabled():
                    plies_cb.setProperty("last_prepreg_plies", self._plies_value(plies_cb))
            except Exception:
                pass
            plies_cb.setEnabled(False)
            plies_cb.setCurrentText("x1")

        nplies = self._plies_value(plies_cb) if is_prepreg else 1
        th = self._dielectric_thickness(mat, kind.currentText(), style.currentText(), nplies)

        it = self.stack_table.item(row, 8)
        if it is None:
            it = _ro_item(f"{th:.2f}")
            self.stack_table.setItem(row, 8, it)
        it.setText(f"{th:.2f}")

    def _on_user_change(self, row: int, what: str):
        if self._building or self._mirroring:
            return

        rtype = self.stack_table.item(row, 1).text() if self.stack_table.item(row, 1) else ""

        # If user changed plies in prepreg, store last_prepreg_plies immediately
        if rtype == "Dielectric" and what == "plies":
            plies_cb = self.stack_table.cellWidget(row, 7)
            kind = self.stack_table.cellWidget(row, 4)
            if isinstance(plies_cb, QComboBox) and isinstance(kind, QComboBox) and kind.currentText() == "Prepreg":
                plies_cb.setProperty("last_prepreg_plies", self._plies_value(plies_cb))

        if rtype == "Dielectric":
            self._refresh_dielectric_row(row)

        # mirror ONLY dielectric rows if enabled
        if not bool(self.keep_sym.isChecked()):
            self._update_thickness_views()
            return

        mrow = self._mirror_row(row)
        if mrow == row or mrow < 0 or mrow >= self.stack_table.rowCount():
            self._update_thickness_views()
            return

        self._mirroring = True
        try:
            mrtype = self.stack_table.item(mrow, 1).text() if self.stack_table.item(mrow, 1) else ""
            if rtype != mrtype or rtype != "Dielectric":
                return

            src_kind = self.stack_table.cellWidget(row, 4)
            src_mat = self.stack_table.cellWidget(row, 5)
            src_style = self.stack_table.cellWidget(row, 6)
            src_plies = self.stack_table.cellWidget(row, 7)

            dst_kind = self.stack_table.cellWidget(mrow, 4)
            dst_mat = self.stack_table.cellWidget(mrow, 5)
            dst_style = self.stack_table.cellWidget(mrow, 6)
            dst_plies = self.stack_table.cellWidget(mrow, 7)

            if isinstance(src_kind, QComboBox) and isinstance(dst_kind, QComboBox):
                v = src_kind.currentText()
                if dst_kind.findText(v) >= 0:
                    dst_kind.setCurrentText(v)
            if isinstance(src_mat, QComboBox) and isinstance(dst_mat, QComboBox):
                v = src_mat.currentText()
                if dst_mat.findText(v) >= 0:
                    dst_mat.setCurrentText(v)

            self._refresh_dielectric_row(mrow)

            if isinstance(src_style, QComboBox) and isinstance(dst_style, QComboBox):
                s = src_style.currentText()
                if s and dst_style.findText(s) >= 0:
                    dst_style.setCurrentText(s)

            if isinstance(src_plies, QComboBox) and isinstance(dst_plies, QComboBox):
                dst_plies.setCurrentText(src_plies.currentText())
                dst_plies.setProperty("last_prepreg_plies", src_plies.property("last_prepreg_plies"))

            self._refresh_dielectric_row(mrow)
        finally:
            self._mirroring = False
            self._update_thickness_views()

    def _compute_total_thickness(self) -> float:
        total = 0.0
        for r in range(self.stack_table.rowCount()):
            try:
                total += float(self.stack_table.item(r, 8).text())
            except Exception:
                pass
        return float(total)

    def _update_thickness_views(self):
        target = float(self._mech.t_mm.value())
        real_t = self._compute_total_thickness()
        if target <= 0:
            target = 1.6
        delta_pct = (real_t - target) / target * 100.0
        self.total_thickness_view.setText(f"{real_t:.3f} mm   (Δ {delta_pct:+.1f}%)")
        self.warn_thickness.setText("" if abs(delta_pct) <= 2.0 else "ALERT: spessore stack-up fuori specifica ±2%.")

    def ui_to_dict(self) -> Dict[str, Any]:
        settings = {
            "pcb_type": self.pcb_type.currentText(),
            "layers": int(self.layers.value()),
            "tech": self.tech.currentText(),
            "copper_outer": self.copper_outer.currentText(),
            "copper_inner": self.copper_inner.currentText(),
            "outer_material": self.outer_material.currentText(),
            "inner_material": self.inner_material.currentText(),
            "keep_sym_dielectric": bool(self.keep_sym.isChecked()),
        }
        rows: List[Dict[str, Any]] = []
        for r in range(self.stack_table.rowCount()):
            rt = self.stack_table.item(r, 1).text() if self.stack_table.item(r, 1) else ""
            voce = self.stack_table.item(r, 0).text() if self.stack_table.item(r, 0) else ""
            thickness = float(self.stack_table.item(r, 8).text()) if self.stack_table.item(r, 8) else 0.0
            if rt == "Copper":
                lt = self.stack_table.cellWidget(r, 2)
                rows.append({
                    "row_type": "Copper",
                    "voce": voce,
                    "layer_type": (lt.currentText() if isinstance(lt, QComboBox) else "Signal"),
                    "copper": (self.stack_table.item(r, 3).text() if self.stack_table.item(r, 3) else ""),
                    "thickness_mm": thickness,
                })
            else:
                kind = self.stack_table.cellWidget(r, 4)
                mat = self.stack_table.cellWidget(r, 5)
                style = self.stack_table.cellWidget(r, 6)
                plies = self.stack_table.cellWidget(r, 7)
                rows.append({
                    "row_type": "Dielectric",
                    "voce": voce,
                    "kind": (kind.currentText() if isinstance(kind, QComboBox) else "Prepreg"),
                    "material": (mat.currentText() if isinstance(mat, QComboBox) else ""),
                    "style": (style.currentText() if isinstance(style, QComboBox) else ""),
                    "plies": (plies.currentText() if isinstance(plies, QComboBox) else "x1"),
                    "thickness_mm": thickness,
                })
        return {"settings": settings, "rows": rows}

    def ui_from_dict(self, d: Dict[str, Any]) -> None:
        if not isinstance(d, dict):
            return
        s = d.get("settings", {})
        if isinstance(s, dict):
            if self.pcb_type.findText(str(s.get("pcb_type", ""))) >= 0:
                self.pcb_type.setCurrentText(str(s.get("pcb_type")))
            try:
                self.layers.setValue(int(s.get("layers", 12)))
            except Exception:
                pass
            if self.tech.findText(str(s.get("tech", ""))) >= 0:
                self.tech.setCurrentText(str(s.get("tech")))
            if self.copper_outer.findText(str(s.get("copper_outer", ""))) >= 0:
                self.copper_outer.setCurrentText(str(s.get("copper_outer")))
            if self.copper_inner.findText(str(s.get("copper_inner", ""))) >= 0:
                self.copper_inner.setCurrentText(str(s.get("copper_inner")))
            self._reload_materials()
            if self.outer_material.findText(str(s.get("outer_material", ""))) >= 0:
                self.outer_material.setCurrentText(str(s.get("outer_material")))
            if self.inner_material.findText(str(s.get("inner_material", ""))) >= 0:
                self.inner_material.setCurrentText(str(s.get("inner_material")))
            self.keep_sym.setChecked(bool(s.get("keep_sym_dielectric", True)))

        self._build_stack()

        rows = d.get("rows", [])
        if not isinstance(rows, list):
            return

        for r, rr in enumerate(rows):
            if r >= self.stack_table.rowCount() or not isinstance(rr, dict):
                break
            rt = rr.get("row_type", "")
            if rt == "Copper":
                lt = self.stack_table.cellWidget(r, 2)
                if isinstance(lt, QComboBox):
                    v = str(rr.get("layer_type", "Signal"))
                    if lt.findText(v) >= 0:
                        lt.setCurrentText(v)
            else:
                kind = self.stack_table.cellWidget(r, 4)
                mat = self.stack_table.cellWidget(r, 5)
                style = self.stack_table.cellWidget(r, 6)
                plies = self.stack_table.cellWidget(r, 7)
                if isinstance(kind, QComboBox):
                    v = str(rr.get("kind", "Prepreg"))
                    if kind.findText(v) >= 0:
                        kind.setCurrentText(v)
                if isinstance(mat, QComboBox):
                    v = str(rr.get("material", ""))
                    if v and mat.findText(v) >= 0:
                        mat.setCurrentText(v)

                self._refresh_dielectric_row(r)

                if isinstance(style, QComboBox):
                    v = str(rr.get("style", ""))
                    if v and style.findText(v) >= 0:
                        style.setCurrentText(v)

                if isinstance(plies, QComboBox):
                    v = str(rr.get("plies", "x1"))
                    if plies.findText(v) >= 0:
                        plies.setCurrentText(v)

                # store last_prepreg_plies if prepreg
                if isinstance(kind, QComboBox) and isinstance(plies, QComboBox) and kind.currentText() == "Prepreg":
                    plies.setProperty("last_prepreg_plies", self._plies_value(plies))

                self._refresh_dielectric_row(r)

        self._update_thickness_views()


# =========================
# TAB: Risultati
# =========================
class ResultsTab(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        grid = QGridLayout()
        grid.setSpacing(12)
        outer.addLayout(grid)

        left_col = QVBoxLayout()

        self.params_table = QTableWidget(4, 2)
        self.params_table.setHorizontalHeaderLabels(["Parametro", "Valore"])
        self.params_table.verticalHeader().setVisible(False)
        _configure_table(self.params_table, editable=False, header_h=44, row_h=44, stretch_last=True, selection_rows=False)
        self.params_table.setColumnWidth(0, 260)

        self.tar_layout = QDoubleSpinBox(); self.tar_layout.setRange(1, 2000); self.tar_layout.setValue(75); self.tar_layout.setSuffix(" €/h")
        self.tar_si = QDoubleSpinBox(); self.tar_si.setRange(1, 2000); self.tar_si.setValue(90); self.tar_si.setSuffix(" €/h")
        self.buffer = QDoubleSpinBox(); self.buffer.setDecimals(2); self.buffer.setRange(0, 2.0); self.buffer.setValue(0.25)
        self.week_hours = QDoubleSpinBox(); self.week_hours.setRange(1, 80); self.week_hours.setValue(40); self.week_hours.setSuffix(" h")

        self._set_param_row(0, "Tariffa Layout", self.tar_layout)
        self._set_param_row(1, "Tariffa SI/PI", self.tar_si)
        self._set_param_row(2, "Buffer (0.25 = 25%)", self.buffer)
        self._set_param_row(3, "Ore per settimana", self.week_hours)

        params_box = QGroupBox("Parametri")
        params_l = QVBoxLayout(params_box)
        params_l.addWidget(self.params_table)
        left_col.addWidget(params_box)

        self.totals_table = QTableWidget(0, 5)
        self.totals_table.setHorizontalHeaderLabels(["Attività", "Ore", "Settimane", "Tariffa €/h", "Costo €"])
        _configure_table(self.totals_table, editable=False, header_h=40, row_h=34)

        totals_box = QGroupBox("Riepilogo Totali")
        totals_l = QVBoxLayout(totals_box)
        totals_l.addWidget(self.totals_table)
        totals_l.addWidget(_note_label("Nota: 'Constraint' = vincoli/EDA rules/stack-up. 'Fattibilità' = studio preliminare (sezioni + segnali + stack-up)."))
        left_col.addWidget(totals_box, 1)

        left_widget = QWidget()
        left_widget.setLayout(left_col)
        grid.addWidget(left_widget, 0, 0, 2, 1)

        self.pie_hours_fig = Figure(figsize=(5, 4)); self.pie_hours_canvas = FigureCanvas(self.pie_hours_fig)
        self.pie_cost_fig = Figure(figsize=(5, 4)); self.pie_cost_canvas = FigureCanvas(self.pie_cost_fig)

        grid.addWidget(self.pie_hours_canvas, 0, 1)
        grid.addWidget(self.pie_cost_canvas, 1, 1)

        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 2)

        _autosize_table(self.params_table, max_visible_rows=4)

    def _set_param_row(self, r: int, label: str, widget: QWidget):
        self.params_table.setItem(r, 0, _ro_item(label))
        self.params_table.setCellWidget(r, 1, widget)

    def set_results(self, res: dict):
        bd = res.get("breakdown", {})
        hours = bd.get("hours_with_buffer", {})
        weeks = bd.get("weeks_with_buffer", {})
        costs = bd.get("costs_with_buffer", {})
        rates = bd.get("rates", {})

        totals_order = ["Fattibilità", "Constraint", "Piazzamento", "Routing Critico", "Routing Standard", "SI/PI", "Cleanup", "Documentazione"]

        self.totals_table.setRowCount(len(totals_order) + 1)
        for r, k in enumerate(totals_order):
            hrs = float(hours.get(k, 0.0) or 0.0)
            wks = float(weeks.get(k, 0.0) or 0.0)
            cost = float(costs.get(k, 0.0) or 0.0)
            rate_col = float(rates.get("si_pi")) if k == "SI/PI" else float(rates.get("layout", 0.0))
            self.totals_table.setItem(r, 0, _ro_item(k))
            self.totals_table.setItem(r, 1, _ro_item(f"{hrs:.1f}"))
            self.totals_table.setItem(r, 2, _ro_item(f"{wks:.2f}"))
            self.totals_table.setItem(r, 3, _ro_item(f"{rate_col:.0f}"))
            self.totals_table.setItem(r, 4, _ro_item(f"{cost:.0f}"))

        total_h = float(bd.get("totals", {}).get("hours", 0.0) or 0.0)
        total_w = float(bd.get("totals", {}).get("weeks", 0.0) or 0.0)
        total_c = float(bd.get("totals", {}).get("cost", 0.0) or 0.0)
        last = len(totals_order)

        item0 = _ro_item("TOTALE")
        item1 = _ro_item(f"{total_h:.1f}")
        item2 = _ro_item(f"{total_w:.2f}")
        item3 = _ro_item(f"{float(rates.get('layout', 0.0)):.0f}")
        item4 = _ro_item(f"{total_c:.0f}")

        bold_font = QFont(); bold_font.setBold(True)
        for it in (item0, item1, item2, item3, item4):
            it.setFont(bold_font)
            it.setForeground(QBrush(QColor("#c0392b")))

        self.totals_table.setItem(last, 0, item0)
        self.totals_table.setItem(last, 1, item1)
        self.totals_table.setItem(last, 2, item2)
        self.totals_table.setItem(last, 3, item3)
        self.totals_table.setItem(last, 4, item4)

        _autosize_table(self.totals_table, max_visible_rows=12)

        # pie hours
        labels = []
        sizes = []
        for k in totals_order:
            v = float(hours.get(k, 0.0) or 0.0)
            if v > 0:
                labels.append(k)
                sizes.append(v)

        fig = self.pie_hours_fig
        fig.clear()
        ax = fig.add_subplot(111)
        if sum(sizes) > 0:
            wedges, _, _ = ax.pie(sizes, labels=None, autopct="%1.1f%%", startangle=90)
            ax.legend(wedges, labels, loc="center left", bbox_to_anchor=(1.0, 0.5))
            ax.set_title("Distribuzione ore")
            ax.axis("equal")
        else:
            ax.text(0.5, 0.5, "Nessuna ora", ha="center", va="center")
            ax.set_title("Distribuzione ore")
        fig.tight_layout()
        self.pie_hours_canvas.draw()

        # pie costs
        labels_c = []
        sizes_c = []
        for k in totals_order:
            v = float(costs.get(k, 0.0) or 0.0)
            if v > 0:
                labels_c.append(k)
                sizes_c.append(v)

        fig2 = self.pie_cost_fig
        fig2.clear()
        ax2 = fig2.add_subplot(111)
        if sum(sizes_c) > 0:
            wedges2, _, _ = ax2.pie(sizes_c, labels=None, autopct="%1.1f%%", startangle=90)
            ax2.legend(wedges2, labels_c, loc="center left", bbox_to_anchor=(1.0, 0.5))
            ax2.set_title("Distribuzione costi")
            ax2.axis("equal")
        else:
            ax2.text(0.5, 0.5, "Nessun costo", ha="center", va="center")
            ax2.set_title("Distribuzione costi")
        fig2.tight_layout()
        self.pie_cost_canvas.draw()


# =========================
# QuoteForm + Save/Load
# =========================
class QuoteForm(QWidget):
    refreshRequested = Signal()
    saveRequested = Signal()
    loadRequested = Signal()
    editCoeffsRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.coeffs: QuoteCoeffs = DEFAULT_COEFFS

        vbox = QVBoxLayout(self)
        self.tabs = QTabWidget()

        self.mech = MechTab()
        self.components = ComponentsTab(coeffs_provider=lambda: self.coeffs)
        self.signals = SignalsTab()
        self.stackup = StackupTab(self.mech, self.components, self.signals)
        self.results = ResultsTab()

        self.tabs.addTab(self.mech, "Meccanica")
        self.tabs.addTab(self.components, "Componenti")
        self.tabs.addTab(self.signals, "Segnali")
        self.tabs.addTab(self.stackup, "Stack-up")
        self.tabs.addTab(self.results, "Risultati")
        vbox.addWidget(self.tabs)

        btn_row = QHBoxLayout()
        self.load_btn = QPushButton("Carica")
        self.coeffs_btn = QPushButton("Coefficienti…")
        self.coeffs_btn.setStyleSheet("background:#e74c3c; border:1px solid #c0392b;")
        self.save_btn = QPushButton("Salva")
        self.refresh_btn = QPushButton("Aggiorna")
        btn_row.addStretch()
        btn_row.addWidget(self.load_btn)
        btn_row.addWidget(self.coeffs_btn)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.refresh_btn)
        vbox.addLayout(btn_row)

        self.refresh_btn.clicked.connect(self.refreshRequested.emit)
        self.save_btn.clicked.connect(self.saveRequested.emit)
        self.load_btn.clicked.connect(self.loadRequested.emit)
        self.coeffs_btn.clicked.connect(self.editCoeffsRequested.emit)

        self._clear_sel_filter = _ClearSelectionFilter([
            self.mech.holes_table,
            self.mech.keep_table,
            self.mech.summary_table,
            self.signals.table,
            self.stackup.stack_table,
            self.results.params_table,
            self.results.totals_table,
        ])
        self.installEventFilter(self._clear_sel_filter)

        for w in (self.results.tar_layout, self.results.tar_si, self.results.buffer, self.results.week_hours):
            w.valueChanged.connect(lambda *_: self.recalc())

        QTimer.singleShot(50, self.refreshRequested.emit)

    def open_coeffs_dialog(self):
        dlg = CoeffsDialog(self.coeffs, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self.coeffs = dlg.get_coeffs()
            for sec in self.components.sections:
                self.components._recalc_section(sec)
            self.recalc()

    def ui_state_to_dict(self) -> Dict[str, Any]:
        return {
            "components": self.components.ui_to_dict(),
            "signals": self.signals.ui_to_dict(),
            "stackup": self.stackup.ui_to_dict(),
        }

    def load_ui_state(self, ui: Dict[str, Any]) -> None:
        if not isinstance(ui, dict):
            return
        self.components.ui_from_dict(ui.get("components", {}) if isinstance(ui.get("components", {}), dict) else {})
        self.signals.ui_from_dict(ui.get("signals", {}) if isinstance(ui.get("signals", {}), dict) else {})
        self.stackup.ui_from_dict(ui.get("stackup", {}) if isinstance(ui.get("stackup", {}), dict) else {})

    def load_inputs(
        self,
        inp: LayoutQuoteInputs,
        *,
        skip_components: bool = False,
        skip_signals: bool = False,
    ) -> None:
        # params (always ok)
        try:
            self.results.tar_layout.setValue(float(inp.tariffs.layout_eur_per_h))
            self.results.tar_si.setValue(float(inp.tariffs.si_pi_eur_per_h))
            self.results.buffer.setValue(float(inp.buffer_pct))
            self.results.week_hours.setValue(float(inp.week_hours))
        except Exception:
            pass

        # mech (always ok)
        try:
            self.mech.w_mm.setValue(float(inp.board.width_mm))
            self.mech.h_mm.setValue(float(inp.board.height_mm))
        except Exception:
            pass

        self.mech.holes_table.setRowCount(0)
        try:
            for h in getattr(inp.board, "holes", []) or []:
                hh = _parse_hole_entry(h) if not isinstance(h, HoleType) else h
                if hh:
                    self.mech.add_hole_row(hh.diameter_mm, hh.metallization_mm, hh.count)
        except Exception:
            pass

        self.mech.keep_table.setRowCount(0)
        try:
            for k in getattr(inp.board, "keepouts", []) or []:
                kk = _parse_keepout_entry(k) if not isinstance(k, KeepoutRect) else k
                if kk:
                    self.mech.add_keepout_row(kk.side, kk.width_mm, kk.height_mm, kk.count)
        except Exception:
            pass

        self.mech.update_area_summary()

        # legacy fill signal section only (only if not loading v2 ui)
        if not skip_components:
            try:
                c = inp.components
                sig = self.components.tables["Segnale"]
                sig.item(0, 1).setText(str(int(c.bga_count)))
                per_bga = int(c.bga_total_pins_effective // max(1, int(c.bga_count))) if int(c.bga_count) > 0 else int(c.bga_total_pins_effective)
                sig.item(0, 2).setText(str(int(per_bga)))
                sig.item(0, 4).setText(f"{float(c.min_bga_pitch_mm):.2f}")
                sig.item(1, 1).setText(str(int(c.passives)))
                sig.item(2, 1).setText(str(int(c.actives)))
                sig.item(3, 1).setText(str(int(c.critical)))
                sig.item(4, 1).setText(str(int(c.connectors)))
                self.components._recalc_section("Segnale")
            except Exception:
                pass

        if not skip_signals:
            self.signals.table.setRowCount(0)
            try:
                for it in getattr(inp.highspeed, "interfaces", []) or []:
                    parsed = _parse_hs_entry(it) if not isinstance(it, HighSpeedInterface) else it
                    if parsed:
                        self.signals.add_row((parsed.name, parsed.data_rate_gbps, parsed.diff_pairs, parsed.se_lines, parsed.match_ps))
            except Exception:
                pass

        self.recalc()

    def collect_inputs(self) -> LayoutQuoteInputs:
        tariffs = Tariffs(
            layout_eur_per_h=float(self.results.tar_layout.value()),
            si_pi_eur_per_h=float(self.results.tar_si.value()),
        )
        board = BoardConstraints(
            width_mm=float(self.mech.w_mm.value()),
            height_mm=float(self.mech.h_mm.value()),
            holes=self.mech.collect_holes(),
            keepouts=self.mech.collect_keepouts(),
        )

        sig = self.components.get_signal_legacy()

        comps = ComponentsInputs(
            bga_count=int(sig["bga_count"]),
            bga_total_pins_effective=int(sig["bga_pins_total"]),
            min_bga_pitch_mm=float(sig["pitch_mm"]),
            passives=int(sig["passives"]),
            actives=int(sig["actives"]),
            critical=int(sig["critical"]),
            connectors=int(sig["connectors"]),
            layers=int(self.stackup.layers.value()),
            hdi=("HDI" in self.stackup.tech.currentText()),
            tht=False,
        )

        hs = HighSpeedInputs(interfaces=self.signals.collect_interfaces())

        return LayoutQuoteInputs(
            board=board,
            components=comps,
            highspeed=hs,
            buffer_pct=float(self.results.buffer.value()),
            week_hours=float(self.results.week_hours.value()),
            tariffs=tariffs,
        )

    def recalc(self):
        self.mech.update_area_summary()
        inp = self.collect_inputs()

        ui_cplx = self.components.section_complexity()
        ui_stack = self.stackup.ui_to_dict().get("settings", {})
        ui_nsig = len(self.signals.collect_interfaces())

        res = estimate_layout_quote(inp, coeffs=self.coeffs, ui_complexity=ui_cplx, ui_stackup=ui_stack, ui_signals_count=ui_nsig)
        self.signals.update_from_results(res)
        self.results.set_results(res)
        self.stackup._update_thickness_views()


def save_project_json(path: str, form: QuoteForm) -> None:
    inp = form.collect_inputs()
    ui = form.ui_state_to_dict()
    payload = io_utils.project_to_dict(inp, form.coeffs, ui)
    io_utils.save_json(path, payload)


def load_project_json(path: str, form: QuoteForm) -> None:
    d = io_utils.load_json(path)
    inp, coeffs, ui = io_utils.dict_to_project(d)

    form.coeffs = coeffs

    # If v2 UI exists, load UI first, then load numeric/mech inputs without overwriting UI tables
    if isinstance(ui, dict) and ui:
        form.load_ui_state(ui)
        form.load_inputs(inp, skip_components=True, skip_signals=True)
    else:
        # legacy
        form.load_inputs(inp, skip_components=False, skip_signals=False)

    form.recalc()