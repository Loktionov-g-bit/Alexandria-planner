"""Excel report in the template approved on 2026-10-31 (docs/report-sample-generator.py, docs/report-sample.pdf).
No beige anywhere: cool greys, ink headers, quadrant colours."""

import io
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.marker import DataPoint
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import stickers as lc
from .locales import decimal, texts
from .models import Status, Sticker, User
from .stats import DONE, Report, executor

INK, MUTED, LINE, BAND, LATE, VIOLET = "16191E", "535D69", "D5DAE1", "F4F6F9", "B42318", "7A4FD0"
COLORS = {"do": "F4B6A7", "plan": "B7DCC2", "delegate": "F6D887", "drop": "C5D1E3"}
FONT = "Calibri"

L = texts("report")

thin = Side(style="thin", color=LINE)
B_BOTTOM = Border(bottom=thin)


def fill(c: str) -> PatternFill:
    return PatternFill("solid", start_color=c, end_color=c)


def f(size: float = 11, bold: bool = False, color: str = INK) -> Font:
    return Font(name=FONT, size=size, bold=bold, color=color)


def title_block(ws, tx: dict, title: str, subtitle: str, width_cols: int) -> None:
    ws.sheet_view.showGridLines = False
    ws.row_dimensions[1].height = 8
    ws["B2"] = tx["brand"]
    ws["B2"].font = f(9, True, MUTED)
    ws["B3"] = title
    ws["B3"].font = f(22, True)
    ws.row_dimensions[3].height = 34
    ws["B4"] = subtitle
    ws["B4"].font = f(11, False, MUTED)
    for c in range(2, 2 + width_cols):
        ws.cell(row=5, column=c).border = Border(bottom=Side(style="medium", color=INK))
    ws.column_dimensions["A"].width = 3


def header_row(ws, row: int, headers: list[str], col0: int = 2) -> None:
    for i, h in enumerate(headers):
        c = ws.cell(row=row, column=col0 + i, value=h)
        c.font = f(10, True, "FFFFFF")
        c.fill = fill(INK)
        c.alignment = Alignment(vertical="center", horizontal="left", indent=1, wrap_text=True)
    ws.row_dimensions[row].height = 30


def local(dt: datetime | None, tz) -> date | None:
    return dt.astimezone(tz).date() if dt else None


def build_xlsx(rep: Report, user: User, dept_name: str | None) -> bytes:
    tx = L.get(user.locale, L["ru"])
    try:
        tz = ZoneInfo(user.timezone)
    except Exception:  # noqa: BLE001
        tz = timezone.utc
    today = date.today()
    now = datetime.now(tz)
    period = f"{rep.period.start:%d.%m.%Y} — {rep.period.end:%d.%m.%Y}"
    who = dept_name if rep.scope == "received" and dept_name else (tx["mine"] if rep.scope == "sent" else user.display_name)
    subtitle = f"{who} · {period} · {tx['made']} {now:%d.%m.%Y %H:%M}"
    items: list[Sticker] = rep.stickers

    def is_late(s: Sticker) -> bool:
        return bool(s.deadline and s.deadline < today and s.status in lc.ACTIVE)

    wb = Workbook()
    # --- Summary
    ws = wb.active
    ws.title = tx["s_sheet"]
    title_block(ws, tx, tx["title"], subtitle, 8)
    for col, w in zip("BCDEFGHI", (24, 4, 24, 4, 24, 4, 24, 4)):
        ws.column_dimensions[col].width = w
    tot = rep.totals
    for i, (label, val, color) in enumerate(zip(tx["kpi"], (tot["total"], tot["resolved"], tot["active"], tot["overdue"]), (INK, INK, INK, LATE))):
        col = 2 + i * 2
        ws.cell(row=7, column=col, value=label.upper()).font = f(9, True, MUTED)
        vc = ws.cell(row=8, column=col, value=val)
        vc.font = f(30, True, color)
        vc.alignment = Alignment(horizontal="left")
        ws.cell(row=9, column=col).border = B_BOTTOM
    ws.row_dimensions[8].height = 44

    ws["B11"] = tx["dist"]
    ws["B11"].font = f(13, True)
    header_row(ws, 12, tx["dist_head"])
    ws.merge_cells("B12:C12")
    ws.merge_cells("D12:E12")
    ws.merge_cells("F12:G12")
    for i, q in enumerate(("do", "plan", "delegate", "drop")):
        r = 13 + i
        n = sum(1 for s in items if s.decided_quadrant and s.decided_quadrant.value == q)
        ws.cell(row=r, column=2, value=tx["q"][q]).font = f(11, True)
        ws.cell(row=r, column=2).fill = fill(COLORS[q])
        ws.cell(row=r, column=3).fill = fill(COLORS[q])
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
        ws.cell(row=r, column=4, value=n).font = f(11)
        ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=5)
        pc = ws.cell(row=r, column=6, value=f"=IF(SUM($D$13:$D$16)=0,0,D{r}/SUM($D$13:$D$16))")
        pc.number_format = "0%"
        pc.font = f(11)
        ws.merge_cells(start_row=r, start_column=6, end_row=r, end_column=7)
        for c in range(2, 8):
            ws.cell(row=r, column=c).border = B_BOTTOM
            ws.cell(row=r, column=c).alignment = Alignment(vertical="center", indent=1)
        ws.row_dimensions[r].height = 24

    chart = BarChart()
    chart.type = "bar"
    chart.style = 10
    chart.title = None
    chart.legend = None
    chart.y_axis.majorGridlines = None
    chart.y_axis.delete = True
    chart.x_axis.delete = False
    chart.add_data(Reference(ws, min_col=4, min_row=13, max_row=16), titles_from_data=False)
    chart.set_categories(Reference(ws, min_col=2, min_row=13, max_row=16))
    ser = chart.series[0]
    for idx, q in enumerate(("do", "plan", "delegate", "drop")):
        pt = DataPoint(idx=idx)
        pt.graphicalProperties = GraphicalProperties(solidFill=COLORS[q])
        pt.graphicalProperties.line.solidFill = COLORS[q]
        ser.dPt.append(pt)
    ser.dLbls = DataLabelList()
    ser.dLbls.showVal = True
    chart.x_axis.scaling.orientation = "maxMin"
    chart.height, chart.width = 6.5, 15
    ws.add_chart(chart, "B19")

    inbox = sum(1 for s in items if s.decided_quadrant is None and s.status == Status.new)
    t = rep.times["total"]
    ws["B33"] = tx["inbox_line"].format(n=inbox)
    ws["B33"].font = f(11, False, MUTED)
    ws["B34"] = tx["avg_line"].format(v=decimal(user.locale, f"{t / 24:.1f}") + f" {tx['days']}" if t is not None else tx["nodata"])
    ws["B34"].font = f(11, False, MUTED)

    # --- Stickers
    ws2 = wb.create_sheet(tx["l_sheet"])
    title_block(ws2, tx, tx["l_title"], tx["l_sub"], 11)
    for i, w in enumerate([7, 40, 16, 16, 21, 21, 12, 12, 12, 16, 16]):
        ws2.column_dimensions[get_column_letter(2 + i)].width = w
    header_row(ws2, 7, tx["l_head"])
    rows = sorted(items, key=lambda s: (0 if is_late(s) else 1, s.deadline or date(2099, 1, 1), s.id))
    for i, s in enumerate(rows):
        r = 8 + i
        aq = lc.author_quadrant(s).value
        note = tx["outcome"].get(s.outcome.value, "") if s.outcome else ""
        vals = [s.id, s.title, s.author.display_name, executor(s), tx["q"][s.decided_quadrant.value] if s.decided_quadrant else tx["inbox"],
                tx["q"][aq], local(s.created_at, tz), s.deadline, local(s.resolved_at, tz), tx["status"][s.status.value], note]
        for j, v in enumerate(vals):
            c = ws2.cell(row=r, column=2 + j, value=v)
            c.font = f(10.5)
            c.border = B_BOTTOM
            c.alignment = Alignment(vertical="center", indent=1)
            if i % 2:
                c.fill = fill(BAND)
            if isinstance(v, date):
                c.number_format = "DD.MM.YYYY"
        if s.decided_quadrant:
            ws2.cell(row=r, column=6).fill = fill(COLORS[s.decided_quadrant.value])
            if s.decided_quadrant.value != aq:
                ws2.cell(row=r, column=7).font = f(10.5, True, VIOLET)
        if is_late(s):
            ws2.cell(row=r, column=9).font = f(10.5, True, LATE)
            ws2.cell(row=r, column=12).value = tx["late"]
            ws2.cell(row=r, column=12).font = f(10.5, True, LATE)
        ws2.row_dimensions[r].height = 22
    last = 7 + max(len(rows), 1)
    ws2.auto_filter.ref = f"B7:L{last}"
    ws2.freeze_panes = "C8"
    ws2.cell(row=last + 2, column=2, value=tx["legend"]).font = f(9.5, False, MUTED)

    # --- By person
    ws3 = wb.create_sheet(tx["p_sheet"])
    title_block(ws3, tx, tx["p_title"], tx["p_sub"], 6)
    for i, w in enumerate([22, 18, 16, 20, 20, 18]):
        ws3.column_dimensions[get_column_letter(2 + i)].width = w
    header_row(ws3, 7, tx["p_head"] if rep.scope == "received" else tx["p_head_sent"])
    for i, p in enumerate(rep.by_person):
        r = 8 + i
        h = p["avg_response_hours"]
        vals = [p["user"].display_name, p["sent"], p["resolved"], round(h / 24, 1) if h is not None else None, p["diverged"],
                f"=IF(C{r}=0,0,F{r}/C{r})"]
        for j, v in enumerate(vals):
            c = ws3.cell(row=r, column=2 + j, value=v)
            c.font = f(11, j == 0)
            c.border = B_BOTTOM
            c.alignment = Alignment(vertical="center", indent=1)
            if i % 2:
                c.fill = fill(BAND)
        ws3.cell(row=r, column=5).number_format = "0.0"
        ws3.cell(row=r, column=7).number_format = "0%"
        ws3.row_dimensions[r].height = 24
    r = 8 + len(rep.by_person)
    ws3.cell(row=r, column=2, value=tx["total"]).font = f(11, True)
    if rep.by_person:
        for col in (3, 4, 6):
            letter = get_column_letter(col)
            ws3.cell(row=r, column=col, value=f"=SUM({letter}8:{letter}{r - 1})").font = f(11, True)
        ws3.cell(row=r, column=5, value=f"=IFERROR(AVERAGE(E8:E{r - 1}),0)").font = f(11, True)
        ws3.cell(row=r, column=5).number_format = "0.0"
        ws3.cell(row=r, column=7, value=f"=IF(C{r}=0,0,F{r}/C{r})").number_format = "0%"
    for c in range(2, 8):
        ws3.cell(row=r, column=c).border = Border(top=Side(style="medium", color=INK))
    ws3.freeze_panes = "C8"

    for w in wb.worksheets:
        w.sheet_properties.tabColor = INK
        w.page_setup.orientation = "landscape"
        w.page_setup.fitToWidth = 1
        w.sheet_properties.pageSetUpPr.fitToPage = True
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


__all__ = ["build_xlsx", "DONE"]
