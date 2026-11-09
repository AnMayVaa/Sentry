// Visual stand-ins for the electronics (previews and fit checks only, never printed).
module dummy_board() {
    // PCB, ESP32 module with shield, micro-USB, header pins underneath
    at_inner([board_x0 + board_tol / 2, board_y0 + board_tol / 2], pcb_z0) {
        color("#1f6f3f") cube([board_l, board_w, board_t]);
        color("#c0c4c8") translate([board_l - 25.5, (board_w - 18) / 2, board_t]) cube([25.5 - 6.5, 18, 3.2]);
        color("#20242a") translate([board_l - 6.5, (board_w - 18) / 2, board_t]) cube([6.5, 18, 0.8]);
        color("#c0c4c8") translate([-0.8, board_w / 2 - 4, board_t]) cube([5.5, 8, 2.8]);
        color("#111") for (y = [1.3, board_w - 1.3 - 2.5]) translate([7, y, -8.5]) cube([38, 2.5, 8.5]);
    }
}
module dummy_buzzer(buz) { at_inner(buz, base_h - 9.5) cylinder(d = buzzer_d, h = 9.5); }
// switch body + stem (cap separately); body rests on the backer bar
module dummy_switch(btn) {
    at_inner(btn, base_h - btn_drop) {
        translate([-btn_body / 2, -btn_body / 2, 0]) cube([btn_body, btn_body, 3.5]);
        cylinder(d = 3.5, h = btn_stack_h - 3);
    }
}
module dummy_cap(btn) { at_inner(btn, base_h + lid_t + btn_proud - 6) cylinder(d = btn_cap_d, h = 6); }
module dummy_backer(btn) { at_inner(btn, base_h - btn_drop - btn_slot_h) rotate(90) button_backer(); }
module dummy_led(led_p) {
    at_inner(led_p, base_h - 1) { cylinder(d = led_flange_d, h = 1); cylinder(d = led_d, h = 8.6 - 2.5); translate([0, 0, 8.6 - 2.5]) sphere(d = led_d); }
}
module preview_internals(buz, btn, led_p, rx, e) {
    translate([0, 0, e]) dummy_board();
    color("#151515") translate([0, 0, e * 1.5]) dummy_buzzer(buz);
    color("#202020") translate([0, 0, e * 1.5]) dummy_switch(btn);
    color("#8a8f98") translate([0, 0, e * 1.5]) dummy_backer(btn);
    color("#ff3b30") translate([0, 0, e * 1.5]) dummy_led(led_p);
}
module preview_cap(btn, e) {
    color("#d7262e") translate([0, 0, e]) dummy_cap(btn);
}
module preview_antenna(e) {
    color("#1a1a1a") translate([outer_x + e * 0.5, wall + board_cy, 14]) {
        rotate([0, 90, 0]) cylinder(d = 8, h = 10);
        translate([10, 0, 0]) rotate([0, 0, 0]) cylinder(d = 9, h = 70);
    }
}
