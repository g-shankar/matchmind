"""Write composition/data.js: facts.json and timing.json as one script the
composition loads locally (renders may not fetch)."""

import json
from pathlib import Path

FILM = Path(__file__).resolve().parents[1]
facts = {f["id"]: f for f in json.loads((FILM / "facts.json").read_text())["facts"]}
timing = json.loads((FILM / "timing.json").read_text())
js = "window.FILM = " + json.dumps({"facts": facts, "timing": timing}, ensure_ascii=False) + ";\n"
(FILM / "composition/data.js").write_text(js)
# keep the composition's length in step with timing.json
import re
idx = FILM / "composition/index.html"
h = idx.read_text()
h = re.sub(r'(id="(?:root|stage)"[^>]*?data-duration=")[0-9.]+(")', rf"\g<1>{timing['duration']:g}\g<2>", h)
idx.write_text(h)
print("data.js", len(js), "bytes")
