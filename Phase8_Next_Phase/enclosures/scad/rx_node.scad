// Sentry Phase 8 - RX node enclosure (ESP32 + 2.4 GHz antenna + buzzer + LED + SOS button)
// part = "base" | "lid" | "backer" | "shim" | "assembly" | "exploded"
include <sentry_enclosure.scad>
part = "assembly";

rx_buzzer = [14, strip_y];
rx_button = [34, strip_y];
rx_led    = [54, strip_y];

module rx_lid() {
    difference() {
        union() {
            lid_plate();
            lid_skirt();
            board_holddown();
            button_socket(rx_button);
            buzzer_holder(rx_buzzer);
            led_boss(rx_led);
        }
        screw_holes();
        button_hole(rx_button);
        buzzer_grille(rx_buzzer);
        led_hole(rx_led);
        wave_logo([inner_x / 2, 18], 1.4);   // no brand name, just the Wi-Fi mark
        lid_text("HOLD 2s = SOS", [rx_button[0], inner_y - 2.2], 3.2);
    }
}
module rx_base() { base(sma = true, label = ""); }

include <parts_preview.scad>
module rx_assembly(e = 0) {
    color("#2b2f36") rx_base();
    preview_internals(rx_buzzer, rx_button, rx_led, true, e);
    color("#e8e6e1") translate([0, 0, base_h + e * 2]) rx_lid();
    preview_cap(rx_button, e * 2);
    preview_antenna(e);
}
if (part == "base") rx_base();
else if (part == "lid") translate([0, outer_y, lid_t]) rotate([180, 0, 0]) rx_lid();   // print top face down
else if (part == "backer") button_backer();
else if (part == "shim") button_shim(1.0);
// fit-check parts (assembled position)
else if (part == "lid_asm") translate([0, 0, base_h]) rx_lid();
else if (part == "dummy_board") dummy_board();
else if (part == "dummy_buzzer") dummy_buzzer(rx_buzzer);
else if (part == "dummy_switch") dummy_switch(rx_button);
else if (part == "dummy_cap") dummy_cap(rx_button);
else if (part == "dummy_backer") dummy_backer(rx_button);
else if (part == "dummy_led") dummy_led(rx_led);
else if (part == "assembly" || part == "exploded") {
    e = part == "exploded" ? 30 : 0;
    rx_assembly(e);
}
