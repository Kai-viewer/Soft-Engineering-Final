#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
產生一張「示範用」360° 全景照片 (等距長方投影 equirectangular, 2:1)。
用途：還沒拍到真實教室全景前，先用來測試後台上傳與 Pannellum 瀏覽功能。
只用標準函式庫（zlib 寫 PNG）。輸出：app/spaces/tools/samples/demo_panorama.png

    uv run python app/spaces/tools/make_demo_panorama.py
"""
import math
import os
import struct
import zlib

W, H = 1600, 800
HALF_X, HALF_Z, FLOOR_Y, CEIL_Y = 6.0, 8.0, -1.4, 1.8   # 教室尺寸 (公尺，相機在原點)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples", "demo_panorama.png")


def shade(px, py, pz, face):
    """依照交點所在的面回傳 RGB"""
    if face == "floor":
        tile = (math.floor(px) + math.floor(pz)) % 2
        c = (176, 140, 102) if tile else (186, 150, 112)
        # 課桌：在相機前後排成幾排
        if -4.5 < px < 4.5 and abs(px) > 0.8 and 1.5 < pz < 6.5 and (pz % 1.6) < 0.6:
            c = (120, 85, 55)
        return c
    if face == "ceil":
        if (px % 3.0) < 1.2 and (pz % 4.0) < 1.2:   # 日光燈
            return (250, 250, 238)
        return (232, 234, 236)
    # 牆面
    c = (214, 222, 230)
    if py < FLOOR_Y + 0.12:                         # 踢腳板
        return (120, 128, 138)
    if face == "front":                             # 前方：黑板 + 投影幕
        if -3.2 < px < 1.6 and -0.2 < py < 1.1:
            return (40, 82, 62)
        if 2.0 < px < 5.2 and -0.3 < py < 1.5:
            return (245, 245, 245)
    if face == "back" and -1.2 < px < 1.2 and py < 0.9:   # 後方：門
        return (130, 96, 70)
    if face in ("left", "right"):                   # 兩側：窗戶
        if -0.1 < py < 1.3 and (pz % 3.2) > 0.9:
            sky = 0.5 + 0.5 * (py + 0.1) / 1.4
            return (int(140 + 60 * sky), int(185 + 40 * sky), 235)
    return c


def render():
    rows = bytearray()
    lons = [((x + 0.5) / W - 0.5) * 2 * math.pi for x in range(W)]
    sin_l = [math.sin(l) for l in lons]
    cos_l = [math.cos(l) for l in lons]
    for y in range(H):
        lat = (0.5 - (y + 0.5) / H) * math.pi
        cl, sl = math.cos(lat), math.sin(lat)
        rows.append(0)  # PNG filter: none
        for x in range(W):
            dx, dy, dz = cl * sin_l[x], sl, cl * cos_l[x]
            best, face = 1e9, None
            if dy < -1e-9:
                t = FLOOR_Y / dy
                if t < best: best, face = t, "floor"
            elif dy > 1e-9:
                t = CEIL_Y / dy
                if t < best: best, face = t, "ceil"
            if dx > 1e-9:
                t = HALF_X / dx
                if t < best: best, face = t, "right"
            elif dx < -1e-9:
                t = -HALF_X / dx
                if t < best: best, face = t, "left"
            if dz > 1e-9:
                t = HALF_Z / dz
                if t < best: best, face = t, "front"
            elif dz < -1e-9:
                t = -HALF_Z / dz
                if t < best: best, face = t, "back"
            px, py, pz = dx * best, dy * best, dz * best
            r, g, b = shade(px, py, pz, face)
            # 簡單的距離陰影，讓畫面有深度感
            k = max(0.72, 1.0 - best * 0.025)
            rows += bytes((int(r * k), int(g * k), int(b * k)))
    return bytes(rows)


def write_png(path, raw):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    write_png(OUT, render())
    print("已產生", os.path.normpath(OUT))
