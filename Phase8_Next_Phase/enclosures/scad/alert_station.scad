// Sentry Phase 8 - Alert Station enclosure (ESP32 + buzzer + LED under a light dome + button)
// part = "base" | "lid" | "dome" | "backer" | "shim" | "assembly" | "exploded"
include <sentry_enclosure.scad>
part = "assembly";

as_buzzer = [13, strip_y];
as_dome   = [33, strip_y];
as_button = [53, strip_y - 1];

module as_lid() {
    difference() {
        union() {
            lid_plate();
            lid_skirt();
            board_holddown();
            button_socket(as_button);
            buzzer_holder(as_buzzer);
            led_boss(as_dome);
        }
        screw_holes();
        button_hole(as_button);
        buzzer_grille(as_buzzer);
        led_hole(as_dome);
        dome_recess(as_dome);
        wave_logo([inner_x / 2, 18], 1.4);   // no brand name, just the Wi-Fi mark
        lid_text("SILENCE", [as_button[0] - 1, inner_y - 2.2], 2.8);
    }
}
module as_base() { base(sma = false, label = ""); }

include <parts_preview.scad>
module as_assembly(e = 0) {
    color("#2b2f36") as_base();
    preview_internals(as_buzzer, as_button, as_dome, false, e);
    color("#e8e6e1") translate([0, 0, base_h + e * 2]) as_lid();
    color("#fff4f2", 0.75) at_inner(as_dome, base_h + lid_t + e * 2.6) light_dome();
    color("#ff3b30") at_inner(as_dome, base_h + lid_t + e * 2.6 + 3) sphere(d = 4);
    preview_cap(as_button, e * 2);
}
if (part == "base") as_base();
else if (part == "base_sma") base(sma = true, label = "");   // for an ESP32-WROOM-32U that needs its antenna outside
else if (part == "lid") translate([0, outer_y, lid_t]) rotate([180, 0, 0]) as_lid();
else if (part == "dome") translate([0, 0, 1]) light_dome();
else if (part == "backer") button_backer();
else if (part == "shim") button_shim(1.0);
// fit-check parts (assembled position)
else if (part == "lid_asm") translate([0, 0, base_h]) as_lid();
else if (part == "dummy_board") dummy_board();
else if (part == "dummy_buzzer") dummy_buzzer(as_buzzer);
else if (part == "dummy_switch") dummy_switch(as_button);
else if (part == "dummy_cap") dummy_cap(as_button);
else if (part == "dummy_backer") dummy_backer(as_button);
else if (part == "dummy_led") dummy_led(as_dome);
else if (part == "assembly" || part == "exploded") {
    e = part == "exploded" ? 30 : 0;
    as_assembly(e);
}
