// Sentry Phase 8 - desk stand (fits the RX node and the Alert Station)
// part = "stand" (printable, already lying on its side) | "scene" (preview with a device)
include <sentry_enclosure.scad>
use <alert_station.scad>
part = "stand";

// put a device (its own coordinates) into the stand: bottom on the back plate, USB end on the ledge
module on_stand() {
    stand_frame3d() multmatrix([[0, 0, 1, 0], [1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1]]) children();
}
module stand_frame3d() { translate([0, 5.2, 0]) rotate([0, 0, stand_tilt]) children(); }

if (part == "stand") desk_stand();
else if (part == "scene") {
    // shown standing up (the printed part lies on its side)
    rotate([90, 0, 0]) {
        color("#3a6ea5") desk_stand();
        on_stand() translate([0, 0, 0.4]) as_assembly(0);
    }
}
