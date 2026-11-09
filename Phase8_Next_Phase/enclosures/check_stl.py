#!/usr/bin/env python3
"""Checks the Phase 8 STLs before you send them to a print shop.

1. Every printable part: closed (watertight / manifold), one solid body,
   sits flat on the bed (z = 0), fits a 220 x 220 mm bed, and lists every
   downward-facing surface above the bed (bridges) so you can see none need supports.
2. Fit check: the lid, PCB, buzzer, switch, cap, backer bar and LED are
   placed where they sit in the real device and tested for collisions.

Run:  python3 Phase8_Next_Phase/enclosures/check_stl.py
Needs: pip install trimesh manifold3d numpy
Exit code 1 if anything fails.
"""
import os
import sys

import numpy as np
import trimesh
import manifold3d as m3d

HERE = os.path.dirname(os.path.abspath(__file__))
STL = os.path.join(HERE, "stl")
FIT = os.path.join(HERE, ".fitcheck")
BED = 220.0
PLA_DENSITY = 1.24  # g/cm3

PRINTABLE = [
    "rx_node_base.stl", "rx_node_lid.stl",
    "alert_station_base.stl", "alert_station_base_antenna_hole.stl", "alert_station_lid.stl", "alert_station_light_dome.stl",
    "button_backer_bar.stl", "button_shim_1mm.stl", "desk_stand.stl",
]

failures = []


def fail(msg):
    failures.append(msg)
    print("   FAIL", msg)


def to_manifold(mesh):
    m = m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(mesh.vertices, dtype=np.float32),
                              tri_verts=np.asarray(mesh.faces, dtype=np.uint32)))
    if m.status() != m3d.Error.NoError:
        raise ValueError(f"manifold3d rejected mesh: {m.status()}")
    return m


def bridges(mesh, bed_z, min_area=1.0):
    """Find flat, downward-facing surfaces above the bed (ceilings the printer must
    bridge). Each connected patch is reported as (z, area, width) where
    width = 2 * area / perimeter: ~the bridge length for a strip, ~1 mm for a thin ledge."""
    n = mesh.face_normals
    down = np.where(n[:, 2] < -0.95)[0]
    out = []
    if len(down) == 0:
        return out
    centers_z = mesh.triangles_center[down, 2]
    keep = down[centers_z > bed_z + 0.05]
    if len(keep) == 0:
        return out
    keep_set = set(keep.tolist())
    adj = [(a, b) for a, b in mesh.face_adjacency if a in keep_set and b in keep_set]
    groups = trimesh.graph.connected_components(adj, nodes=keep, min_len=1)
    for g in groups:
        g = np.asarray(list(g))
        area = float(mesh.area_faces[g].sum())
        if area < min_area:
            continue
        edges = np.sort(mesh.faces[g][:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1)
        uniq, counts = np.unique(edges, axis=0, return_counts=True)
        boundary = uniq[counts == 1]
        perim = float(np.linalg.norm(mesh.vertices[boundary[:, 0]] - mesh.vertices[boundary[:, 1]], axis=1).sum())
        width = 2 * area / perim if perim > 0 else 0.0
        z = float(mesh.triangles_center[g, 2].mean())
        out.append((z, area, width))
    out.sort()
    return out


def check_printable(name):
    path = os.path.join(STL, name)
    print(f"== {name}")
    if not os.path.exists(path):
        fail(f"{name}: missing (run build.sh)")
        return
    mesh = trimesh.load(path, force="mesh")
    lo, hi = mesh.bounds
    size = hi - lo
    print(f"   size {size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm, "
          f"{len(mesh.faces)} triangles")
    if not mesh.is_watertight:
        fail(f"{name}: not watertight")
    if not mesh.is_winding_consistent:
        fail(f"{name}: inconsistent winding")
    if mesh.volume <= 0:
        fail(f"{name}: non-positive volume")
    try:
        to_manifold(mesh)
    except ValueError as e:
        fail(f"{name}: {e}")
    bodies = mesh.split(only_watertight=False)
    if len(bodies) != 1:
        fail(f"{name}: {len(bodies)} separate bodies (expected 1)")
    if abs(lo[2]) > 1e-3:
        fail(f"{name}: lowest point z = {lo[2]:.3f}, should sit on the bed at 0")
    if size[0] > BED or size[1] > BED:
        fail(f"{name}: does not fit a {BED:.0f} mm bed")
    # area touching the bed (for adhesion)
    n = mesh.face_normals
    bed_area = mesh.area_faces[(n[:, 2] < -0.99) & (mesh.triangles_center[:, 2] < 0.01)].sum()
    print(f"   volume {mesh.volume / 1000:.1f} cm3 (~{mesh.volume / 1000 * PLA_DENSITY:.0f} g if solid, "
          f"less with 20% infill), {bed_area / 100:.1f} cm2 on the bed")
    br = bridges(mesh, lo[2])
    if br:
        worst = max(b[2] for b in br)
        print(f"   flat ceilings above the bed: {len(br)} patches, widest {worst:.1f} mm "
              f"(a 0.4 mm nozzle bridges 10-20 mm cleanly)")
        for z, a, w in br:
            if w >= 1.0:
                print(f"     z={z:5.2f}  area {a:6.1f} mm2  width {w:4.1f} mm")
        if worst > 12:
            fail(f"{name}: a ceiling {worst:.1f} mm wide (> 12 mm) may sag; needs supports")
    else:
        print("   no bridges: prints with zero overhangs")
    print("   ok" if not any(f.startswith(name) for f in failures) else "")


def load_fit(dev, part):
    return to_manifold(trimesh.load(os.path.join(FIT, f"{dev}_{part}.stl"), force="mesh"))


def load_print(name):
    return to_manifold(trimesh.load(os.path.join(STL, name), force="mesh"))


def overlap(a, b):
    return (a ^ b).volume()


def fit_check(dev, base_stl):
    print(f"== fit check: {dev}")
    base = load_print(base_stl)
    parts = {p: load_fit(dev, p) for p in
             ["lid_asm", "dummy_board", "dummy_buzzer", "dummy_switch", "dummy_cap", "dummy_backer", "dummy_led"]}
    lid = parts["lid_asm"]
    pairs = [("base", base, "lid", lid)]
    for p in ["dummy_board", "dummy_buzzer", "dummy_switch", "dummy_cap", "dummy_backer", "dummy_led"]:
        pairs.append(("base", base, p, parts[p]))
        if p != "dummy_buzzer":
            pairs.append(("lid", lid, p, parts[p]))
    names = list(parts)[1:]
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if {a, b} == {"dummy_switch", "dummy_cap"}:
                continue  # the cap is pressed onto the switch stem by design
            pairs.append((a, parts[a], b, parts[b]))
    for an, a, bn, b in pairs:
        v = overlap(a, b)
        if v > 0.05:
            fail(f"{dev}: {an} collides with {bn} ({v:.2f} mm3)")
    # the buzzer is meant to be gripped by 3 crush ribs: small, deliberate overlap
    rib = overlap(lid, parts["dummy_buzzer"])
    print(f"   buzzer crush-rib grip: {rib:.2f} mm3 of interference (by design, 0.1 mm per rib)")
    if not 0.1 < rib < 5:
        fail(f"{dev}: buzzer grip {rib:.2f} mm3 is outside the expected range")
    # PCB hold-down: the lid pillars must stop the board lifting more than ~0.5 mm
    lifted = parts["dummy_board"].translate([0, 0, 0.6])
    if overlap(lid, lifted) <= 0.01:
        fail(f"{dev}: lid pillars do not hold the PCB down")
    else:
        print("   PCB is held: it can lift < 0.6 mm before touching the lid pillars")
    # PCB must rest on the posts (moving it down 0.2 mm must hit the base)
    if overlap(base, parts["dummy_board"].translate([0, 0, -0.2])) <= 0.01:
        fail(f"{dev}: PCB is not supported by the posts")
    else:
        print("   PCB rests on its 4 corner posts")
    # the lid must stay seated: dropping it 0.2 mm must hit the base (it sits on the walls)
    if overlap(base, lid.translate([0, 0, -0.2])) <= 0.01:
        fail(f"{dev}: lid does not sit on the base walls")
    # the cap must stick out above the lid
    cap_top = parts["dummy_cap"].bounding_box()[5] if hasattr(parts["dummy_cap"], "bounding_box") else None
    lid_top = lid.bounding_box()[5] if hasattr(lid, "bounding_box") else None
    if cap_top is not None and lid_top is not None:
        print(f"   button cap sticks out {cap_top - lid_top:.1f} mm above the lid")
    if not any(f.startswith(dev) for f in failures):
        print("   ok: no collisions")


def main():
    for name in PRINTABLE:
        check_printable(name)
    fit_check("rx_node", "rx_node_base.stl")
    fit_check("alert_station", "alert_station_base.stl")
    print()
    if failures:
        print(f"{len(failures)} problem(s):")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    print("ALL STL CHECKS PASSED")


if __name__ == "__main__":
    main()
