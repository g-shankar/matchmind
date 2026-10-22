"""Music, sound effects and the final mix, all synthesized here (no samples).

- out/audio/music.wav : the music-only track (120 BPM, beat grid = timing.json)
- out/audio/mix.wav   : music ducked under the voice, plus sfx and voice
Loudness is set afterwards by scripts/master.sh (-14 LUFS, -1 dBTP).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

FILM = Path(__file__).resolve().parents[1]
SR = 48000
rng = np.random.default_rng(7)

# A minor: Am F C G, one chord per bar
CHORDS = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]
# how busy the music is in each scene (pad, bass, kick, hats)
LAYERS = {1: (1, 0, 0, 0), 2: (1, 1, 1, 0), 3: (1, 1, 1, 1), 4: (1, 1, 1, 1),
          5: (1, 1, 1, 0), 6: (1, 1, 1, 1), 7: (1, 1, 1, 1), 8: (1, 1, 0, 0)}


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def env(n, a, r):
    e = np.ones(n)
    a, r = int(a * SR), int(r * SR)
    if a:
        e[:a] = np.linspace(0, 1, a)
    if r:
        e[-r:] *= np.linspace(1, 0, r)
    return e


def lowpass(x, cutoff):
    # one-pole, enough to soften the pad
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


def add(buf, t, sig, gain=1.0):
    i = int(round(t * SR))
    j = min(len(buf), i + len(sig))
    if j > i:
        buf[i:j] += gain * sig[: j - i]


def pad_bar(chord, dur):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    s = np.zeros(n)
    for m in chord:
        for det in (-0.08, 0.08):
            f = hz(m) * (1 + det / 100)
            s += np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(4 * np.pi * f * tt) + 0.12 * np.sin(6 * np.pi * f * tt)
    return s * env(n, 0.25, 0.3) / 10


def bass_note(m, dur):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    f = hz(m - 24)
    s = np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(4 * np.pi * f * tt)
    return s * env(n, 0.005, 0.08) * np.exp(-tt * 3)


def kick():
    n = int(0.3 * SR)
    tt = np.arange(n) / SR
    f = 45 + 80 * np.exp(-tt * 30)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 12)


def hat():
    n = int(0.05 * SR)
    x = rng.standard_normal(n)
    x = x - lowpass(x, 6000)
    return x * np.exp(-np.arange(n) / SR * 80) * 0.5


def swish(dur=0.45):
    n = int(dur * SR)
    x = rng.standard_normal(n)
    tt = np.arange(n) / SR
    cut = 300 + 5000 * np.sin(np.pi * tt / dur) ** 2
    y, acc = np.empty(n), 0.0
    for i in range(n):
        a = np.exp(-2 * np.pi * cut[i] / SR)
        acc = (1 - a) * x[i] + a * acc
        y[i] = acc
    return y * np.sin(np.pi * tt / dur) * 0.9


def click():
    n = int(0.06 * SR)
    tt = np.arange(n) / SR
    return np.sin(2 * np.pi * 1800 * tt) * np.exp(-tt * 90) * 0.5


def hit():
    n = int(0.9 * SR)
    tt = np.arange(n) / SR
    body = np.sin(2 * np.pi * np.cumsum(40 + 90 * np.exp(-tt * 18)) / SR) * np.exp(-tt * 4)
    air = rng.standard_normal(n) * np.exp(-tt * 14) * 0.15
    return body + air


def buzz():
    n = int(0.35 * SR)
    tt = np.arange(n) / SR
    sq = np.sign(np.sin(2 * np.pi * 110 * tt))
    return lowpass(sq, 1500) * env(n, 0.01, 0.08) * 0.35


SFX = {"swish": swish, "click": click, "hit": hit, "buzz": buzz}


def sfx_events(timing):
    c = timing["cues"]
    ev = [{"t": s["start"], "kind": "swish"} for s in timing["scenes"][1:]]
    ev.append({"t": c["s1a.crew"], "kind": "hit"})
    ev += [{"t": c[k], "kind": "click"} for k in c if k.startswith("s2b.") or k.startswith("s3b.")]
    ev += [{"t": c["s3c.blocks"], "kind": "buzz"}, {"t": c["s3d.templates"], "kind": "click"},
           {"t": c["s4a.saved"], "kind": "hit"}, {"t": c["s4b.kerrigan"], "kind": "click"},
           {"t": c["s4c.eighty-three"], "kind": "click"}, {"t": c["s4c.twenty-four"], "kind": "click"},
           {"t": c["s4d.four-times"], "kind": "hit"}]
    ev += [{"t": c[k], "kind": "click"} for k in c if k.startswith("s6a.")]
    ev += [{"t": c[k], "kind": "click"} for k in ("s8a.container-apps", "s8a.event-hubs", "s8a.azure-openai")]
    ev += [{"t": c["s8b.pitchpulse"], "kind": "hit"}]
    return sorted(ev, key=lambda e: e["t"])


def main() -> None:
    timing = json.loads((FILM / "timing.json").read_text())
    total = timing["duration"]
    n = int(total * SR) + SR
    music = np.zeros(n)
    bar, beat = timing["bar"], timing["beat"]

    def scene_at(t):
        for s in timing["scenes"]:
            if s["start"] <= t < s["start"] + s["duration"]:
                return s["n"]
        return 8

    k, h = kick(), hat()
    for b in range(int(total / bar)):
        t0 = b * bar
        lay = LAYERS[scene_at(t0)]
        chord = CHORDS[b % 4]
        if lay[0]:
            add(music, t0, pad_bar(chord, bar), 0.9)
        for i in range(8):
            t = t0 + i * beat / 2
            if lay[1] and i % 2 == 0:
                add(music, t, bass_note(chord[0], beat * 0.9), 0.35)
            if lay[3] and i % 2 == 1:
                add(music, t, h, 0.25)
        for i in range(4):
            if lay[2]:
                add(music, t0 + i * beat, k, 0.55)
    # fade out across the last bar
    end = int(total * SR)
    music[end - int(bar * SR):end] *= np.linspace(1, 0, int(bar * SR))
    music[end:] = 0

    out = FILM / "out/audio"
    out.mkdir(parents=True, exist_ok=True)
    sf.write(out / "music.wav", np.stack([music, music], 1) * 0.5, SR)

    # duck the music under the voice (-10 dB, 150 ms ramps)
    duck = np.ones(n)
    ramp = int(0.15 * SR)
    for line in timing["lines"]:
        a, b = int(line["speech"][0] * SR) - ramp, int(line["speech"][1] * SR) + ramp
        duck[max(a, 0):b] = np.minimum(duck[max(a, 0):b], 0.32)
    duck = np.convolve(duck, np.ones(ramp) / ramp, mode="same")

    voice = np.zeros(n)
    for line in timing["lines"]:
        v, sr = sf.read(FILM / "out/vo" / f"{line['id']}.wav")
        idx = np.arange(0, len(v) * SR / sr) * sr / SR
        v = np.interp(idx, np.arange(len(v)), v)
        add(voice, line["start"], v, 1.0)

    fx = np.zeros(n)
    events = sfx_events(timing)
    for e in events:
        add(fx, e["t"], SFX[e["kind"]](), 0.22)  # a little above the ducked music
    timing["sfx"] = events
    (FILM / "timing.json").write_text(json.dumps(timing, indent=1) + "\n")

    mix = music * 0.5 * duck + fx + voice * 0.9
    mix = mix[: int(total * SR)]
    mix /= max(1e-9, np.abs(mix).max()) / 0.9
    sf.write(out / "mix.wav", np.stack([mix, mix], 1), SR)
    print(f"music + mix written, {total:.1f} s, {len(events)} sfx")


if __name__ == "__main__":
    main()
