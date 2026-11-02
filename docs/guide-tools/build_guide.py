"""Builds frontend/public/guide/<lang>/index.html from docs/guide/<lang>.html.

Sources hold only the page body; this script adds the shared head, icons, the
language switcher and the shared guide.css / guide.js. guide/index.html picks
the reader's language (the app's saved choice first, then the browser's).
Usage: python3 docs/guide-tools/build_guide.py
"""
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC, OUT = ROOT / "docs" / "guide", ROOT / "frontend" / "public" / "guide"
LANGS = {"ru": "Русский", "en": "English", "de": "Deutsch", "cs": "Čeština", "be": "Беларуская", "kk": "Қазақша", "ka": "ქართული"}
FONTS = ("https://fonts.googleapis.com/css2?family=Onest:wght@400;500;600;700&family=Unbounded:wght@400;500;600"
         "&family=Noto+Sans+Georgian:wght@400;500;600;700&display=swap")
icons = json.loads((SRC / "icons.json").read_text(encoding="utf-8"))

PAGE = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title}</title>
<meta name="description" content="{desc}" />
<link rel="icon" href="../../favicon.ico" />
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="{fonts}" rel="stylesheet" />
<link href="../guide.css" rel="stylesheet" />
</head>
<body>
{body}
<script src="../guide.js"></script>
</body>
</html>
"""


def switcher(lang: str) -> str:
    opts = "".join(f'<option value="{c}"{" selected" if c == lang else ""} lang="{c}">{n}</option>' for c, n in LANGS.items() if (SRC / f"{c}.html").exists())
    return f'<label class="langs">{icons["globe"]}<select aria-label="Language" onchange="location.href=\'../\'+this.value+\'/\'">{opts}</select></label>'


built = []
for lang in LANGS:
    f = SRC / f"{lang}.html"
    if not f.exists():
        continue
    text = f.read_text(encoding="utf-8")
    title = re.search(r"<!-- title: (.*?) -->", text).group(1)
    desc = re.search(r"<!-- description: (.*?) -->", text).group(1)
    body = re.sub(r"<!-- (title|description): .*? -->\n", "", text)
    body = body.replace('src="../alexandria-planner-logo.svg"', 'src="../../alexandria-planner-logo.svg"')
    body = body.replace("{{langs}}", switcher(lang))
    body = re.sub(r"\{\{icon:(\w+)\}\}", lambda m: icons[m.group(1)], body)
    missing = re.findall(r"\{\{[^}]*\}\}", body)
    assert not missing, (lang, missing)
    (OUT / lang).mkdir(parents=True, exist_ok=True)
    (OUT / lang / "index.html").write_text(PAGE.format(lang=lang, title=html.escape(title, quote=False), desc=html.escape(desc), fonts=FONTS, body=body), encoding="utf-8")
    built.append(lang)

codes = json.dumps(built)
(OUT / "index.html").write_text(f"""<!doctype html>
<html><head><meta charset="utf-8" /><title>Alexandria Planner</title>
<script>
  // same origin as the app, so the app's saved language wins
  var codes = {codes}, pick = null
  try {{ pick = localStorage.getItem('lang') }} catch (e) {{}}
  if (codes.indexOf(pick) < 0) pick = (navigator.languages || [navigator.language]).map(function (l) {{ return l.slice(0, 2) }}).filter(function (l) {{ return codes.indexOf(l) >= 0 }})[0] || 'en'
  location.replace(pick + '/' + location.hash)
</script>
</head><body><noscript>{" · ".join(f'<a href="{c}/">{LANGS[c]}</a>' for c in built)}</noscript></body></html>
""", encoding="utf-8")
print("built", built)
