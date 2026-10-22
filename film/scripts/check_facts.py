"""Every line the film shows must come from facts.json. This checks the
crew-line drafts: allowed in drafts, refused in a final render."""

import json
import sys
from pathlib import Path

FILM = Path(__file__).resolve().parents[1]
facts = json.loads((FILM / "facts.json").read_text())["facts"]
drafts = [f["id"] for f in facts if f.get("draft")]
if drafts:
    msg = "draft facts still in use: " + ", ".join(drafts)
    if "--final" in sys.argv:
        sys.exit("refusing final render, " + msg)
    print("warning:", msg)
else:
    print("facts: no drafts")
