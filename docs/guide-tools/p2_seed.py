"""Phase 2: demo department with fictional people and stickers in every state."""
import json
from datetime import date, timedelta

import httpx

from common import C, PW, U, WORK, fresh_code, logins

B = U + "/api/"
d = lambda n: (date.today() + timedelta(days=n)).isoformat()  # noqa: E731
boss = httpx.Client(base_url=B)
boss.post("auth/login", json={"login": logins()["boss"], "password": PW}).raise_for_status()
boss.post("auth/totp", json={"code": fresh_code()}).raise_for_status()

boss.post("admin/departments", json={"name": C["dept2"]}).raise_for_status()
people, names = {}, logins()
for key, color, dep in [("iv", "#4f9d69", 1), ("ma", "#d9822b", 1), ("ol", "#7c5cc4", 1), ("da", "#c2546b", 1), ("pa", "#2e86ab", 2)]:
    fn, ln = C[key]
    r = boss.post("admin/users", json={"first_name": fn, "last_name": ln, "password": PW, "department_id": dep, "avatar_color": color}); r.raise_for_status()
    names[key] = r.json()["login"]
    c = httpx.Client(base_url=B)
    c.post("auth/login", json={"login": names[key], "password": PW}).raise_for_status()
    people[key] = c
(WORK / "logins.json").write_text(json.dumps(names))
ids = {u["display_name"]: u["id"] for u in boss.get("directory/users").json()}


def mk(c, **kw):
    r = c.post("stickers", json=kw); r.raise_for_status(); return r.json()["id"]


def act(c, sid, action, **kw):
    c.post(f"stickers/{sid}/actions", json={"action": action, **kw}).raise_for_status()


def place(sid, q):
    boss.put(f"stickers/{sid}/place", json={"quadrant": q}).raise_for_status()


iv, ma, ol, da = people["iv"], people["ma"], people["ol"], people["da"]
# history first (so it lands in archive / stats)
r1 = mk(ma, title=C["r1"]); act(boss, r1, "resolve", outcome="done", text=C["r1a"]); act(ma, r1, "confirm")
r2 = mk(ma, title=C["r2"], important=True); place(r2, "plan"); act(boss, r2, "resolve", outcome="approved", text=C["r2a"]); act(ma, r2, "confirm")
r3 = mk(ol, title=C["r3"]); place(r3, "drop"); act(boss, r3, "reject", text=C["r3a"])
r4 = mk(ma, title=C["r4"], urgent=True); act(ma, r4, "withdraw")
r5 = mk(da, title=C["r5"], urgent=True); place(r5, "do"); act(boss, r5, "resolve", outcome="declined", text=C["r5a"]); act(da, r5, "confirm")
r6 = mk(iv, title=C["r6"], urgent=True, important=True); place(r6, "do"); act(boss, r6, "resolve", outcome="done", text=C["r6a"]); act(iv, r6, "confirm")
h = mk(iv, title=C["h"], important=True); place(h, "plan"); act(boss, h, "resolve", outcome="approved", text=C["ha"])
# inbox
mk(iv, title=C["in1"], body=C["in1b"], important=True, deadline=d(3))
mk(ma, title=C["main"], body=C["mainb"], urgent=True, important=True, deadline=d(1))
mk(ol, title=C["in3"], urgent=True)
# board
a = mk(ma, title=C["a"], body=C["ab"], urgent=True, important=True, deadline=d(-1)); place(a, "do")
g = mk(ol, title=C["g"], urgent=True); place(g, "do")
b = mk(iv, title=C["b"], important=True, deadline=d(6)); place(b, "plan"); act(boss, b, "start")
f = mk(ma, title=C["trip"], body=C["tripb"], important=True); place(f, "plan"); act(boss, f, "ask", text=C["tripq"])
k = mk(da, title=C["k"], body=C["kb"], important=True, urgent=True, deadline=d(2)); place(k, "plan")
c = mk(ol, title=C["c"], urgent=True, deadline=d(2)); place(c, "delegate"); act(boss, c, "delegate", user_id=ids[" ".join(C["iv"])], text=C["cn"])
j = mk(da, title=C["j"], urgent=True); place(j, "delegate")
e = mk(iv, title=C["e"]); place(e, "drop")
mk(boss, title=C["p1"], important=True, personal=True, deadline=d(10))
mk(boss, title=C["p2"], urgent=True, important=True, personal=True)
# employee-to-employee (manager sees only counts in stats)
mk(iv, title=C["peer"], recipient_ids=[ids[" ".join(C["ma"])]], urgent=True)
print("seeded", names)
