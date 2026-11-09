// =====================================================================
// Sentry Phase 8 - parametric enclosure library (OpenSCAD 2021.01+)
//
// One box design is shared by the RX node and the Alert Station, so
// one desk stand, one set of screws and one print profile fit both.
//
//   +---------------------------- 72.8 x 72.8 x 35.8 mm ----+  (no brand name on any part)
//   |  [USB]  ESP32 DevKit (pins down, on 4 corner posts)    | [SMA]
//   |                                                        |
//   |  buzzer      button / dome       LED / button          |
//   +--------------------------------------------------------+
//
// All sizes in mm. Change the numbers in the "MEASURE YOUR PARTS"
// block, re-render, and every hole/socket moves with them.
// Print: PLA or PETG, 0.2 mm layers, 3 walls, 20 % infill, NO supports.
// =====================================================================

$fn = 64;

// ---------------- MEASURE YOUR PARTS ----------------
board_l      = 52.0;   // ESP32 DevKit PCB length (USB end to antenna end). 30-pin ~51.5, 38-pin ~55
board_w      = 28.5;   // PCB width
board_t      = 1.6;    // PCB thickness
board_tol    = 0.6;    // total play around the PCB
under_board  = 21.0;   // space under the PCB: header pins (8.5) + Dupont housings (14) + room to bend the wires

usb_w = 12.0;          // micro-USB plug overmould opening (width)
usb_h = 8.0;           // (height)
usb_z_above_pcb = 1.4; // centre of the USB socket above the PCB top

sma_d = 6.6;           // 2.4 GHz antenna SMA bulkhead hole (RP-SMA/SMA 1/4"-36 thread = 6.35)

buzzer_d   = 12.0;     // active buzzer body diameter
buzzer_tol = 0.4;

led_d        = 5.0;    // 5 mm LED body
led_flange_d = 5.8;    // LED rim at the bottom of the body

btn_body     = 12.0;   // 12 x 12 tactile switch body
btn_cap_d    = 12.0;   // cap diameter (round cap). The lid hole is cap + 0.6
btn_stack_h  = 10.3;   // switch bottom -> cap top (12x12x7.3 switch + kit cap = ~10.3)
btn_proud    = 1.5;    // how far the cap sticks out above the lid

screw_pilot_d = 2.5;   // M3 self-tapping (or M3 machine screw tapped into plastic)
screw_clear_d = 3.4;
screw_head_d  = 6.4;   // M3 countersunk head

// ---------------- BOX ----------------
wall   = 2.4;
floor_t = 2.4;
lid_t  = 2.4;
inner_x = 68;          // along the board
inner_y = 68;
inner_h = 31;          // floor top -> lid underside
corner_r = 6;
fit    = 0.3;          // clearance for parts that slide into each other

outer_x = inner_x + 2 * wall;
outer_y = inner_y + 2 * wall;
base_h  = floor_t + inner_h;   // base wall height (lid sits on top)

// ---------------- LAYOUT (inner coordinates, origin = inside corner) ----------------
boss_d   = 7;
boss_in  = 4;                                // boss centre from inner walls
boss_xy  = [[boss_in, boss_in], [inner_x - boss_in, boss_in],
            [boss_in, inner_y - boss_in], [inner_x - boss_in, inner_y - boss_in]];

board_x0 = 1.5;                              // USB end gap to the wall
board_y0 = 8.5;
pcb_l = board_l + board_tol;
pcb_w = board_w + board_tol;
pcb_z0 = floor_t + under_board;              // underside of PCB (base coordinates)
pcb_z1 = pcb_z0 + board_t;
board_cy = board_y0 + pcb_w / 2;

strip_y  = 54;                               // component row (buzzer / button / LED)

// ---------------- helpers ----------------
module rounded_box(x, y, h, r) {
    hull() for (cx = [r, x - r], cy = [r, y - r]) translate([cx, cy, 0]) cylinder(r = r, h = h);
}
module at_inner(p, z = 0) { translate([wall + p[0], wall + p[1], z]) children(); }

// =====================================================================
// BASE
// =====================================================================
module base(sma = true, label = "") {
    difference() {
        union() {
            difference() {
                rounded_box(outer_x, outer_y, base_h, corner_r);
                translate([wall, wall, floor_t]) rounded_box(inner_x, inner_y, base_h, corner_r - wall);
            }
            // lid screw bosses
            for (p = boss_xy) at_inner(p) cylinder(d = boss_d, h = base_h);
            // fill the rounded inner corner behind each boss
            for (p = boss_xy) at_inner(p) hull() {
                cylinder(d = boss_d, h = base_h);
                translate([p[0] < inner_x / 2 ? -boss_in : boss_in - 0.01, p[1] < inner_y / 2 ? -boss_in : boss_in - 0.01, 0])
                    cylinder(d = 0.01, h = base_h);
            }
            board_posts();
        }
        // screw pilots
        for (p = boss_xy) at_inner(p, base_h - 14) cylinder(d = screw_pilot_d, h = 15);
        // USB opening (x = 0 wall)
        translate([-1, wall + board_cy - usb_w / 2, pcb_z1 + usb_z_above_pcb - usb_h / 2])
            cube([wall + 2, usb_w, usb_h]);
        // chamfer the outside of the USB opening so any cable fits
        translate([0, wall + board_cy, pcb_z1 + usb_z_above_pcb])
            rotate([0, 90, 0]) linear_extrude(height = 1.2, scale = 0.8)
                square([usb_h + 2.4, usb_w + 2.4], center = true);
        // antenna (x = max wall)
        if (sma)
            translate([outer_x - wall - 1, wall + board_cy, 14]) rotate([0, 90, 0]) cylinder(d = sma_d, h = wall + 2);
        // side vents (y = 0 wall), stylised slots
        for (i = [0 : 6]) translate([wall + 16 + i * 6, -1, floor_t + 5]) cube([2.2, wall + 2, 12]);
        // keyholes for wall screws (USB end hangs down). Screw head <= 8 mm, shank <= 4 mm
        for (ky = [16, inner_y - 16]) keyhole(28, ky);
        // rubber feet recesses (8 mm stick-on bumpers)
        for (cx = [9, outer_x - 9], cy = [9, outer_y - 9]) translate([cx, cy, -0.01]) cylinder(d = 8.6, h = 0.8);
        // underside label
        if (label != "")
            translate([outer_x / 2, outer_y / 2 + 3, -0.01]) linear_extrude(0.6)
                mirror([1, 0, 0]) text(label, size = 4.2, font = "DejaVu Sans:style=Bold", halign = "center", valign = "center");
    }
}

// keyhole at inner coords (x, y): big hole 8.6, then a 4.2 slot running +x (up on the wall)
module keyhole(x, y) {
    lip = 1.2;
    at_inner([x, y], -1) {
        cylinder(d = 8.6, h = floor_t + 2);
        hull() { cylinder(d = 4.2, h = floor_t + 2); translate([7, 0, 0]) cylinder(d = 4.2, h = floor_t + 2); }
    }
    // channel above the lip so the screw head can slide
    at_inner([x, y], lip) hull() { cylinder(d = 8.6, h = floor_t); translate([7, 0, 0]) cylinder(d = 8.6, h = floor_t); }
}

// 4 corner posts the PCB rests on, with a 2 mm fence that locates it.
// Posts stay within 3.5 mm of the PCB ends so they miss the header pins.
module board_posts() {
    post = 3.5;
    fence = 1.2;
    for (ex = [0, 1], ey = [0, 1]) {
        px = board_x0 + (ex ? pcb_l - post : 0);
        py = board_y0 + (ey ? pcb_w - post : 0);
        fy = ey ? board_y0 + pcb_w : board_y0 - fence;          // fence outside the long edge
        // post the PCB corner rests on
        at_inner([px, py]) cube([post, post, pcb_z0]);
        // long-edge fence (+ web to the floor); at the antenna end it runs on past the
        // PCB end so it overlaps the end fence and forms one solid L (no edge-only contact)
        at_inner([px, fy]) cube([post + (ex ? fence : 0), fence, pcb_z1 + 2]);
        // end fence at the antenna end (the USB end is located by the wall + USB plug)
        if (ex) at_inner([board_x0 + pcb_l, ey ? py : board_y0 - fence]) cube([fence, post + fence, pcb_z1 + 2]);
    }
}

// =====================================================================
// LID (modelled in assembled position: z = 0 is the top of the base walls)
// =====================================================================
embed = 0.5;              // lid features reach this far into the plate (clean union)
btn_plate_t = 2.0;        // backer bar
btn_slot_h  = btn_plate_t + 0.3;
btn_wall    = 1.6;
btn_sock    = btn_body + 0.4;
// distance from lid underside to the top of the backer bar
btn_drop    = btn_stack_h - btn_proud - lid_t;
btn_sock_h  = btn_drop + btn_slot_h + 1.2;

module lid_plate(chamfer = 1.2) {
    // top edge chamfer for a finished look
    hull() {
        rounded_box(outer_x, outer_y, lid_t - chamfer, corner_r);
        translate([chamfer, chamfer, 0]) rounded_box(outer_x - 2 * chamfer, outer_y - 2 * chamfer, lid_t, corner_r - chamfer);
    }
}

// skirt that keys the lid into the base (cut away at the corner bosses)
module lid_skirt() {
    h = 3; t = 1.6;
    difference() {
        translate([wall + fit, wall + fit, -h]) rounded_box(inner_x - 2 * fit, inner_y - 2 * fit, h + embed, corner_r - wall - fit);
        translate([wall + fit + t, wall + fit + t, -h - 1]) rounded_box(inner_x - 2 * (fit + t), inner_y - 2 * (fit + t), h + 1 + embed, max(0.5, corner_r - wall - fit - t));
        for (p = boss_xy) at_inner(p, -h - 1) cylinder(d = boss_d + 2 * 2.5, h = h + 2);
    }
}

// pillars that stop the PCB lifting (antenna-end corners, clear of the module)
module board_holddown() {
    gap = 0.4;
    len = base_h - pcb_z1 - gap;
    for (py = [board_y0 + 1.8, board_y0 + pcb_w - 1.8])
        at_inner([board_x0 + pcb_l - 1.8, py], -len) cylinder(d = 3, h = len + embed);
}

module screw_holes() {
    for (p = boss_xy) at_inner(p, -1) {
        cylinder(d = screw_clear_d, h = lid_t + 2);
        translate([0, 0, 1 + lid_t - (screw_head_d - screw_clear_d) / 2]) cylinder(d1 = screw_clear_d, d2 = screw_head_d + 0.01, h = (screw_head_d - screw_clear_d) / 2 + 0.01);
    }
}

// ----- button: hole + socket + slots for the backer bar -----
module button_hole(p) { at_inner(p, -1) cylinder(d = btn_cap_d + 0.6, h = lid_t + 2); }
module button_socket(p) {
    seg = btn_sock - 5;   // wall length, corners open for the switch legs
    at_inner(p, -btn_sock_h) difference() {
        union() for (a = [0, 90, 180, 270]) rotate(a)
            translate([-seg / 2, btn_sock / 2, 0]) cube([seg, btn_wall, btn_sock_h + embed]);
        // backer-bar slot through the two walls facing +-y
        translate([-2.2, -btn_sock, btn_sock_h - btn_drop - btn_slot_h]) cube([4.4, 2 * btn_sock, btn_slot_h]);
    }
}
// backer bar: slides through the socket slots under the switch (print flat)
module button_backer() {
    l = btn_sock + 2 * btn_wall + 4;
    difference() {
        translate([-l / 2, -2, 0]) cube([l, 4, btn_plate_t]);
    }
    // pull tab
    translate([l / 2 - 1, -3, 0]) cube([2, 6, btn_plate_t]);
}
// 0.5 / 1.0 mm shims: put between bar and switch if the cap does not stick out enough
module button_shim(t = 1.0) { translate([-5, -2, 0]) cube([10, 4, t]); }

// ----- buzzer: press-fit ring with crush ribs + sound grille -----
module buzzer_holder(p) {
    d = buzzer_d + buzzer_tol;
    at_inner(p, -6) difference() {
        cylinder(d = d + 3.2, h = 6 + embed);
        translate([0, 0, -1]) cylinder(d = d, h = 6 + 1 + embed + 0.01);
        // gap for the wires
        translate([-2, 0, -1]) cube([4, d, 4]);
    }
    // crush ribs: 0.1 mm interference holds the buzzer without glue
    for (a = [60, 180, 300]) at_inner(p, -6) rotate(a) translate([d / 2 + 0.2, 0, 0]) cylinder(d = 1, h = 6 + embed, $fn = 12);
}
module buzzer_grille(p) {
    at_inner(p, -1) {
        cylinder(d = 1.8, h = lid_t + 2, $fn = 16);
        for (a = [0 : 60 : 300]) rotate(a) translate([3.2, 0, 0]) cylinder(d = 1.8, h = lid_t + 2, $fn = 16);
    }
}

// ----- LED: hole + boss so the LED rim stops on the lid underside -----
module led_hole(p) { at_inner(p, -1) cylinder(d = led_d + 0.2, h = lid_t + 2); }
module led_boss(p) {
    at_inner(p, -4) difference() {
        cylinder(d = 9, h = 4 + embed);
        translate([0, 0, -1]) cylinder(d = led_flange_d + 0.3, h = 5);
    }
}

// ----- light dome for the Alert Station (print in white / natural PLA) -----
dome_d = 20; dome_h = 15; dome_wall = 1.2; dome_plug = 1.0;
module dome_recess(p) { at_inner(p, lid_t - dome_plug) cylinder(d = dome_d - 2 * dome_wall + 0.3 + 2 * dome_wall, h = dome_plug + 1); }
module light_dome() {
    // printed open side down; 45 deg top chamfer = no supports
    difference() {
        union() {
            translate([0, 0, -dome_plug]) cylinder(d = dome_d, h = dome_plug);   // plug into the recess
            cylinder(d1 = dome_d, d2 = dome_d + 2, h = 1.0);                     // 45 deg flange (no overhang)
            translate([0, 0, 1]) cylinder(d = dome_d + 2, h = 0.6);
            hull() {
                cylinder(d = dome_d, h = dome_h - 4);
                cylinder(d = dome_d - 8, h = dome_h);
            }
        }
        hull() {
            translate([0, 0, -dome_plug - 1]) cylinder(d = dome_d - 2 * dome_wall, h = dome_h - 4 + dome_plug + 1);
            translate([0, 0, -dome_plug - 1]) cylinder(d = dome_d - 8 - 2 * dome_wall, h = dome_h - dome_wall + dome_plug + 1);
        }
    }
}

module lid_text(txt, p, size, depth = 0.6) {
    at_inner(p, lid_t - depth) linear_extrude(depth + 1)
        text(txt, size = size, font = "DejaVu Sans:style=Bold", halign = "center", valign = "center");
}

// wave logo (three Wi-Fi arcs over a dot) engraved on the lid
module wave_logo(p, s = 1, depth = 0.6) {
    at_inner(p, lid_t - depth) linear_extrude(depth + 1) scale(s) {
        intersection() {
            union() for (r = [4, 7, 10]) difference() { circle(r = r + 1.4); circle(r = r); }
            polygon([[0, 0], [20, 20], [-20, 20]]);   // 90 deg wedge pointing up
        }
        circle(r = 1.8);
    }
}

// =====================================================================
// DESK STAND (fits both devices). Device leans back 20 deg, USB end in the
// cradle with a cable notch. Printed on its side (no supports).
// =====================================================================
stand_w = outer_x;        // same width as the device: line the sides up
stand_tilt = 20;
stand_th = 3.2;
stand_dev_t = base_h + lid_t + 0.8;   // device thickness + play
module stand_frame() { translate([0, 5.2]) rotate(stand_tilt) children(); }
module stand_profile() {
    th = stand_th; dev_t = stand_dev_t;
    lip_h = 7; back_len = 58;
    stand_frame() union() {
        translate([-th, 0]) square([th, back_len]);          // back plate
        translate([-th, -th]) square([dev_t + 2 * th, th]);  // ledge
        translate([dev_t, -th]) square([th, lip_h + th]);     // front lip
    }
    // wedge under the ledge down to the ground
    hull() {
        stand_frame() translate([-th, -th]) square([dev_t + 2 * th, th]);
        translate([-th - 2, 0]) square([dev_t + 12, 3]);
    }
    // rear foot + strut
    hull() { translate([-28, 0]) square([20, 3]); stand_frame() translate([-th, 32]) square([th, 4]); }
}
// Region in front of the back plate between z0 and z1, whose roof rises 45 deg
// away from the back plate: when printed on its side every layer is supported.
module stand_notch(z0, z1) {
    translate([0, 5.2, 0]) rotate([0, 0, stand_tilt]) hull() {
        translate([0.01, -60, z0]) cube([0.01, 260, z1 - z0]);
        translate([150, -60, z0]) cube([0.01, 260, z1 - z0 + 150]);
    }
}
module desk_stand() {
    // USB plug position along the device width (from the device side wall)
    usb_c = wall + board_cy;
    difference() {
        linear_extrude(stand_w) stand_profile();
        // cable notch: everything in front of the back plate, in a band around the plug
        stand_notch(usb_c - 9, usb_c + 9);
    }
}
