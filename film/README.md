# Demo film

The PitchPulse demo video, built in code from the engine's own data so every
number on screen traces back to the demo match.

- `storyboard.md`: shot list and voiceover, scene by scene.
- `brief.txt`: the brief and every production decision.
- `facts.json`: every name and number the film may show, each with its source line.
- `timing.json`: scene, voice, cue and sound-effect times on a 120 BPM grid.
- `composition/`: the HyperFrames scenes (HTML, SVG and GSAP; no screenshots).
- `scripts/`: facts, voice (Kokoro, local), timing, music and sfx (synthesized), mastering.

Build: `pip install -e backend kokoro-onnx soundfile`, put the Kokoro v1.0 model
files in `~/.cache/kokoro`, then `./film/build.sh` (draft) or `./film/build.sh final`.
Output lands in `film/out/`.
