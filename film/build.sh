#!/usr/bin/env bash
# Rebuild the demo film from the engine's data: facts -> voice -> timing ->
# music and mix -> picture -> master. Draft by default; `./build.sh final` for 60 fps high quality.
set -euo pipefail
cd "$(dirname "$0")"
mode=${1:-draft}
python3 scripts/facts.py
python3 scripts/voice.py
python3 scripts/timing.py
python3 scripts/audio.py
python3 scripts/data_js.py
if [ "$mode" = final ]; then
  python3 scripts/check_facts.py --final
  q=high; fps=60
else
  python3 scripts/check_facts.py
  q=draft; fps=30
fi
mkdir -p out
(cd composition && npx hyperframes@0.8.181 render . -q $q -f $fps -o ../out/picture.mp4)
scripts/master.sh out/picture.mp4 out/pitchpulse-demo.mp4
