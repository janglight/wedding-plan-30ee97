"""Stills: python3 build.py top dollhouse living kitchen master [--res 960x540] [--samples 48]"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy, house as K
a = sys.argv[1:]
opt = {a[i][2:]: a[i + 1] for i in range(len(a)) if a[i].startswith("--")}
shots = [x for i, x in enumerate(a) if not x.startswith("--") and not (i and a[i - 1].startswith("--"))] or ["dollhouse", "living"]
res = tuple(map(int, opt.get("res", "960x540").split("x")))
OUT = os.path.join(os.environ.get("BLUEPRINT_OUT", os.path.join(K.HERE, "..", "..", "blueprint-out")), "floor2")
os.makedirs(OUT, exist_ok=True)
s = K.build(samples=int(opt.get("samples", 48)), res=res)
print("parts", len(K.PARTS))
SH = {  # loc, target, lens, ceiling on?
    "top": ((5.25, 4.45, 30), (5.25, 4.46, 0), 50, False),
    "dollhouse": ((14.5, -7.0, 14.5), (5.6, 4.0, 0.2), 40, False),
    "living": ((7.75, 5.75, 1.62), (8.9, 0.9, 0.62), 17, True),
    "kitchen": ((7.5, 1.7, 1.45), (8.9, 5.9, 0.95), 18, True),
    "master": ((3.3, 4.15, 1.5), (1.5, 0.5, 0.75), 17, True),
    "dressing": ((4.25, 3.15, 1.5), (5.25, 0.2, 1.05), 15, True),
}
for n in shots:
    loc, tgt, lens, ceil = SH[n]
    K.camera(loc, tgt, lens)
    for o in K.coll("ceiling").objects:
        o.hide_render = not ceil
    for o in K.coll("ground").objects:
        o.hide_render = ceil
    s.view_settings.exposure = 1.6 if ceil else 0.0
    s.render.filepath = os.path.join(OUT, n + ".png")
    t = time.time(); bpy.ops.render.render(write_still=True); print(n, "rendered in", round(time.time() - t), "s")
