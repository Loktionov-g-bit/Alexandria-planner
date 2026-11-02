import sys
from datetime import date, datetime
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

INK, MUTED, LINE, BAND, LATE = "16191E", "535D69", "D5DAE1", "F4F6F9", "B42318"
Q = {
    "q1": ("Срочно и важно", "F4B6A7"),
    "q2": ("Важно, не срочно", "B7DCC2"),
    "q3": ("Срочно, не важно", "F6D887"),
    "q4": ("Не срочно, не важно", "C5D1E3"),
}
FONT = "Calibri"
thin = Side(style="thin", color=LINE)
B_BOTTOM = Border(bottom=thin)
fill = lambda c: PatternFill("solid", start_color=c, end_color=c)
f = lambda size=11, bold=False, color=INK: Font(name=FONT, size=size, bold=bold, color=color)

STICKERS = [
    (101, "Заказать новые кружки на кухню", "Петрова А.", "Руководитель", "q4", "q4", date(2026, 10, 20), None, None, "Отложен", ""),
    (104, "Сверка актов до конца года", "Бухгалтерия", "Руководитель", "q2", "q2", date(2026, 10, 26), date(2026, 12, 20), None, "Разобран", "групповой"),
    (108, "Отчёт за октябрь для дирекции", "Руководитель", "Руководитель", "q1", "q1", date(2026, 10, 27), date(2026, 10, 30), None, "В работе", "личный"),
    (110, "План обучения нового сотрудника", "Петрова А.", "Руководитель", "q2", "q2", date(2026, 10, 28), date(2026, 11, 15), None, "Разобран", ""),
    (112, "Согласовать закупку картриджей", "Иванов И.", "Руководитель", "q1", "q1", date(2026, 10, 29), date(2026, 11, 5), None, "В работе", ""),
    (113, "Сломался кондиционер в серверной", "Козлов Д.", "Руководитель", "q1", "q1", date(2026, 10, 29), date(2026, 10, 30), None, "В работе", ""),
    (114, "Перенос встречи с поставщиком", "Смирнова Е.", "Руководитель", "q1", "q1", date(2026, 10, 30), date(2026, 11, 3), date(2026, 10, 30), "Закрыт", "согласовано"),
    (115, "Подписать акт выполненных работ", "Петрова А.", "Руководитель", "q1", "q1", date(2026, 10, 30), date(2026, 10, 31), date(2026, 10, 31), "Решён", "выполнено"),
    (116, "Пропуск для курьера на завтра", "Смирнова Е.", "Козлов Д.", "q3", "q1", date(2026, 10, 31), date(2026, 11, 1), None, "Делегирован", ""),
    (118, "Не работает принтер на втором этаже", "Козлов Д.", "Руководитель", None, "q3", date(2026, 10, 31), date(2026, 10, 31), None, "Новый", ""),
    (119, "Нужна подпись на договоре поставки", "Смирнова Е.", "Руководитель", None, "q1", date(2026, 10, 31), date(2026, 11, 1), None, "Новый", ""),
    (120, "Согласовать скидку 12% для клиента", "Иванов И.", "Руководитель", "q1", "q1", date(2026, 10, 31), date(2026, 10, 31), date(2026, 10, 31), "Решён", "согласовано"),
    (121, "Ответить на претензию клиента", "Смирнова Е.", "Руководитель", "q1", "q1", date(2026, 10, 31), date(2026, 11, 1), None, "В работе", ""),
    (122, "Проверить счёт перед оплатой", "Иванов И.", "Руководитель", "q1", "q2", date(2026, 10, 31), date(2026, 11, 1), date(2026, 10, 31), "Решён", "отклонено"),
]
TODAY = date(2026, 10, 31)


def title_block(ws, title, subtitle, width_cols):
    ws.sheet_view.showGridLines = False
    ws.row_dimensions[1].height = 8
    ws["B2"] = "ALEXANDRIA · ПЛАНЕР"
    ws["B2"].font = f(9, True, MUTED)
    ws["B3"] = title
    ws["B3"].font = f(22, True)
    ws.row_dimensions[3].height = 34
    ws["B4"] = subtitle
    ws["B4"].font = f(11, False, MUTED)
    for c in range(2, 2 + width_cols):
        ws.cell(row=5, column=c).border = Border(bottom=Side(style="medium", color=INK))
    ws.column_dimensions["A"].width = 3


def header_row(ws, row, headers, col0=2):
    for i, h in enumerate(headers):
        c = ws.cell(row=row, column=col0 + i, value=h)
        c.font = f(10, True, "FFFFFF")
        c.fill = fill(INK)
        c.alignment = Alignment(vertical="center", horizontal="left", indent=1, wrap_text=True)
    ws.row_dimensions[row].height = 30


wb = Workbook()

# --- Сводка ---------------------------------------------------------------
ws = wb.active
ws.title = "Сводка"
title_block(ws, "Отчёт по стикерам", "Отдел продаж · 26 — 31 октября 2026 · сформирован 31.10.2026 02:40", 8)
for col, w in zip("BCDEFGHI", (24, 4, 24, 4, 24, 4, 24, 4)):
    ws.column_dimensions[col].width = w

active = [s for s in STICKERS if s[9] not in ("Решён", "Закрыт")]
late = [s for s in active if s[7] and s[7] < TODAY]
solved = [s for s in STICKERS if s[9] in ("Решён", "Закрыт")]
kpis = [
    ("Всего стикеров", len(STICKERS), INK),
    ("Решено", len(solved), INK),
    ("В работе / на доске", len(active), INK),
    ("Просрочено", len(late), LATE),
]
for i, (label, val, color) in enumerate(kpis):
    col = 2 + i * 2
    lc = ws.cell(row=7, column=col, value=label.upper())
    lc.font = f(9, True, MUTED)
    vc = ws.cell(row=8, column=col, value=val)
    vc.font = f(30, True, color)
    vc.alignment = Alignment(horizontal="left")
    ws.cell(row=9, column=col).border = Border(bottom=Side(style="thin", color=LINE))
ws.row_dimensions[8].height = 44

ws["B11"] = "Распределение по квадрантам"
ws["B11"].font = f(13, True)
header_row(ws, 12, ["Квадрант", "", "Стикеров", "", "Доля"])
ws.merge_cells("B12:C12"); ws.merge_cells("D12:E12"); ws.merge_cells("F12:G12")
on_board = [s for s in STICKERS if s[4]]
for i, (key, (name, color)) in enumerate(Q.items()):
    r = 13 + i
    n = sum(1 for s in on_board if s[4] == key)
    ws.cell(row=r, column=2, value=name).font = f(11, True)
    ws.cell(row=r, column=2).fill = fill(color)
    ws.cell(row=r, column=3).fill = fill(color)
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
    ws.cell(row=r, column=4, value=n).font = f(11)
    ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=5)
    pc = ws.cell(row=r, column=6, value=f"=D{r}/SUM($D$13:$D$16)")
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
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.chart.marker import DataPoint
for idx, (_, color) in enumerate(Q.values()):
    pt = DataPoint(idx=idx)
    pt.graphicalProperties = GraphicalProperties(solidFill=color)
    pt.graphicalProperties.line.solidFill = color
    ser.dPt.append(pt)
ser.dLbls = DataLabelList(); ser.dLbls.showVal = True
chart.x_axis.scaling.orientation = "maxMin"
chart.height, chart.width = 6.5, 15
ws.add_chart(chart, "B19")

ws["B33"] = "Неразобранных во «Входящих»: " + str(sum(1 for s in STICKERS if not s[4]))
ws["B33"].font = f(11, False, MUTED)
ws["B34"] = "Среднее время до решения: 0,8 дн."
ws["B34"].font = f(11, False, MUTED)

# --- Стикеры --------------------------------------------------------------
ws2 = wb.create_sheet("Стикеры")
title_block(ws2, "Все стикеры за период", "Сортировка: просроченные сверху, затем по сроку", 11)
heads = ["№", "Заголовок", "Автор", "Исполнитель", "Квадрант", "Оценка автора", "Создан", "Срок", "Решён", "Статус", "Итог / пометка"]
widths = [7, 40, 16, 16, 21, 21, 12, 12, 12, 14, 16]
for i, w in enumerate(widths):
    ws2.column_dimensions[get_column_letter(2 + i)].width = w
header_row(ws2, 7, heads)
rows = sorted(STICKERS, key=lambda s: (0 if (s[7] and s[7] < TODAY and s[9] not in ("Решён", "Закрыт")) else 1, s[7] or date(2099, 1, 1)))
for i, s in enumerate(rows):
    r = 8 + i
    is_late = s[7] and s[7] < TODAY and s[9] not in ("Решён", "Закрыт")
    vals = [s[0], s[1], s[2], s[3], Q[s[4]][0] if s[4] else "Входящие", Q[s[5]][0], s[6], s[7], s[8], s[9], s[10]]
    for j, v in enumerate(vals):
        c = ws2.cell(row=r, column=2 + j, value=v)
        c.font = f(10.5)
        c.border = B_BOTTOM
        c.alignment = Alignment(vertical="center", indent=1)
        if i % 2:
            c.fill = fill(BAND)
        if isinstance(v, date):
            c.number_format = "DD.MM.YYYY"
    qc = ws2.cell(row=r, column=6)
    if s[4]:
        qc.fill = fill(Q[s[4]][1])
    ec = ws2.cell(row=r, column=7)
    if s[4] and s[5] != s[4]:
        ec.font = f(10.5, True, "7A4FD0")
    if is_late:
        ws2.cell(row=r, column=9).font = f(10.5, True, LATE)
        ws2.cell(row=r, column=11).value = "Просрочен"
        ws2.cell(row=r, column=11).font = f(10.5, True, LATE)
    ws2.row_dimensions[r].height = 22
last = 7 + len(rows)
ws2.auto_filter.ref = f"B7:L{last}"
ws2.freeze_panes = "C8"
ws2.cell(row=last + 2, column=2, value="Фиолетовым — оценка автора, не совпавшая с решением руководителя.").font = f(9.5, False, MUTED)

# --- По сотрудникам -------------------------------------------------------
ws3 = wb.create_sheet("По сотрудникам")
title_block(ws3, "Нагрузка по сотрудникам", "Отправлено, решено, время ответа и расхождения оценок", 6)
heads = ["Сотрудник", "Отправил стикеров", "Из них решено", "Ср. время ответа, дн.", "Расхождений оценки", "Доля расхождений"]
for i, w in enumerate([22, 18, 16, 20, 20, 18]):
    ws3.column_dimensions[get_column_letter(2 + i)].width = w
header_row(ws3, 7, heads)
people = ["Иванов И.", "Петрова А.", "Смирнова Е.", "Козлов Д."]
avg = {"Иванов И.": 0.4, "Петрова А.": 1.1, "Смирнова Е.": 0.6, "Козлов Д.": 1.9}
for i, p in enumerate(people):
    r = 8 + i
    mine = [s for s in STICKERS if s[2] == p]
    vals = [p, len(mine), sum(1 for s in mine if s[9] in ("Решён", "Закрыт")), avg[p], sum(1 for s in mine if s[4] and s[4] != s[5]), f"=IF(C{r}=0,0,F{r}/C{r})"]
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
r = 8 + len(people)
ws3.cell(row=r, column=2, value="Итого").font = f(11, True)
for col in (3, 4, 6):
    L = get_column_letter(col)
    ws3.cell(row=r, column=col, value=f"=SUM({L}8:{L}{r-1})").font = f(11, True)
ws3.cell(row=r, column=5, value=f"=AVERAGE(E8:E{r-1})").font = f(11, True)
ws3.cell(row=r, column=5).number_format = "0.0"
for c in range(2, 8):
    ws3.cell(row=r, column=c).border = Border(top=Side(style="medium", color=INK))
ws3.freeze_panes = "C8"

for w in wb.worksheets:
    w.sheet_properties.tabColor = INK
    w.page_setup.orientation = "landscape"
    w.page_setup.fitToWidth = 1
    w.sheet_properties.pageSetUpPr.fitToPage = True

wb.save(sys.argv[1])
print("ok")
