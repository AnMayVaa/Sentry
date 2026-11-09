// How the parts sit on a 220 x 220 mm printer bed (no supports needed).
part = "plate";
module bed() { color("#d9d9d9") translate([0, 0, -1]) cube([220, 220, 1]); }
if (part == "plate") {           // RX node set
    bed();
    color("#2b2f36") translate([8, 8, 0]) import("../stl/rx_node_base.stl");
    color("#e8e6e1") translate([90, 8, 0]) import("../stl/rx_node_lid.stl");
    color("#8a8f98") translate([40, 110, 0]) import("../stl/button_backer_bar.stl");
    color("#8a8f98") translate([40, 120, 0]) import("../stl/button_shim_1mm.stl");
    color("#3a6ea5") translate([95, 100, 0]) import("../stl/desk_stand.stl");
} else if (part == "plate_as") { // Alert Station set
    bed();
    color("#2b2f36") translate([8, 8, 0]) import("../stl/alert_station_base.stl");
    color("#e8e6e1") translate([90, 8, 0]) import("../stl/alert_station_lid.stl");
    color("#fff4f2") translate([40, 130, 0]) import("../stl/alert_station_light_dome.stl");
    color("#8a8f98") translate([40, 110, 0]) import("../stl/button_backer_bar.stl");
    color("#3a6ea5") translate([95, 100, 0]) import("../stl/desk_stand.stl");
}
