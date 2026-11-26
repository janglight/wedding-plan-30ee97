"""The counter over the film frames (stage name in its colour, parts placed), then the silent mp4.
    python3 hud.py --frames <dir> --timeline <json> --out silent.mp4"""
import argparse, bisect, glob, json, os, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFont
ap = argparse.ArgumentParser(); ap.add_argument("--frames"); ap.add_argument("--timeline"); ap.add_argument("--out")
a = ap.parse_args()
tl = json.load(open(a.timeline)); fps = tl["fps"]
land = [t for t, s in tl["landings"]]; total = len(land)
stages = sorted(tl["stages"].values(), key=lambda s: s["t0"])
tmp = tempfile.mkdtemp()
F = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"; FM = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
files = sorted(glob.glob(os.path.join(a.frames, "f*.png")))
for i, f in enumerate(files):
    t = int(os.path.basename(f)[1:5]) / fps
    im = Image.open(f).convert("RGB"); W, H = im.size; u = H / 540
    d = ImageDraw.Draw(im, "RGBA")
    big, small, mono = ImageFont.truetype(F, int(22 * u)), ImageFont.truetype(F, int(12 * u)), ImageFont.truetype(FM, int(13 * u))
    fade = max(0.0, min(1.0, (tl["dive"] + 1.2 - t) / 0.8)) * max(0.0, min(1.0, t / 0.6))
    A = int(255 * fade)
    if A > 0:
        n = bisect.bisect_right(land, t)
        cur = [s for s in stages if s["t0"] <= t <= s["t1"] + 0.3]
        x, y = int(28 * u), H - int(74 * u)
        d.rounded_rectangle((x - 12 * u, y - 10 * u, x + 250 * u, y + 56 * u), radius=int(8 * u), fill=(18, 18, 20, int(150 * fade)))
        if t < stages[0]["t0"]:
            label, col = "2F PLAN  ·  SCALE 1/100", (235, 235, 235)
        elif cur:
            label, col = cur[-1]["label"], tuple(int(60 + 195 * c) for c in cur[-1]["color"])
        elif t < tl["wave"][0]:
            label, col = "ASSEMBLED", (235, 235, 235)
        else:
            label, col = "MATERIALS", (240, 200, 150)
        d.text((x, y), label, font=big, fill=(*col, A))
        d.text((x, y + 30 * u), f"{n:04d} / {total:04d} parts", font=mono, fill=(230, 230, 230, A))
        d.rectangle((x + 150 * u, y + 36 * u, x + 236 * u, y + 40 * u), fill=(90, 90, 95, A))
        d.rectangle((x + 150 * u, y + 36 * u, x + 150 * u + 86 * u * n / total, y + 40 * u), fill=(*col, A))
    im.save(os.path.join(tmp, f"{i:04d}.png"))
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", os.path.join(tmp, "%04d.png"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17", a.out], check=True)
print("wrote", a.out, len(files), "frames")
