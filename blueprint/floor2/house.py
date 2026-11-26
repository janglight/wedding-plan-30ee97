"""2F unit (3 rooms, bath, LDK) read off the plan photo. Metres, x east, y north, origin at the SW corner of the
master bedroom, floor top at z=0. Every board, tile, wall block, frame and piece of furniture is its own object,
tagged with a build stage. Materials are procedural (no downloads) and carry a clay<->real 'reveal' for the film."""
import bpy, bmesh, math, os, random
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
H = 2.4
DOOR_H = 2.1
random.seed(7)
PARTS = []          # (object, stage)
STAGE = ["misc"]
FOCUS = (8.3, 2.0, 0.0)   # the reveal wave starts in the living room
PX = 94.0           # plan photo: pixels per metre
PX0, PY0 = 13.0, 1700.0   # pixel of the origin


def reset(samples=48, res=(960, 540)):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene
    s.render.engine = "CYCLES"
    s.cycles.device = "CPU"
    s.cycles.samples = samples
    s.cycles.use_adaptive_sampling = True
    s.cycles.adaptive_threshold = 0.03
    try:
        s.cycles.use_denoising = True
        s.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception as e:
        print("denoise", e)
    s.cycles.max_bounces = 6
    s.cycles.diffuse_bounces = 3
    s.cycles.glossy_bounces = 3
    s.cycles.transmission_bounces = 6
    s.cycles.transparent_max_bounces = 8
    s.cycles.caustics_reflective = False
    s.cycles.caustics_refractive = False
    s.cycles.sample_clamp_indirect = 8.0
    s.render.threads_mode = "AUTO"
    s.render.resolution_x, s.render.resolution_y = res
    s.render.resolution_percentage = 100
    s.render.image_settings.file_format = "PNG"
    s.view_settings.view_transform = "Khronos PBR Neutral"
    s.view_settings.exposure = 0.0
    for n in ("structure", "ceiling", "ground"):
        c = bpy.data.collections.new(n)
        s.collection.children.link(c)
    return s


def coll(n):
    return bpy.data.collections[n]


# ---------------------------------------------------------------- materials
def reveal_group():
    g = bpy.data.node_groups.get("Reveal")
    if g:
        return g
    g = bpy.data.node_groups.new("Reveal", "ShaderNodeTree")
    g.interface.new_socket("Fac", in_out="OUTPUT", socket_type="NodeSocketFloat")
    N, L = g.nodes, g.links
    out = N.new("NodeGroupOutput")
    geo = N.new("ShaderNodeNewGeometry")
    d = N.new("ShaderNodeVectorMath"); d.operation = "DISTANCE"
    d.inputs[1].default_value = FOCUS
    L.new(geo.outputs["Position"], d.inputs[0])
    nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 1.6
    L.new(geo.outputs["Position"], nz.inputs["Vector"])
    add = N.new("ShaderNodeMath"); add.operation = "ADD"
    L.new(d.outputs["Value"], add.inputs[0]); L.new(nz.outputs[0], add.inputs[1])
    r = N.new("ShaderNodeValue"); r.name = "R"; r.outputs[0].default_value = 1000.0
    mr = N.new("ShaderNodeMapRange")
    mr.inputs["To Min"].default_value = 1.0; mr.inputs["To Max"].default_value = 0.0
    sub = N.new("ShaderNodeMath"); sub.operation = "SUBTRACT"; sub.inputs[1].default_value = 0.6
    L.new(r.outputs[0], sub.inputs[0])
    L.new(add.outputs[0], mr.inputs["Value"])
    L.new(sub.outputs[0], mr.inputs["From Min"]); L.new(r.outputs[0], mr.inputs["From Max"])
    L.new(mr.outputs[0], out.inputs[0])
    return g


def set_reveal(radius):
    reveal_group().nodes["R"].outputs[0].default_value = radius


MATS = {}


def mat(name, color=(0.8, 0.8, 0.8), rough=0.5, metal=0.0, kind="plain", emit=0.0, ecol=None, color2=None, scale=1.0, reveal=True):
    """real shader mixed with white clay by the Reveal wave; clay glows with the object's colour (the stage flash)"""
    if name in MATS:
        return MATS[name]
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    N, L = m.node_tree.nodes, m.node_tree.links
    N.clear()
    out = N.new("ShaderNodeOutputMaterial")
    mix = N.new("ShaderNodeMixShader")
    rv = N.new("ShaderNodeGroup"); rv.node_tree = reveal_group()
    L.new(rv.outputs[0], mix.inputs[0])
    clay = N.new("ShaderNodeBsdfPrincipled")
    clay.inputs["Base Color"].default_value = (0.74, 0.73, 0.71, 1)
    clay.inputs["Roughness"].default_value = 0.75
    oi = N.new("ShaderNodeObjectInfo")
    L.new(oi.outputs["Color"], clay.inputs["Emission Color"])
    clay.inputs["Emission Strength"].default_value = 1.0
    L.new(clay.outputs[0], mix.inputs[1])
    c4 = (*color, 1)
    if kind == "glass":
        fr = N.new("ShaderNodeFresnel"); fr.inputs[0].default_value = 1.45
        tr = N.new("ShaderNodeBsdfTransparent"); tr.inputs[0].default_value = (0.93, 0.97, 0.96, 1)
        gl = N.new("ShaderNodeBsdfGlossy"); gl.inputs["Roughness"].default_value = 0.02
        real = N.new("ShaderNodeMixShader")
        gg = N.new("ShaderNodeNewGeometry")
        ff = N.new("ShaderNodeMath"); ff.operation = "SUBTRACT"; ff.use_clamp = True   # no reflection from inside the pane
        L.new(fr.outputs[0], ff.inputs[0]); L.new(gg.outputs["Backfacing"], ff.inputs[1])
        L.new(ff.outputs[0], real.inputs[0]); L.new(tr.outputs[0], real.inputs[1]); L.new(gl.outputs[0], real.inputs[2])
        clay.inputs["Alpha"].default_value = 0.35
    elif kind == "sheer":
        tr = N.new("ShaderNodeBsdfTransparent")
        tl = N.new("ShaderNodeBsdfTranslucent"); tl.inputs[0].default_value = c4
        df = N.new("ShaderNodeBsdfDiffuse"); df.inputs[0].default_value = c4
        a = N.new("ShaderNodeMixShader"); a.inputs[0].default_value = 0.5
        L.new(tl.outputs[0], a.inputs[1]); L.new(df.outputs[0], a.inputs[2])
        real = N.new("ShaderNodeMixShader"); real.inputs[0].default_value = 0.72
        L.new(tr.outputs[0], real.inputs[1]); L.new(a.outputs[0], real.inputs[2])
    else:
        real = N.new("ShaderNodeBsdfPrincipled")
        real.inputs["Base Color"].default_value = c4
        real.inputs["Roughness"].default_value = rough
        real.inputs["Metallic"].default_value = metal
        if emit:
            real.inputs["Emission Color"].default_value = (*(ecol or color), 1)
            real.inputs["Emission Strength"].default_value = emit
        tc = N.new("ShaderNodeTexCoord")
        if kind == "wood":
            mp = N.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (1.2 * scale, 22 * scale, 22 * scale)
            L.new(tc.outputs["Object"], mp.inputs[0])
            nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 3.0; nz.inputs["Detail"].default_value = 6
            L.new(mp.outputs[0], nz.inputs["Vector"])
            rnd = N.new("ShaderNodeMath"); rnd.operation = "MULTIPLY"; rnd.inputs[1].default_value = 0.55
            L.new(oi.outputs["Random"], rnd.inputs[0])
            sm = N.new("ShaderNodeMath"); sm.operation = "ADD"
            gm = N.new("ShaderNodeMath"); gm.operation = "MULTIPLY"; gm.inputs[1].default_value = 0.5
            L.new(nz.outputs[0], gm.inputs[0]); L.new(gm.outputs[0], sm.inputs[0]); L.new(rnd.outputs[0], sm.inputs[1])
            cr = N.new("ShaderNodeValToRGB")
            cr.color_ramp.elements[0].position = 0.15; cr.color_ramp.elements[0].color = (*(color2 or [c * 0.62 for c in color]), 1)
            cr.color_ramp.elements[1].position = 0.85; cr.color_ramp.elements[1].color = c4
            L.new(sm.outputs[0], cr.inputs[0]); L.new(cr.outputs[0], real.inputs["Base Color"])
            bp = N.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = 0.08
            L.new(nz.outputs[0], bp.inputs["Height"]); L.new(bp.outputs[0], real.inputs["Normal"])
        elif kind in ("fabric", "plaster", "stone"):
            nz = N.new("ShaderNodeTexNoise")
            nz.inputs["Scale"].default_value = {"fabric": 420.0, "plaster": 60.0, "stone": 9.0}[kind] * scale
            nz.inputs["Detail"].default_value = 5
            L.new(tc.outputs["Object"], nz.inputs["Vector"])
            bp = N.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = {"fabric": 0.35, "plaster": 0.06, "stone": 0.03}[kind]
            L.new(nz.outputs[0], bp.inputs["Height"]); L.new(bp.outputs[0], real.inputs["Normal"])
            if kind in ("stone", "fabric"):
                cr = N.new("ShaderNodeValToRGB")
                k = 0.86 if kind == "stone" else 0.9
                cr.color_ramp.elements[0].position = 0.3; cr.color_ramp.elements[0].color = (*(color2 or [c * k for c in color]), 1)
                cr.color_ramp.elements[1].position = 0.7; cr.color_ramp.elements[1].color = c4
                n2 = N.new("ShaderNodeTexNoise"); n2.inputs["Scale"].default_value = (2.5 if kind == "stone" else 30) * scale
                n2.inputs["Detail"].default_value = 8
                L.new(tc.outputs["Object"], n2.inputs["Vector"])
                L.new(n2.outputs[0], cr.inputs[0]); L.new(cr.outputs[0], real.inputs["Base Color"])
        elif kind == "tile":   # per-object shade
            rr = N.new("ShaderNodeMapRange"); rr.inputs["To Min"].default_value = 0.9; rr.inputs["To Max"].default_value = 1.05
            L.new(oi.outputs["Random"], rr.inputs[0])
            mm = N.new("ShaderNodeVectorMath"); mm.operation = "SCALE"; mm.inputs[0].default_value = color
            L.new(rr.outputs[0], mm.inputs["Scale"]); L.new(mm.outputs[0], real.inputs["Base Color"])
        elif kind == "image":
            im = N.new("ShaderNodeTexImage"); im.image = bpy.data.images.load(os.path.join(HERE, "plan.jpg"))
            im.extension = "EXTEND"
            L.new(tc.outputs["UV"], im.inputs[0]); L.new(im.outputs[0], real.inputs["Base Color"])
    L.new(real.outputs[0], mix.inputs[2])
    L.new((mix if reveal else real).outputs[0], out.inputs[0])
    MATS[name] = m
    return m


def M(n):
    return MATS[n]


def materials():
    mat("wall", (0.86, 0.84, 0.80), 0.9, kind="plaster")
    mat("cut", (0.16, 0.16, 0.17), 0.8)
    mat("slab", (0.55, 0.54, 0.52), 0.9, kind="plaster")
    mat("oak", (0.50, 0.40, 0.31), 0.42, kind="wood", color2=(0.27, 0.21, 0.165))
    mat("oak2", (0.62, 0.42, 0.24), 0.4, kind="wood", color2=(0.42, 0.27, 0.14), scale=1.4)
    mat("walnut_dark", (0.10, 0.06, 0.04), 0.5)
    mat("walnut", (0.33, 0.19, 0.11), 0.35, kind="wood", color2=(0.17, 0.09, 0.05), scale=1.4)
    mat("ash", (0.78, 0.66, 0.48), 0.4, kind="wood", color2=(0.62, 0.50, 0.34), scale=1.4)
    mat("tile", (0.74, 0.73, 0.70), 0.25, kind="tile")
    mat("tile_dark", (0.5, 0.5, 0.5), 0.35, kind="tile")
    mat("tile_wall", (0.88, 0.89, 0.88), 0.15, kind="tile")
    mat("grout", (0.30, 0.30, 0.30), 0.9)
    mat("white", (0.9, 0.9, 0.89), 0.35)
    mat("frame", (0.42, 0.33, 0.25), 0.45, kind="wood", color2=(0.33, 0.25, 0.18), scale=1.4)
    mat("trim", (0.30, 0.22, 0.16), 0.45)
    mat("steel", (0.18, 0.19, 0.2), 0.35, metal=0.9)
    mat("chrome", (0.8, 0.8, 0.8), 0.15, metal=1.0)
    mat("black", (0.02, 0.02, 0.022), 0.25)
    mat("glass", kind="glass")
    mat("marble", (0.88, 0.87, 0.84), 0.12, kind="stone", color2=(0.62, 0.61, 0.6))
    mat("boucle", (0.90, 0.86, 0.78), 1.0, kind="fabric", scale=0.35)
    mat("cream", (0.90, 0.86, 0.78), 0.6)
    mat("jute", (0.76, 0.68, 0.55), 1.0, kind="fabric", scale=0.12)
    mat("sheet", (0.55, 0.58, 0.62), 0.9, kind="fabric")
    mat("pink", (0.80, 0.60, 0.61), 0.95, kind="fabric", scale=0.5)
    mat("silver", (0.62, 0.63, 0.64), 0.32, metal=0.85)
    mat("kitchen_grey", (0.42, 0.44, 0.45), 0.4)
    mat("ribbed", (0.75, 0.8, 0.8), 0.3)
    mat("art", (0.03, 0.035, 0.06), 0.25, emit=0.06, ecol=(0.25, 0.3, 0.55))
    mat("leaf2", (0.16, 0.30, 0.10), 0.5)
    mat("panel", (1, 1, 1), 0.5, emit=6.0, ecol=(1.0, 0.95, 0.88))
    mat("linen", (0.88, 0.86, 0.80), 0.95, kind="fabric")
    mat("sage", (0.42, 0.50, 0.40), 0.95, kind="fabric")
    mat("terracotta", (0.66, 0.33, 0.22), 0.95, kind="fabric")
    mat("navy", (0.10, 0.14, 0.24), 0.95, kind="fabric")
    mat("rug", (0.80, 0.76, 0.68), 1.0, kind="fabric", scale=0.25)
    mat("sheer", (0.95, 0.94, 0.9), kind="sheer")
    mat("ceramic", (0.93, 0.93, 0.92), 0.08)
    mat("pot", (0.75, 0.72, 0.66), 0.6, kind="stone", scale=6)
    mat("leaf", (0.07, 0.22, 0.06), 0.4)
    mat("brass", (0.8, 0.58, 0.25), 0.25, metal=1.0)
    mat("lamp", (1.0, 0.85, 0.65), 0.5, emit=14.0, ecol=(1.0, 0.72, 0.42))
    mat("downlight", (1.0, 0.9, 0.8), 0.5, emit=40.0, ecol=(1.0, 0.82, 0.62))
    mat("screen", (0.01, 0.01, 0.012), 0.08)
    mat("books", (0.5, 0.3, 0.22), 0.7, kind="tile")
    mat("paper", kind="image", rough=0.9, reveal=False)
    mat("desk", (0.16, 0.13, 0.11), 0.5, kind="wood", scale=0.3, reveal=False)


# ---------------------------------------------------------------- geometry
def _finish(name, bm, m, stage=None, col=None, smooth=False):
    me = bpy.data.meshes.new(name)
    c = sum((v.co for v in bm.verts), Vector()) / max(1, len(bm.verts))
    bmesh.ops.translate(bm, verts=bm.verts, vec=-c)
    if smooth:
        for f in bm.faces:
            f.smooth = True
    bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me)
    o.location = c
    o.color = (0, 0, 0, 1)
    me.materials.append(m if not isinstance(m, str) else M(m))
    (coll(col) if col else coll("structure")).objects.link(o)
    o["home"] = tuple(c)
    PARTS.append((o, stage or STAGE[0]))
    return o


def box(name, x0, x1, y0, y1, z0, z1, m, bevel=0.0, seg=1, rot=None, stage=None, col=None, smooth=False):
    """axis box; rot=(pivot_xy, degrees) turns it about a vertical axis"""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, verts=bm.verts, vec=(abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)))
    bmesh.ops.translate(bm, verts=bm.verts, vec=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    if bevel:
        bmesh.ops.bevel(bm, geom=bm.edges[:], offset=bevel, segments=seg, profile=0.5, affect="EDGES")
    if rot:
        (px, py), deg = rot
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(px, py, 0), matrix=Matrix.Rotation(math.radians(deg), 3, "Z"))
    return _finish(name, bm, m, stage, col, smooth or seg > 2)


def cyl(name, x, y, r, z0, z1, m, verts=24, r2=None, stage=None, col=None, smooth=True):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts, radius1=r, radius2=r if r2 is None else r2, depth=z1 - z0)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(x, y, (z0 + z1) / 2))
    o = _finish(name, bm, m, stage, col)
    for p in o.data.polygons:
        p.use_smooth = len(p.vertices) == 4 and smooth
    return o


def ball(name, x, y, z, r, m, squash=(1, 1, 1), stage=None):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=r)
    bmesh.ops.scale(bm, verts=bm.verts, vec=squash)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(x, y, z))
    return _finish(name, bm, m, stage, smooth=True)


# ---------------------------------------------------------------- the plan, in numbers
# walls: axis ('x' runs east-west at y=c, 'y' runs north-south at x=c), c, from, to, thickness, openings
# opening: (kind, from, to, sill, head[, hinge_end, swing_side])
WALLS = [
    ("x", 0.0, 0.0, 10.5, 0.2, [("win", 1.0, 2.6, 0.9, 2.15), ("win", 4.3, 5.9, 0.9, 2.15), ("win", 7.4, 9.8, 0.12, 2.2)]),   # south
    ("y", 10.5, 0.0, 8.9, 0.2, [("win", 3.75, 5.45, 0.95, 2.15), ("win", 7.3, 8.1, 1.2, 2.0)]),  # east
    ("y", 0.0, 0.0, 4.5, 0.2, []),                                             # west of master
    ("x", 4.5, 0.0, 3.1, 0.2, []),                                             # neighbour's bath above master
    ("y", 3.1, 4.5, 8.9, 0.2, []),                                             # neighbour's kitchen
    ("x", 8.9, 3.1, 10.5, 0.2, [("entry", 3.75, 4.7, 0, DOOR_H)]),             # stair hall
    ("y", 3.6, 0.0, 4.5, 0.12, [("door", 3.55, 4.35, 0, DOOR_H, 1, -1)]),      # master | room, nook
    ("x", 3.4, 3.6, 6.6, 0.12, [("door", 3.78, 4.6, 0, DOOR_H, 0, -1)]),       # room north
    ("y", 6.6, 0.0, 3.4, 0.12, []),                                            # room | living
    ("x", 4.5, 3.1, 4.9, 0.12, []),                                            # bath south
    ("y", 4.9, 4.5, 8.9, 0.12, [("door", 4.7, 5.45, 0, DOOR_H, 0, -1), ("open", 7.15, 8.8, 0, H)]),  # bath, entrance | hall
    ("x", 7.0, 3.1, 4.9, 0.12, []),                                            # bath | entrance
    ("y", 6.4, 6.5, 8.9, 0.12, [("door", 6.62, 7.4, 0, DOOR_H, 0, 1)]),        # small room west
    ("x", 6.5, 6.4, 10.5, 0.12, [("door", 9.62, 10.3, 0, DOOR_H, 0, 1)]),      # small room, utility south
    ("y", 9.4, 6.5, 8.9, 0.12, []),                                            # small room | utility
]
WOOD = [(0, 3.6, 0, 4.5), (3.6, 6.6, 0, 3.4), (6.6, 10.5, 0, 3.4), (3.6, 10.5, 3.4, 4.5), (4.9, 10.5, 4.5, 6.5),
        (4.9, 6.4, 6.5, 8.9), (6.4, 9.4, 6.5, 8.9)]
TILED = [("bath", 3.1, 4.9, 4.5, 7.0, 0.3, "tile"), ("entry", 3.1, 4.9, 7.0, 8.9, 0.45, "tile_dark"),
         ("utility", 9.4, 10.5, 6.5, 8.9, 0.3, "tile")]
OUTLINE = [(0, 0), (10.5, 0), (10.5, 8.9), (3.1, 8.9), (3.1, 4.5), (0, 4.5)]


def W(axis, c, a0, a1, lo, hi, z0, z1):
    """a box in wall coordinates: a along the wall, lo/hi across it"""
    return (a0, a1, c + lo, c + hi, z0, z1) if axis == "x" else (c + lo, c + hi, a0, a1, z0, z1)


CAPZ = [0.0]


def wall_run(axis, c, a0, a1, t, z0, z1, tag):
    """a solid stretch of wall as blocks (each its own part), with a dark cut cap when it reaches the top"""
    n = max(1, round((a1 - a0) / 0.7))
    courses = max(1, round((z1 - z0) / 0.6))
    for i in range(n):
        for k in range(courses):
            b0, b1 = a0 + (a1 - a0) * i / n, a0 + (a1 - a0) * (i + 1) / n
            c0, c1 = z0 + (z1 - z0) * k / courses, z0 + (z1 - z0) * (k + 1) / courses
            box(f"wall_{tag}", *W(axis, c, b0, b1, -t / 2, t / 2, c0, c1), "wall", stage="walls")
    if z0 == 0 and a1 - a0 > 0.25:
        box(f"baseboard_{tag}", *W(axis, c, a0 + 0.003, a1 - 0.003, -t / 2 - 0.008, t / 2 + 0.008, 0.001, 0.07), "trim", stage="frames")
    if z1 >= H - 1e-6:
        box(f"crown_{tag}", *W(axis, c, a0 + 0.003, a1 - 0.003, -t / 2 - 0.02, t / 2 + 0.02, H - 0.06, H - 0.001), "trim", stage="ceiling", col="ceiling")
        box(f"cap_{tag}", *W(axis, c, a0, a1, -t / 2, t / 2, H, H + 0.003 + CAPZ[0]), "cut", stage="walls", col="ground")


def window(axis, c, a0, a1, sill, head, t, tag):
    f = 0.05
    for nm, b in (("jl", (a0, a0 + f, sill, head)), ("jr", (a1 - f, a1, sill, head)), ("hd", (a0, a1, head - f, head)),
                  ("sl", (a0, a1, sill, sill + f)), ("mu", ((a0 + a1) / 2 - 0.025, (a0 + a1) / 2 + 0.025, sill + f, head - f))):
        box(f"win_{tag}_{nm}", *W(axis, c, b[0], b[1], -0.05, 0.05, b[2], b[3]), "frame", bevel=0.004, stage="frames")
    mid = (a0 + a1) / 2
    box(f"glass_{tag}_a", *W(axis, c, a0 + f, mid, -0.012, -0.004, sill + f, head - f), "glass", stage="glass")
    box(f"glass_{tag}_b", *W(axis, c, mid, a1 - f, 0.004, 0.012, sill + f, head - f), "glass", stage="glass")
    box(f"sillboard_{tag}", *W(axis, c, a0 - 0.03, a1 + 0.03, -t / 2 - 0.02, t / 2 + 0.02, sill - 0.03, sill), "frame", bevel=0.004, stage="frames")


def door(axis, c, a0, a1, head, t, tag, hinge_end=0, side=1, entry=False, angle=78):
    f = 0.04
    d = t / 2 + 0.01
    m = "steel" if entry else "frame"
    box(f"door_{tag}_jl", *W(axis, c, a0, a0 + f, -d, d, 0, head), m, bevel=0.003, stage="frames")
    box(f"door_{tag}_jr", *W(axis, c, a1 - f, a1, -d, d, 0, head), m, bevel=0.003, stage="frames")
    box(f"door_{tag}_hd", *W(axis, c, a0, a1, -d, d, head - f, head), m, bevel=0.003, stage="frames")
    h = a0 + f if hinge_end == 0 else a1 - f
    piv = (h, c + side * 0.02) if axis == "x" else (c + side * 0.02, h)
    ang = 0 if entry else angle
    # leaf lies in the opening, then turns about the hinge into the room on `side`
    sgn = side * (1 if hinge_end == 0 else -1) * (1 if axis == "x" else -1)
    leaf = box(f"door_{tag}_leaf", *W(axis, c, a0 + f, a1 - f, side * 0.0, side * 0.04, 0.01, head - f), "steel" if entry else "frame",
               bevel=0.003, rot=(piv, sgn * ang), stage="frames")
    # lever handle
    mid = (a1 - f - 0.08) if hinge_end == 0 else (a0 + f + 0.08)
    box(f"door_{tag}_handle", *W(axis, c, mid - 0.06, mid + 0.06, side * 0.04, side * 0.09, 0.98, 1.0), "chrome",
        rot=(piv, sgn * ang), stage="frames")
    return leaf


def build_walls():
    for wi, (axis, c, a0, a1, t, ops) in enumerate(WALLS):
        e0, e1 = a0 - t / 2 + 0.002, a1 + t / 2 - 0.002      # run into the corners, never flush with the crossing wall
        CAPZ[0] = wi * 0.0004
        cur = e0
        for oi, op in enumerate(sorted(ops, key=lambda o: o[1])):
            kind, o0, o1, sill, head = op[:5]
            tag = f"{wi}_{oi}"
            if o0 > cur:
                wall_run(axis, c, cur, o0, t, 0, H, tag + "a")
            if kind == "win":
                wall_run(axis, c, o0, o1, t, 0, sill, tag + "s")
                wall_run(axis, c, o0, o1, t, head, H, tag + "h")
                window(axis, c, o0, o1, sill, head, t, tag)
            elif kind in ("door", "entry"):
                wall_run(axis, c, o0, o1, t, head, H, tag + "h")
                door(axis, c, o0, o1, head, t, tag, *(op[5:7] if len(op) > 5 else (0, 1)), entry=kind == "entry")
            cur = o1
        if cur < e1:
            wall_run(axis, c, cur, e1, t, 0, H, f"{wi}_z")


def build_floor():
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, -0.07)) for x, y in OUTLINE]
    f = bm.faces.new(vs)
    r = bmesh.ops.extrude_face_region(bm, geom=[f])
    bmesh.ops.translate(bm, verts=[v for v in r["geom"] if isinstance(v, bmesh.types.BMVert)], vec=(0, 0, 0.02))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    _finish("slab", bm, "slab", "slab")
    # oak boards, laid east-west, staggered
    bw, bl = 0.19, 1.6
    row = 0
    y = 0.0
    while y < 8.9:
        x = -random.choice((0.3, 0.7, 1.1, 1.45))
        while x < 10.5:
            for (x0, x1, y0, y1) in WOOD:
                ax0, ax1, ay0, ay1 = max(x, x0), min(x + bl, x1), max(y, y0), min(y + bw, y1)
                if ax1 - ax0 > 0.02 and ay1 - ay0 > 0.02:
                    box("board", ax0 + 0.001, ax1 - 0.001, ay0 + 0.001, ay1 - 0.001, -0.049, 0.0, "oak", stage="floor")
            x += bl
        y += bw
        row += 1
    for name, x0, x1, y0, y1, s, m in TILED:
        z = -0.03 if name == "entry" else -0.004
        box(f"grout_{name}", x0, x1, y0, y1, -0.049, z - 0.004, "grout", stage="floor")
        nx, ny = max(1, round((x1 - x0) / s)), max(1, round((y1 - y0) / s))
        for i in range(nx):
            for j in range(ny):
                box(f"tile_{name}", x0 + (x1 - x0) * i / nx + 0.002, x0 + (x1 - x0) * (i + 1) / nx - 0.002,
                    y0 + (y1 - y0) * j / ny + 0.002, y0 + (y1 - y0) * (j + 1) / ny - 0.002, z - 0.012, z, m, stage="floor")


def build_ceiling():
    for i, (x0, x1, y0, y1) in enumerate(WOOD + [t[1:5] for t in TILED]):
        box(f"ceiling_{i}", x0, x1, y0, y1, H, H + 0.1, "white", stage="ceiling", col="ceiling")
    for (x, y) in [(7.6, 1.0), (9.4, 1.0), (7.6, 2.6), (9.4, 2.6), (7.4, 5.3), (9.6, 5.3), (5.65, 4.0), (5.65, 5.6), (5.65, 7.6),
                   (1.8, 1.2), (1.8, 3.2), (5.1, 1.7), (7.9, 7.7), (4.0, 5.7), (4.0, 7.9)]:
        cyl("downlight", x, y, 0.055, H - 0.012, H - 0.002, "downlight", stage="lights", col="ceiling", smooth=False)


# ---------------------------------------------------------------- furniture
def curtain(axis, c, a0, a1, z0=0.03, z1=2.32, name="curtain"):
    bm = bmesh.new()
    n = int((a1 - a0) / 0.02)
    cols = []
    for i in range(n + 1):
        a = a0 + (a1 - a0) * i / n
        d = 0.035 * math.sin(a * 42) + 0.01 * math.sin(a * 17)
        p = (a, c + d) if axis == "x" else (c + d, a)
        cols.append((bm.verts.new((*p, z0)), bm.verts.new((*p, z1))))
    for i in range(n):
        bm.faces.new((cols[i][0], cols[i + 1][0], cols[i + 1][1], cols[i][1]))
    _finish(name, bm, "sheer", "decor", smooth=True)


def rod(name, a, b, r, m, verts=10, r2=None, stage=None, col=None):
    """a round bar from point a to point b"""
    a, b = Vector(a), Vector(b)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts, radius1=r, radius2=r if r2 is None else r2, depth=(b - a).length)
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=(b - a).to_track_quat("Z", "Y").to_matrix())
    bmesh.ops.translate(bm, verts=bm.verts, vec=(a + b) / 2)
    o = _finish(name, bm, m, stage, col)
    for p in o.data.polygons:
        p.use_smooth = len(p.vertices) == 4
    return o


def sofa(cx, cy, w=1.9, d=0.95, yaw=-90, m="boucle"):
    """rounded two-seater; built with its back on +x, then turned by yaw about its centre"""
    r = ((cx, cy), yaw)
    x0, x1, y0, y1 = cx - d / 2, cx + d / 2, cy - w / 2, cy + w / 2
    box("sofa_base", x0, x1 - 0.05, y0 + 0.05, y1 - 0.05, 0.03, 0.26, m, 0.08, 4, rot=r)
    box("sofa_back", x1 - 0.28, x1, y0 + 0.1, y1 - 0.1, 0.2, 0.78, m, 0.12, 5, rot=r)
    box("sofa_arm_a", x0 + 0.05, x1 - 0.05, y0, y0 + 0.27, 0.05, 0.6, m, 0.12, 5, rot=r)
    box("sofa_arm_b", x0 + 0.05, x1 - 0.05, y1 - 0.27, y1, 0.05, 0.6, m, 0.12, 5, rot=r)
    L = (w - 0.54) / 2
    for i in range(2):
        a = y0 + 0.27 + L * i
        box(f"sofa_seat{i}", x0, x1 - 0.26, a + 0.005, a + L - 0.005, 0.24, 0.47, m, 0.09, 5, rot=r)
        box(f"sofa_cushion{i}", x1 - 0.5, x1 - 0.22, a + 0.01, a + L - 0.01, 0.45, 0.9, m, 0.11, 5, rot=r)
        box(f"sofa_pillow{i}", x1 - 0.62, x1 - 0.48, a + 0.1, a + L - 0.12, 0.47, 0.72, "linen", 0.06, 4, rot=r)


def chair(x, y, yaw):
    """walnut frame, curved back rail, round cream seat (the dining set in the photo)"""
    c, s_ = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    P = lambda dx, dy, z: (x + dx * c - dy * s_, y + dx * s_ + dy * c, z)
    for i, (dx, dy) in enumerate(((-0.19, -0.18), (0.19, -0.18))):
        rod(f"chair_leg{i}", P(dx, dy, 0), P(dx * 0.92, dy * 0.92, 0.43), 0.014, "walnut", r2=0.019)
    for i, dx in enumerate((-0.2, 0.2)):
        rod(f"chair_post{i}", P(dx, 0.2, 0), P(dx * 0.98, 0.23, 0.78), 0.014, "walnut", r2=0.018)
    rod("chair_stretcher", P(-0.19, 0.0, 0.2), P(0.19, 0.0, 0.2), 0.009, "walnut")
    box("chair_frame", x - 0.21, x + 0.21, y - 0.2, y + 0.22, 0.4, 0.43, "walnut", 0.008, rot=((x, y), yaw))
    for k in range(3):   # the bent back rail, in three facets
        a = (k - 1) * 0.16
        box("chair_back", x + a - 0.085, x + a + 0.085, y + 0.215, y + 0.24, 0.66, 0.79, "walnut", 0.008, 2,
            rot=((x + a, y + 0.23), -(k - 1) * 14))
        o = PARTS[-1][0]
        p = Vector(o["home"]) - Vector((x, y, 0))
        q = Matrix.Rotation(math.radians(yaw), 3, "Z") @ p + Vector((x, y, 0))
        o.location = q; o.rotation_euler = (0, 0, math.radians(yaw)); o["home"] = tuple(q)
    cyl("chair_seat", x, y + 0.01, 0.215, 0.43, 0.49, "cream", verts=28)


def dining(x0, x1, y0, y1):
    box("dining_top", x0, x1, y0, y1, 0.715, 0.75, "walnut", 0.018, 3)
    box("dining_apron", x0 + 0.12, x1 - 0.12, y0 + 0.1, y1 - 0.1, 0.65, 0.715, "walnut")
    for i, (x, y) in enumerate(((x0 + 0.13, y0 + 0.11), (x1 - 0.13, y0 + 0.11), (x0 + 0.13, y1 - 0.11), (x1 - 0.13, y1 - 0.11))):
        dx, dy = (-0.04 if x < (x0 + x1) / 2 else 0.04), (-0.03 if y < (y0 + y1) / 2 else 0.03)
        rod(f"dining_leg{i}", (x + dx, y + dy, 0), (x, y, 0.715), 0.018, "walnut", r2=0.03)
    S = STAGE
    S[0] = "decor"
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    cyl("dining_vase", cx, cy, 0.055, 0.75, 0.86, "ceramic", r2=0.03)
    for i in range(9):
        o = ball("sprig", 0, 0, 0, 0.035, "leaf2", squash=(1, 0.6, 0.2))
        o.location = (cx + 0.08 * math.cos(i * 2.1), cy + 0.08 * math.sin(i * 2.1), 0.92 + 0.025 * i)
        o.rotation_euler = (0.4, 0.5, i * 2.1); o["home"] = tuple(o.location)
    for i, (mx, my) in enumerate(((cx - 0.35, cy + 0.12), (cx + 0.38, cy - 0.15))):
        cyl(f"coaster{i}", mx, my, 0.055, 0.75, 0.757, "oak2", smooth=False)
        cyl(f"mug{i}", mx, my, 0.04, 0.757, 0.84, "ceramic")
        box(f"mug_handle{i}", mx + 0.04, mx + 0.062, my - 0.006, my + 0.006, 0.775, 0.825, "ceramic")
    S[0] = "furniture"


def master_bed():
    """the bed in the photo: head under the south window, one wide walnut headboard wall with a side unit each end"""
    box("bed_headwall", 0.45, 3.2, 0.11, 0.17, 0.0, 0.88, "walnut", 0.006)
    box("bed_side_a", 0.45, 0.93, 0.17, 0.6, 0.0, 0.42, "walnut", 0.006)
    box("bed_side_b", 2.72, 3.2, 0.17, 0.6, 0.0, 0.42, "walnut", 0.006)
    box("bed_side_gap", 0.47, 0.91, 0.598, 0.602, 0.2, 0.21, "black")
    box("bed_platform", 0.95, 2.7, 0.17, 2.3, 0.0, 0.3, "walnut", 0.008)
    box("mattress", 0.98, 2.67, 0.2, 2.26, 0.3, 0.55, "sheet", 0.06, 4)
    box("duvet", 0.93, 2.3, 0.55, 2.3, 0.4, 0.6, "pink", 0.07, 4, rot=((1.6, 1.4), -9))
    box("pillow", 1.05, 1.75, 0.24, 0.62, 0.55, 0.68, "linen", 0.06, 4)
    cyl("bolster", 0, 0, 0.11, 0, 0.9, "white", verts=20)
    o = PARTS[-1][0]; o.rotation_euler = (math.radians(90), 0, math.radians(20)); o.location = (2.5, 0.75, 0.66); o["home"] = tuple(o.location)
    for i, x in enumerate((0.6, 3.05)):
        box(f"bed_switch{i}", x - 0.07, x + 0.07, 0.165, 0.175, 0.62, 0.7, "black")


def rack(x0, x1, y0, y1, bays, tag, drawers=False):
    """chrome system hanger along y: four posts a bay, white shelves top and bottom, a rail under the top shelf"""
    L = (y1 - y0) / bays
    for b in range(bays + 1):
        y = y0 + L * b
        for x in (x0 + 0.02, x1 - 0.02):
            cyl(f"rack_post_{tag}", x, y, 0.011, 0.0, 2.1, "chrome", verts=8)
    for b in range(bays):
        a0, a1 = y0 + L * b + 0.012, y0 + L * (b + 1) - 0.012
        box(f"rack_shelf_{tag}", x0, x1, a0, a1, 2.0, 2.02, "white")
        box(f"rack_shelf_{tag}", x0, x1, a0, a1, 0.16, 0.18, "white")
        rod(f"rack_rail_{tag}", ((x0 + x1) / 2, a0, 1.9), ((x0 + x1) / 2, a1, 1.9), 0.009, "chrome", verts=8)
        if b % 2 == 0:
            box(f"rack_shelf_{tag}", x0, x1, a0, a1, 0.95, 0.97, "white")
            rod(f"rack_rail_{tag}", ((x0 + x1) / 2, a0, 0.88), ((x0 + x1) / 2, a1, 0.88), 0.009, "chrome", verts=8)
        else:
            for z in (0.6, 1.05, 1.5):
                box(f"rack_shelf_{tag}", x0, x1, a0, a1, z, z + 0.02, "white")
        rod(f"rack_brace_{tag}", (x1 - 0.02 if x0 > 5 else x0 + 0.02, a0, 0.3), (x1 - 0.02 if x0 > 5 else x0 + 0.02, a1, 0.8), 0.004, "chrome", verts=6)


def furnish():
    S = STAGE
    # ---- living: sofa before the sheer south window, TV on an easel by the west wall, cabinets on the east wall
    S[0] = "furniture"
    sofa(9.88, 1.25, yaw=0)   # across the room from the TV
    box("aircon", 6.95, 7.3, 0.22, 0.55, 0.0, 1.85, "silver", 0.03, 3)
    box("aircon_vent", 7.0, 7.25, 0.552, 0.556, 1.35, 1.75, "steel")
    # TV on a tripod easel
    tvr = ((7.02, 1.25), 0)
    box("tv", 6.98, 7.01, 0.6, 1.9, 0.82, 1.56, "screen", 0.004, rot=tvr)
    box("tv_art", 7.01, 7.013, 0.63, 1.87, 0.85, 1.53, "art", rot=tvr)
    rod("easel_leg_a", (7.2, 0.8, 0), (6.95, 1.2, 1.2), 0.016, "oak2", r2=0.012)
    rod("easel_leg_b", (7.2, 1.7, 0), (6.95, 1.3, 1.2), 0.016, "oak2", r2=0.012)
    rod("easel_leg_c", (6.75, 1.25, 0), (6.93, 1.25, 1.2), 0.016, "oak2", r2=0.012)
    # sideboard with the oven and rice cooker, then the hutch
    S[0] = "builtin"
    # east wall, as in the reference: sofa, then the hutch, then the oven sideboard beside the dining table
    DY = 0.73
    hb = lambda n, x0, x1, y0, y1, *a, **k: box(n, x0, x1, y0 + DY, y1 + DY, *a, **k)
    hc = lambda n, x, y, *a, **k: cyl(n, x, y + DY, *a, **k)
    hb("sideboard", 9.98, 10.38, 2.55, 3.6, 0.04, 0.92, "walnut", 0.006)
    hb("sideboard_niche", 9.975, 10.3, 2.6, 3.55, 0.5, 0.86, "walnut_dark")
    hb("sideboard_div", 9.975, 10.3, 3.06, 3.09, 0.5, 0.86, "walnut")
    hb("oven", 10.0, 10.3, 3.12, 3.52, 0.5, 0.74, "cream", 0.02, 3)
    hb("oven_window", 9.996, 10.0, 3.16, 3.4, 0.54, 0.7, "screen")
    hb("rice_cooker", 10.02, 10.28, 2.66, 2.98, 0.5, 0.72, "white", 0.06, 4)
    for i in range(2):
        hb("sideboard_drawer", 9.972, 9.98, 2.57 + 0.52 * i, 3.07 + 0.52 * i, 0.08, 0.47, "walnut", 0.003)
    hb("hutch_base", 9.98, 10.38, 1.55, 2.47, 0.12, 0.95, "walnut", 0.006)
    for i in range(2):
        hb("hutch_glass", 9.972, 9.98, 1.6 + 0.43 * i, 1.99 + 0.43 * i, 0.18, 0.72, "ribbed")
        hb("hutch_drawer", 9.972, 9.98, 1.58 + 0.44 * i, 2.0 + 0.44 * i, 0.76, 0.92, "walnut", 0.003)
    for i, y in enumerate((1.6, 2.42)):
        hc(f"hutch_foot{i}", 10.02, y, 0.015, 0, 0.12, "black", verts=8)
    hb("hutch_side_a", 10.1, 10.38, 1.55, 1.58, 0.95, 1.95, "walnut"); hb("hutch_side_b", 10.1, 10.38, 2.44, 2.47, 0.95, 1.95, "walnut")
    for z in (1.42, 1.9):
        hb("hutch_shelf", 10.1, 10.38, 1.58, 2.44, z, z + 0.025, "walnut")
    S[0] = "decor"
    hc("jug", 10.2, 1.78, 0.06, 0.95, 1.16, "ceramic", r2=0.035); hc("dish", 10.2, 2.2, 0.05, 0.95, 0.99, "ceramic", r2=0.12)
    for i in range(3):
        hc("plate", 10.24, 1.85, 0.11, 1.445 + 0.012 * i, 1.455 + 0.012 * i, "ceramic")
    hc("cup_a", 10.22, 2.15, 0.04, 1.445, 1.53, "ceramic"); hc("cup_b", 10.22, 2.3, 0.04, 1.445, 1.53, "ceramic")
    hc("top_vase", 10.24, 1.8, 0.05, 1.925, 2.06, "ceramic", r2=0.025)
    hc("top_pot", 10.24, 2.25, 0.06, 1.925, 2.03, "pot", r2=0.075)
    for i in range(14):
        o = ball("ivy", 0, 0, 0, 0.05, "leaf2", squash=(1, 0.7, 0.2))
        t = i / 13
        o.location = (10.2 - 0.08 * math.sin(i * 2.3), 2.25 + DY + 0.14 * math.cos(i * 1.9) + 0.12 * t, 2.1 - 0.75 * t ** 1.5 * (i % 2))
        o.rotation_euler = (0.5, 0.4, i * 2.3); o["home"] = tuple(o.location)
    hc("side_vase", 10.18, 2.75, 0.07, 0.92, 1.08, "pot", r2=0.045)
    for i in range(7):
        o = ball("twig", 0, 0, 0, 0.04, "leaf2", squash=(1, 0.6, 0.2))
        o.location = (10.18 + 0.1 * math.cos(i * 2.2), 2.75 + DY + 0.12 * math.sin(i * 2.2), 1.15 + 0.035 * i)
        o.rotation_euler = (0.4, 0.5, i * 2.2); o["home"] = tuple(o.location)
    ball("glow_lamp", 10.18, 3.0 + DY, 1.0, 0.075, "lamp", stage="lights")
    hc("glow_lamp_base", 10.18, 3.0, 0.045, 0.92, 0.935, "oak2")
    curtain("x", 0.2, 7.35, 9.95, name="curtain_south")
    # ---- dining (the walnut set in the photo) on a jute rug
    S[0] = "furniture"
    box("rug_dining", 7.2, 9.7, 3.45, 5.3, 0.0, 0.014, "jute", 0.004)
    dining(7.7, 9.2, 3.95, 4.75)
    for (x, y, yaw) in ((8.08, 3.72, 180), (8.82, 3.72, 180), (8.08, 4.98, 0), (8.82, 4.98, 0)):
        chair(x, y, yaw)
    # ---- kitchen (grey fronts, white counter, as in the photo)
    S[0] = "builtin"
    n = 4
    for i in range(n):
        x0, x1 = 7.36 + (9.52 - 7.36) * i / n, 7.36 + (9.52 - 7.36) * (i + 1) / n
        for k, (z0, z1) in enumerate(((0.1, 0.36), (0.365, 0.61), (0.615, 0.86))):
            box("kitchen_drawer", x0 + 0.002, x1 - 0.002, 5.88, 6.44, z0, z1, "kitchen_grey", 0.004)
        box("kitchen_upper", x0 + 0.002, x1 - 0.002, 6.09, 6.44, 1.5, 2.25, "white", 0.004)
    box("kitchen_plinth", 7.36, 9.52, 5.93, 6.44, 0, 0.1, "black")
    box("counter", 7.34, 9.54, 5.86, 6.44, 0.86, 0.9, "white", 0.004)
    box("backsplash", 7.36, 9.52, 6.425, 6.44, 0.9, 1.5, "tile_wall")
    box("sink", 7.6, 8.15, 5.98, 6.34, 0.895, 0.903, "steel")
    cyl("tap", 7.87, 6.37, 0.012, 0.9, 1.18, "chrome", verts=10)
    box("tap_spout", 7.86, 7.88, 6.2, 6.37, 1.16, 1.18, "chrome")
    box("hob", 8.6, 9.2, 5.96, 6.36, 0.9, 0.906, "black")
    box("hood", 8.6, 9.2, 6.14, 6.44, 1.42, 1.5, "steel")
    box("fridge", 6.58, 7.3, 5.74, 6.44, 0.02, 1.86, "silver", 0.01)
    box("fridge_gap", 6.58, 7.3, 5.735, 5.745, 0.75, 0.76, "black")
    S[0] = "decor"
    cyl("kettle", 9.35, 6.2, 0.07, 0.9, 1.08, "chrome", r2=0.05)
    cyl("fruit_bowl", 8.38, 6.15, 0.08, 0.9, 0.96, "ceramic", r2=0.13)
    # ---- master bedroom
    S[0] = "furniture"
    master_bed()
    # ---- dressing room (the chrome system hangers in the photo)
    S[0] = "builtin"
    rack(3.7, 4.2, 0.25, 2.35, 2, "w")
    rack(6.0, 6.5, 0.25, 3.15, 3, "e")
    for x in (4.45, 5.25):
        cyl("rack_post_s", x, 0.2, 0.011, 0, 2.1, "chrome", verts=8); cyl("rack_post_s", x, 0.62, 0.011, 0, 2.1, "chrome", verts=8)
    box("rack_shelf_s", 4.45, 5.25, 0.2, 0.62, 2.0, 2.02, "white"); box("rack_shelf_s", 4.45, 5.25, 0.2, 0.62, 0.95, 0.97, "white")
    for k in range(2):
        box("rack_drawer_s", 4.47, 5.23, 0.2, 0.62, 0.2 + 0.26 * k, 0.45 + 0.26 * k, "white", 0.004)
    S[0] = "lights"
    box("dressing_light", 4.85, 5.35, 1.45, 1.95, H - 0.05, H - 0.002, "panel", col="ceiling")
    box("master_light", 1.5, 2.1, 2.3, 2.9, H - 0.05, H - 0.002, "panel", col="ceiling")
    box("living_light", 8.2, 9.0, 1.6, 2.4, H - 0.05, H - 0.002, "panel", col="ceiling")
    # ---- small room (guest)
    S[0] = "furniture"
    box("guest_frame", 7.25, 9.3, 7.78, 8.78, 0.08, 0.3, "walnut", 0.01)
    box("guest_mattress", 7.28, 9.27, 7.8, 8.76, 0.3, 0.5, "white", 0.05, 4)
    box("guest_duvet", 7.25, 8.7, 7.77, 8.79, 0.36, 0.55, "linen", 0.06, 4)
    box("guest_pillow", 8.8, 9.22, 7.95, 8.6, 0.5, 0.64, "white", 0.06, 4)
    S[0] = "builtin"
    box("closet", 8.3, 9.32, 6.58, 7.1, 0.05, 2.2, "white", 0.004)
    # ---- bath
    box("vanity", 3.22, 3.7, 5.5, 6.05, 0.3, 0.8, "walnut", 0.005)
    box("basin", 3.24, 3.68, 5.56, 6.0, 0.8, 0.9, "ceramic", 0.03, 3)
    cyl("basin_tap", 3.28, 5.78, 0.01, 0.9, 1.05, "chrome", verts=8)
    box("bath_mirror", 3.205, 3.215, 5.5, 6.05, 1.1, 1.8, "chrome")
    box("toilet_tank", 3.22, 3.4, 4.75, 5.15, 0.4, 0.8, "ceramic", 0.02, 3)
    box("toilet_bowl", 3.4, 3.85, 4.77, 5.13, 0.0, 0.4, "ceramic", 0.06, 4)
    box("toilet_lid", 3.4, 3.86, 4.76, 5.14, 0.4, 0.43, "ceramic", 0.012, 2)
    box("shower_tray", 3.22, 4.82, 6.15, 6.92, -0.004, 0.03, "ceramic", 0.008)
    box("shower_glass", 3.9, 4.82, 6.14, 6.15, 0.03, 2.0, "glass", stage="glass")
    cyl("shower_pipe", 3.26, 6.55, 0.012, 1.0, 2.05, "chrome", verts=8)
    cyl("shower_head", 3.4, 6.55, 0.1, 2.03, 2.05, "chrome")
    S[0] = "decor"
    box("bath_mat", 4.0, 4.6, 5.55, 5.95, 0, 0.012, "linen", 0.004)
    # ---- entrance
    S[0] = "builtin"
    for i in range(2):
        box("shoe_cabinet", 3.22, 3.58, 7.12 + 0.82 * i, 7.12 + 0.82 * (i + 1) - 0.004, -0.03, 2.2, "white", 0.004)
    S[0] = "decor"
    box("door_mat", 3.9, 4.6, 8.3, 8.75, -0.038, -0.028, "navy")
    # ---- utility
    S[0] = "builtin"
    box("washer", 9.5, 10.1, 8.2, 8.8, 0.0, 0.85, "white", 0.01)
    box("boiler", 9.5, 9.9, 6.6, 6.95, 1.2, 1.9, "white", 0.01)
    STAGE[0] = "misc"


# ---------------------------------------------------------------- world
def world(strength=1.0, sun=4.5, az=148, el=38):
    w = bpy.data.worlds.new("w"); bpy.context.scene.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    N, L = w.node_tree.nodes, w.node_tree.links
    N.clear()
    out = N.new("ShaderNodeOutputWorld"); bg = N.new("ShaderNodeBackground")
    tc = N.new("ShaderNodeTexCoord"); sx = N.new("ShaderNodeSeparateXYZ")
    L.new(tc.outputs["Generated"], sx.inputs[0])
    cr = N.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].position = 0.0; cr.color_ramp.elements[0].color = (0.9, 0.9, 0.88, 1)
    cr.color_ramp.elements[1].position = 0.6; cr.color_ramp.elements[1].color = (0.48, 0.66, 0.95, 1)
    e = cr.color_ramp.elements.new(0.08); e.color = (0.86, 0.9, 0.95, 1)
    L.new(sx.outputs["Z"], cr.inputs[0]); L.new(cr.outputs[0], bg.inputs[0])
    bg.inputs[1].default_value = strength
    L.new(bg.outputs[0], out.inputs[0])
    d = bpy.data.lights.new("sun", "SUN"); d.energy = sun; d.angle = math.radians(2.5); d.color = (1.0, 0.93, 0.84)
    o = bpy.data.objects.new("sun", d); bpy.context.scene.collection.objects.link(o)
    a, e_ = math.radians(az), math.radians(el)   # azimuth from north, clockwise; light comes from there
    v = Vector((math.sin(a) * math.cos(e_), math.cos(a) * math.cos(e_), math.sin(e_)))
    o.rotation_euler = v.to_track_quat("Z", "Y").to_euler()
    return o


def ground(paper=True):
    """the plan photo as a sheet under the model, mapped so the drawing is life size, on a dark desk"""
    w, h = 1502 / PX, 2560 / PX
    x0, y1 = -PX0 / PX, PY0 / PX
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in ((x0, y1 - h, -0.075), (x0 + w, y1 - h, -0.075), (x0 + w, y1, -0.075), (x0, y1, -0.075))]
    f = bm.faces.new(vs)
    uv = bm.loops.layers.uv.new()
    for l, c in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        l[uv].uv = c
    o = _finish("paper", bm, "paper" if paper else "slab", "paper", col="ground")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=120)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(5, 4, -0.09))
    _finish("desk", bm, "desk", "paper", col="ground")
    return o


def camera(loc, target, lens=35, name="cam"):
    c = bpy.data.cameras.new(name); o = bpy.data.objects.new(name, c)
    bpy.context.scene.collection.objects.link(o)
    c.lens = lens; c.clip_start = 0.05; c.clip_end = 500
    aim(o, loc, target)
    bpy.context.scene.camera = o
    return o


def aim(o, loc, target, roll=0.0):
    o.location = loc
    q = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y")
    o.rotation_euler = (q @ Matrix.Rotation(roll, 4, "Z").to_quaternion()).to_euler()


def build(paper=True, samples=48, res=(960, 540)):
    s = reset(samples, res)
    materials()
    STAGE[0] = "slab"
    ground(paper)
    build_floor()
    build_walls()
    build_ceiling()
    furnish()
    world()
    return s
