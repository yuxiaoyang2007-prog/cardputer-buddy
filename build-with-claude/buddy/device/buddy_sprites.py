"""Clawd sprite drawing functions for each evolution stage.

Split from buddy_ui_cp.py to reduce per-file compilation memory
on ESP32-S3 (MicroPython compiles to bytecode in RAM).
"""

import M5

_LCD = M5.Lcd

ORANGE = 0xCC785C
DARK = 0x1F1F1F
YELLOW = 0xFFFF00
GRAY_MID = 0x777777
GREEN = 0x00FF00


def draw_baby(x0, y0, blink=False, walk=0):
    c = ORANGE
    _LCD.fillRect(x0 + 5, y0, 16, 1, c)
    _LCD.fillRect(x0 + 3, y0 + 1, 20, 1, c)
    _LCD.fillRect(x0 + 1, y0 + 2, 24, 1, c)
    _LCD.fillRect(x0, y0 + 3, 26, 7, c)
    _LCD.fillRect(x0 + 1, y0 + 10, 24, 1, c)
    _LCD.fillRect(x0 + 3, y0 + 11, 20, 1, c)
    eye_c = c if blink else DARK
    _LCD.fillRect(x0 + 4, y0 + 5, 4, 3, eye_c)
    _LCD.fillRect(x0 + 18, y0 + 5, 4, 3, eye_c)
    ly = y0 + 13
    if walk == 0:
        _LCD.fillRect(x0 + 1, ly, 4, 7, c)
        _LCD.fillRect(x0 + 8, ly + 3, 4, 4, c)
        _LCD.fillRect(x0 + 14, ly, 4, 7, c)
        _LCD.fillRect(x0 + 21, ly + 3, 4, 4, c)
    else:
        _LCD.fillRect(x0 + 1, ly + 3, 4, 4, c)
        _LCD.fillRect(x0 + 8, ly, 4, 7, c)
        _LCD.fillRect(x0 + 14, ly + 3, 4, 4, c)
        _LCD.fillRect(x0 + 21, ly, 4, 7, c)


def draw_adult(x0, y0, blink=False, walk=0):
    c = ORANGE
    _LCD.fillRect(x0 + 5, y0, 18, 1, c)
    _LCD.fillRect(x0 + 3, y0 + 1, 22, 1, c)
    _LCD.fillRect(x0 + 1, y0 + 2, 26, 1, c)
    _LCD.fillRect(x0, y0 + 3, 28, 8, c)
    _LCD.fillRect(x0 + 1, y0 + 11, 26, 1, c)
    _LCD.fillRect(x0 + 3, y0 + 12, 22, 1, c)
    eye_c = c if blink else DARK
    _LCD.fillRect(x0 + 4, y0 + 5, 5, 3, eye_c)
    _LCD.fillRect(x0 + 19, y0 + 5, 5, 3, eye_c)
    ly = y0 + 14
    if walk == 0:
        _LCD.fillRect(x0 + 1, ly, 3, 6, c)
        _LCD.fillRect(x0 + 6, ly + 2, 3, 4, c)
        _LCD.fillRect(x0 + 11, ly, 3, 6, c)
        _LCD.fillRect(x0 + 15, ly + 2, 3, 4, c)
        _LCD.fillRect(x0 + 20, ly, 3, 6, c)
        _LCD.fillRect(x0 + 25, ly + 2, 3, 4, c)
    else:
        _LCD.fillRect(x0 + 1, ly + 2, 3, 4, c)
        _LCD.fillRect(x0 + 6, ly, 3, 6, c)
        _LCD.fillRect(x0 + 11, ly + 2, 3, 4, c)
        _LCD.fillRect(x0 + 15, ly, 3, 6, c)
        _LCD.fillRect(x0 + 20, ly + 2, 3, 4, c)
        _LCD.fillRect(x0 + 25, ly, 3, 6, c)


def draw_master(x0, y0, blink=False, walk=0):
    c = ORANGE
    _LCD.fillRect(x0 + 12, y0, 2, 2, YELLOW)
    _LCD.fillRect(x0 + 15, y0, 2, 2, YELLOW)
    _LCD.fillRect(x0 + 18, y0, 2, 2, YELLOW)
    by = y0 + 2
    _LCD.fillRect(x0 + 5, by, 20, 1, c)
    _LCD.fillRect(x0 + 3, by + 1, 24, 1, c)
    _LCD.fillRect(x0 + 1, by + 2, 28, 1, c)
    _LCD.fillRect(x0, by + 3, 30, 9, c)
    _LCD.fillRect(x0 + 1, by + 12, 28, 1, c)
    _LCD.fillRect(x0 + 3, by + 13, 24, 1, c)
    eye_c = c if blink else DARK
    _LCD.fillRect(x0 + 5, by + 5, 5, 4, eye_c)
    _LCD.fillRect(x0 + 20, by + 5, 5, 4, eye_c)
    ly = by + 15
    if walk == 0:
        _LCD.fillRect(x0 + 1, ly, 3, 5, c)
        _LCD.fillRect(x0 + 5, ly + 2, 3, 3, c)
        _LCD.fillRect(x0 + 9, ly, 3, 5, c)
        _LCD.fillRect(x0 + 13, ly + 2, 3, 3, c)
        _LCD.fillRect(x0 + 17, ly, 3, 5, c)
        _LCD.fillRect(x0 + 21, ly + 2, 3, 3, c)
        _LCD.fillRect(x0 + 25, ly, 3, 5, c)
        _LCD.fillRect(x0 + 29, ly + 2, 1, 3, c)
    else:
        _LCD.fillRect(x0 + 1, ly + 2, 3, 3, c)
        _LCD.fillRect(x0 + 5, ly, 3, 5, c)
        _LCD.fillRect(x0 + 9, ly + 2, 3, 3, c)
        _LCD.fillRect(x0 + 13, ly, 3, 5, c)
        _LCD.fillRect(x0 + 17, ly + 2, 3, 3, c)
        _LCD.fillRect(x0 + 21, ly, 3, 5, c)
        _LCD.fillRect(x0 + 25, ly + 2, 3, 3, c)
        _LCD.fillRect(x0 + 29, ly, 1, 5, c)


def draw_environment(stage, y_base, screen_w):
    y = min(y_base, 110)
    if stage == 2:
        _LCD.fillRect(34, y - 2, 2, 2, GRAY_MID)
        _LCD.fillRect(116, y - 1, 1, 1, GRAY_MID)
        _LCD.fillRect(154, y - 3, 2, 1, GRAY_MID)
    elif stage >= 3:
        _LCD.fillRect(0, y, screen_w, 1, GREEN)
        _LCD.fillRect(42, y - 4, 1, 3, YELLOW)
        _LCD.fillRect(41, y - 3, 3, 1, YELLOW)
        _LCD.fillRect(126, y - 5, 1, 5, YELLOW)
        _LCD.fillRect(124, y - 3, 5, 1, YELLOW)
