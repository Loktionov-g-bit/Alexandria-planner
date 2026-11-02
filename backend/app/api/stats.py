"""Statistics page and Excel export."""

from datetime import date
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import Response

from .. import report, stats
from ..deps import DB, CurrentUser
from ..models import Department
from ..schemas import UserBrief

router = APIRouter(prefix="/api/stats", tags=["stats"])

PeriodKind = Literal["day", "week", "month", "quarter", "custom"]


async def make(db, user, period: PeriodKind, start: date | None, end: date | None):
    from ..telegram.bot import _today_local

    return await stats.build(db, user, stats.period_of(period, _today_local(user), start, end))


@router.get("")
async def overview(db: DB, user: CurrentUser, period: PeriodKind = "week", start: date | None = None, end: date | None = None) -> dict:
    rep = await make(db, user, period, start, end)
    return {
        "scope": rep.scope,
        "period": {"start": rep.period.start, "end": rep.period.end},
        "totals": rep.totals,
        "times": rep.times,
        "divergence": rep.divergence,
        "board": rep.board,
        "by_quadrant": {q: sum(1 for s in rep.stickers if s.decided_quadrant and s.decided_quadrant.value == q)
                        for q in ("do", "plan", "delegate", "drop")},
        "people": [{**{k: v for k, v in p.items() if k != "user"}, "user": UserBrief.model_validate(p["user"])} for p in rep.by_person],
        "e2e": rep.e2e,
    }


@router.get("/report.xlsx")
async def export(db: DB, user: CurrentUser, period: PeriodKind = "week", start: date | None = None, end: date | None = None) -> Response:
    rep = await make(db, user, period, start, end)
    dept = await db.get(Department, user.department_id) if user.department_id else None
    data = report.build_xlsx(rep, user, dept.name if dept else None)
    name = f"planner-report-{rep.period.start:%Y%m%d}-{rep.period.end:%Y%m%d}.xlsx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
