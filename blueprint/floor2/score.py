"""Action sounds for the 2F film, on the film's own clock (timeline.json written by film.py): paper air over the
sheet, a wooden knock per floor board, a plaster thud per wall block (thinned), a tink per pane, a cabinet knock
per fitted unit, a soft thump per piece of furniture, a pop per plant, a chime as the wave turns clay into wood,
a whoosh into the dive and the ceiling sliding shut. A slow pad sits under it (no music key needed).

    python ~/.claude/skills/blueprint/run_sfx.py score.py --timeline <timeline.json> --out <wav>
"""
import math
import random

from sfx.score_kit import airy, env_fade, hz
from sfx.synth import SR, blip, chime, click, impact, pad, pop, riser, whoosh

TIMELINE = "timeline.json"
TARGET_LUFS = -15.0
SEED = 412


def knock(f, dur=0.07, tau=0.018, grit=0.35):
    out = []
    for k in range(int(dur * SR)):
        t = k / SR
        s = math.sin(2 * math.pi * f * t) * math.exp(-t / tau) + 0.5 * math.sin(2 * math.pi * f * 2.3 * t) * math.exp(-t / (tau * 0.5))
        out.append(s + random.uniform(-1, 1) * math.exp(-t / 0.002) * grit)
    return out


def thump():
    out, ph = [], 0.0
    for k in range(int(0.5 * SR)):
        u = k / SR
        ph += 2 * math.pi * (70 - 30 * u) / SR
        out.append(math.sin(ph) * math.exp(-u / 0.12))
    return out


def score(mix, tl):
    random.seed(SEED)
    dur = tl["duration"]
    w0, w1 = tl["wave"]
    c0, c1 = tl["ceiling"]
    N = lambda *n: [hz(x) for x in n]
    l, r = pad(dur, [(0.0, N("D3", "A3", "E4")), (5.0, N("Bb2", "F3", "D4")), (9.0, N("G2", "D3", "Bb3")),
                     (w0, N("D3", "A3", "F#4", "A4")), (tl["dive"], N("G2", "D3", "B3", "F#4")), (c0, N("D3", "A3", "F#4", "D5"))])
    mix.put_stereo(0.0, l, r, 0.5)
    mix.put(0.0, env_fade(airy(2.4, 1800, 4200, 0.4), 0.4, 0.8), 0.006)
    mix.put(1.2, riser(1.2, 300, 2600), 0.01)
    mix.put(2.0, env_fade(airy(9.5, 400, 2200, 0.7), 1.2, 1.5), 0.016, pan=-0.2)
    k = 0
    for t, st in tl["landings"]:
        k += 1
        p = random.uniform(-0.6, 0.6)
        if st == "slab":
            mix.put(t, thump(), 0.03)
        elif st == "floor" and k % 2:
            mix.put(t, knock(random.uniform(330, 460), 0.08, 0.02, 0.4), 0.010, pan=p)
        elif st == "walls" and k % 3 == 0:
            mix.put(t, knock(random.uniform(170, 240), 0.1, 0.03, 0.5), 0.009, pan=p)
        elif st == "frames" and k % 2:
            mix.put(t, click(random.uniform(1800, 2600), 0.025), 0.009, pan=p)
        elif st == "glass":
            mix.put(t, blip(random.uniform(2800, 3600), 0.18, 0.05), 0.007, pan=p)
        elif st == "builtin" and k % 2:
            mix.put(t, knock(random.uniform(480, 640), 0.09, 0.022, 0.35), 0.011, pan=p)
        elif st == "furniture" and k % 2:
            mix.put(t, knock(random.uniform(380, 560), 0.08, 0.02, 0.25), 0.01, pan=p)
            if k % 8 == 1:
                mix.put(t - 0.02, thump(), 0.01, pan=p * 0.5)
        elif st == "decor" and k % 3 == 0:
            mix.put(t, pop(random.uniform(500, 700), random.uniform(900, 1200), 0.1), 0.008, pan=p)
        elif st == "lights":
            mix.put(t, blip(random.uniform(1500, 2100), 0.25, 0.08), 0.006, pan=p)
    mix.put(w0 - 0.8, riser(0.9, 260, 3800), 0.012)
    mix.put(w0, env_fade(airy(w1 - w0 + 0.6, 500, 3200, 0.9), 0.3, 0.8), 0.02)
    mix.put(w0 + 0.2, chime(N("D5", "A5", "F#6"), 2.4, 0.8), 0.014)
    d = tl["dive"]
    mix.put(d + 0.6, whoosh(c0 - d - 0.4, 300, 1800, 0.6), 0.022, pan=-0.1)
    mix.put(c0, whoosh(c1 - c0, 900, 250, 0.5), 0.016)
    mix.put(c1 - 0.08, thump(), 0.022)
    mix.put(c1, impact(1.0), 0.008)
    mix.put(c1, chime(N("A4", "D5", "F#5"), 1.6, 0.6), 0.01)
