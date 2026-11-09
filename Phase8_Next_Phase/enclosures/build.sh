#!/usr/bin/env bash
# Rebuilds every STL and PNG from the OpenSCAD sources, then checks them.
#   bash Phase8_Next_Phase/enclosures/build.sh
# Needs: openscad (2021.01+), xvfb-run for PNGs on a headless machine,
#        python3 with trimesh + manifold3d for the checks.
set -euo pipefail
cd "$(dirname "$0")"
OS="openscad"
command -v xvfb-run >/dev/null && PNG="xvfb-run -a openscad" || PNG="openscad"
mkdir -p stl png .fitcheck

stl() {  # file part out
  echo "  STL  $3"
  $OS -o "$3" -D "part=\"$2\"" "scad/$1" 2>&1 | grep -iE "^(ERROR|WARNING)" || true
}
echo "== printable parts (already in print orientation)"
stl rx_node.scad       base   stl/rx_node_base.stl
stl rx_node.scad       lid    stl/rx_node_lid.stl
stl rx_node.scad       backer stl/button_backer_bar.stl
stl rx_node.scad       shim   stl/button_shim_1mm.stl
stl alert_station.scad base   stl/alert_station_base.stl
stl alert_station.scad base_sma stl/alert_station_base_antenna_hole.stl
stl alert_station.scad lid    stl/alert_station_lid.stl
stl alert_station.scad dome   stl/alert_station_light_dome.stl
stl desk_stand.scad    stand  stl/desk_stand.stl

echo "== fit-check parts (assembled position, not for printing)"
for dev in rx_node alert_station; do
  for p in lid_asm dummy_board dummy_buzzer dummy_switch dummy_cap dummy_backer dummy_led; do
    stl $dev.scad $p .fitcheck/${dev}_$p.stl
  done
done

png() {  # file part out camera
  echo "  PNG  $3"
  $PNG -o "$3" -D "part=\"$2\"" --imgsize=1600,1200 --viewall --autocenter --camera=$4 --colorscheme=Tomorrow "scad/$1" 2>&1 | grep -iE "^ERROR" || true
}
echo "== previews"
png rx_node.scad       assembly png/rx_node_assembled.png      0,0,0,55,0,25,0
png rx_node.scad       exploded png/rx_node_exploded.png       0,0,0,62,0,30,0
png rx_node.scad       assembly png/rx_node_back.png           0,0,0,125,0,200,0
png alert_station.scad assembly png/alert_station_assembled.png 0,0,0,55,0,25,0
png alert_station.scad exploded png/alert_station_exploded.png  0,0,0,62,0,30,0
png desk_stand.scad    scene    png/desk_stand_with_device.png  0,0,0,75,0,140,0
png print_plate.scad   plate    png/print_plate_rx_node.png     0,0,0,40,0,20,0
png print_plate.scad   plate_as png/print_plate_alert_station.png 0,0,0,40,0,20,0

echo "== convert STLs to binary (5x smaller, same geometry)"
python3 - <<'PY'
import glob, trimesh
for f in glob.glob("stl/*.stl") + glob.glob(".fitcheck/*.stl"):
    m = trimesh.load(f, force="mesh")
    m.export(f)   # trimesh writes binary STL
PY

echo "== checks"
python3 check_stl.py
