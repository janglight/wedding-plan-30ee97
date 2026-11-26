"""The film: the plan photo on a desk, the unit assembling itself on it in white clay (each system flashing its
colour), a wave from the living room turning clay into oak, plaster and linen, then a dive in as the ceiling closes.

    python3 film.py [--res 960x540] [--samples 16] [--step 1] [--stills 1.0,6.5,12.5]   (resumes: existing frames are kept)
"""
import sys, os, json, math, random, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from mathutils import Vector
import house as K

a = sys.argv[1:]
opt = {a[i][2:]: a[i + 1] for i in range(len(a)) if a[i].startswith("--")}
res = tuple(map(int, opt.get("res", "960x540").split("x")))
FPS = 24
DUR = 20.9
OUT = os.path.join(os.environ.get("BLUEPRINT_OUT", os.path.join(K.HERE, "..", "..", "blueprint-out")), "floor2", opt.get("dir", "film"))
os.makedirs(OUT, exist_ok=True)
s = K.build(samples=int(opt.get("samples", 16)), res=res)
s.cycles.adaptive_threshold = 0.05
random.seed(3)

# stage: (first launch, last launch, flash colour, label)
STAGES = {
    "slab": (2.3, 2.3, (0.6, 0.6, 0.6), "SLAB"),
    "floor": (2.7, 5.0, (1.0, 0.55, 0.1), "FLOOR"),
    "walls": (4.7, 7.6, (0.1, 0.55, 1.0), "WALLS"),
    "frames": (7.4, 8.5, (0.2, 1.0, 0.4), "DOORS & WINDOWS"),
    "glass": (8.3, 8.9, (0.2, 0.9, 1.0), "GLASS"),
    "builtin": (8.7, 9.7, (0.9, 0.2, 1.0), "KITCHEN & BUILT-INS"),
    "furniture": (9.5, 10.7, (1.0, 0.35, 0.1), "FURNITURE"),
    "decor": (10.5, 11.3, (1.0, 0.3, 0.6), "PLANTS & DECOR"),
    "lights": (11.1, 11.5, (1.0, 0.9, 0.3), "LIGHTS"),
}
FLY = 0.55
WAVE = (11.9, 13.7)
CEIL = (19.05, 19.95)

by = {}
for o, st in K.PARTS:
    by.setdefault(st, []).append(o)
C = Vector((5.25, 4.45, 0))
ORDER = {
    "floor": lambda o: o.location.x + o.location.y + random.uniform(0, 1.5),
    "walls": lambda o: round(o.location.z / 0.6) * 10 + math.atan2(o.location.y - C.y, o.location.x - C.x),
}
SCHED = []   # (object, launch, stage, kind)
for st, (t0, t1, col, label) in STAGES.items():
    objs = [o for o in by.get(st, []) if o.users_collection[0].name != "ceiling"]
    objs.sort(key=ORDER.get(st, lambda o: (o.location - Vector(K.FOCUS)).length + random.uniform(0, 1)))
    for i, o in enumerate(objs):
        SCHED.append((o, t0 + (t1 - t0) * i / max(1, len(objs) - 1), st, "drop"))
ceil = sorted(K.coll("ceiling").objects, key=lambda o: -o.location.y)
for i, o in enumerate(ceil):
    SCHED.append((o, CEIL[0] + (CEIL[1] - CEIL[0] - 0.5) * i / max(1, len(ceil) - 1), "ceiling", "slide"))
HOME = {o.name: (Vector(o["home"]) if "home" in o else o.location.copy()) for o, *_ in SCHED}

# camera: (t, location, target, lens)
CAM = [
    (0.0, (5.25, 4.2, 46.0), (5.25, 4.45, 0), 96),
    (2.6, (5.6, 3.2, 41.0), (5.25, 4.45, 0), 88),
    (6.0, (10.5, -3.0, 27.0), (5.3, 4.3, 0.2), 62),
    (9.5, (14.0, -6.5, 16.0), (5.5, 4.1, 0.3), 42),
    (13.0, (15.2, -5.2, 14.0), (5.7, 4.0, 0.4), 40),
    (15.2, (15.0, -1.5, 11.5), (6.4, 3.8, 0.6), 38),
    (17.3, (9.6, 7.2, 6.2), (8.6, 3.0, 0.6), 26),
    (18.6, (7.9, 6.1, 2.95), (8.8, 1.6, 0.6), 20),
    (19.6, (7.75, 5.75, 1.62), (8.9, 0.9, 0.62), 17),
    (DUR, (7.79, 5.62, 1.6), (8.9, 0.9, 0.62), 17),
]


def hermite(keys, t):
    t = min(max(t, keys[0][0]), keys[-1][0])
    i = max(k for k in range(len(keys) - 1) if keys[k][0] <= t)
    def tan(k):
        if k == 0 or k == len(keys) - 1:
            return keys[k][1] * 0
        return (keys[k + 1][1] - keys[k - 1][1]) / (keys[k + 1][0] - keys[k - 1][0])
    t0, p0 = keys[i]; t1, p1 = keys[i + 1]
    h = t1 - t0; u = (t - t0) / h
    return ((2 * u ** 3 - 3 * u ** 2 + 1) * p0 + (u ** 3 - 2 * u ** 2 + u) * h * tan(i)
            + (-2 * u ** 3 + 3 * u ** 2) * p1 + (u ** 3 - u ** 2) * h * tan(i + 1))


cam = K.camera((0, 0, 10), (0, 0, 0), 50)
KL = [(k[0], Vector(k[1])) for k in CAM]; KT = [(k[0], Vector(k[2])) for k in CAM]; KF = [(k[0], Vector((k[3], 0, 0))) for k in CAM]


def sstep(a, b, x):
    u = min(1, max(0, (x - a) / (b - a)))
    return u * u * (3 - 2 * u)


def state(t):
    K.aim(cam, hermite(KL, t), hermite(KT, t))
    cam.data.lens = hermite(KF, t).x
    for o, t0, st, kind in SCHED:
        o.hide_render = t < t0
        if t < t0:
            continue
        u = min(1.0, (t - t0) / FLY)
        e = 1 - (1 - u) ** 3
        h = HOME[o.name]
        if kind == "slide":
            o.location = h + Vector((0, 11 * (1 - e), 0))
        else:
            o.location = h + Vector((0, 0, (2.2 + 0.6 * math.sin(hash(o.name) % 7)) * (1 - e)))
            o.scale = (0.35 + 0.65 * e,) * 3
            c = STAGES[st][2]
            k = 2.2 * (0.7 if u < 1 else max(0.0, 1 - (t - t0 - FLY) / 0.6))
            o.color = (c[0] * k, c[1] * k, c[2] * k, 1)
    K.set_reveal(-1.0 + 17.5 * sstep(WAVE[0], WAVE[1], t) ** 1.3 if t < WAVE[1] + 0.2 else 1000.0)
    s.view_settings.exposure = 1.5 * sstep(CEIL[0], CEIL[1] + 0.1, t)
    for o in K.coll("ground").objects:
        if o.name.startswith("cap"):
            o.hide_render = o.hide_render or t > CEIL[1]


tl = {"fps": FPS, "duration": DUR, "wave": WAVE, "ceiling": CEIL, "dive": 15.2,
      "stages": {st: {"label": v[3], "t0": v[0], "t1": v[1] + FLY, "color": v[2]} for st, v in STAGES.items()},
      "landings": sorted([(round(t0 + FLY, 3), st) for o, t0, st, k in SCHED if k == "drop"])}
json.dump(tl, open(os.path.join(OUT, "..", "timeline.json"), "w"))
print("parts", len(SCHED), "frames", int(DUR * FPS))

if "stills" in opt:
    frames = [int(float(x) * FPS) for x in opt["stills"].split(",")]
else:
    frames = range(0, int(DUR * FPS), int(opt.get("step", 1)))
for f in frames:
    path = os.path.join(OUT, f"f{f:04d}.png")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        continue
    state(f / FPS)
    s.render.filepath = path
    t = time.time(); bpy.ops.render.render(write_still=True)
    print("frame", f, round(time.time() - t, 1), "s", flush=True)
