"""Print an Arabic receipt on an ESC/POS thermal printer the robust way (MIT).

Why raster? Arabic needs letter shaping (joining forms) and right-to-left ordering, and cheap
printers ship with inconsistent Arabic code pages. Rendering the receipt to an image on the host
and sending it as an ESC/POS raster bitmap (GS v 0) sidesteps every code-page problem.

Why bands? A cheap *network* printer has a small receive buffer. Sending one huge raster job can
overrun it and print garbage. We send many small, self-contained bands (128 rows each), one short
TCP connection per band, with a tiny pause.

    pip install pillow arabic-reshaper python-bidi
    python raster_receipt.py --out receipt.bin                 # no printer needed: writes the bytes
    python raster_receipt.py --host 192.168.1.50 --port 9100    # print on the network printer
"""
import argparse
import socket
import time

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

DOTS_80MM = 576          # printable width of an 80 mm head at 203 dpi (multiple of 8)
DOTS_58MM = 384
BAND_ROWS = 128


def shape(text: str) -> str:
    """Arabic text -> visual order string ready to draw left-to-right."""
    return get_display(arabic_reshaper.reshape(text))


def render_receipt(lines, font_path, width=DOTS_80MM, size=26, pad=8) -> Image.Image:
    """lines = [(text, align)] with align in {'right','center','left'}"""
    font = ImageFont.truetype(font_path, size)
    probe = ImageDraw.Draw(Image.new("L", (width, 10)))
    heights = [probe.textbbox((0, 0), shape(t), font=font)[3] + pad for t, _ in lines]
    img = Image.new("L", (width, sum(heights) + 2 * pad), 255)
    d = ImageDraw.Draw(img)
    y = pad
    for (text, align), h in zip(lines, heights):
        s = shape(text)
        w = d.textbbox((0, 0), s, font=font)[2]
        x = {"right": width - w - pad, "center": (width - w) // 2}.get(align, pad)
        d.text((x, y), s, font=font, fill=0)
        y += h
    return img


def raster_bands(img: Image.Image, open_drawer=False, cut=True):
    """Image -> list of ESC/POS byte buffers (GS v 0, normal density), BAND_ROWS rows each."""
    img = img.convert("1")                      # 1-bit, threshold dither
    w, h = img.size
    assert w % 8 == 0, "width must be a multiple of 8"
    bpr = w // 8
    px = img.load()
    bands, y0 = [], 0
    while y0 < h:
        bh = min(BAND_ROWS, h - y0)
        buf = bytearray()
        if y0 == 0:
            buf += b"\x1b\x40"                                    # ESC @  initialise
            if open_drawer:
                buf += b"\x1b\x70\x00\x19\xfa"                    # ESC p 0 25 250  pulse drawer pin 2
        buf += bytes([0x1D, 0x76, 0x30, 0x00, bpr & 0xFF, bpr >> 8, bh & 0xFF, bh >> 8])   # GS v 0 m xL xH yL yH
        for y in range(y0, y0 + bh):
            for xb in range(bpr):
                b = 0
                for bit in range(8):
                    if px[xb * 8 + bit, y] == 0:                  # black pixel -> 1 bit
                        b |= 0x80 >> bit
                buf.append(b)
        y0 += bh
        if y0 >= h:
            buf += b"\n\n\n"
            if cut:
                buf += b"\x1d\x56\x42\x00"                        # GS V 66 0  feed + partial cut
        bands.append(bytes(buf))
    return bands


def send_bands(host, port, bands, pause=0.05, timeout=5):
    for b in bands:
        with socket.create_connection((host, port), timeout=timeout) as s:   # short connection per band
            s.sendall(b)
        time.sleep(pause)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host")
    ap.add_argument("--port", type=int, default=9100)
    ap.add_argument("--font", default="C:/Windows/Fonts/tahoma.ttf")
    ap.add_argument("--out", help="write the ESC/POS bytes to a file instead of printing")
    ap.add_argument("--png", help="also save the rendered receipt as a PNG preview")
    a = ap.parse_args()
    receipt = [("مطعم تجريبي", "center"), ("فاتورة رقم 1042", "center"), ("-" * 28, "center"),
               ("ساندويش شاورما  ×2          5.000", "right"), ("كولا  ×2                 1.000", "right"),
               ("-" * 28, "center"), ("الإجمالي شامل الضريبة 16%      6.960", "right"), ("شكراً لزيارتكم", "center")]
    image = render_receipt(receipt, a.font)
    if a.png:
        image.save(a.png)
    data = raster_bands(image)
    print(f"{image.size[0]}x{image.size[1]} px -> {len(data)} band(s), {sum(map(len, data))} bytes")
    if a.out:
        open(a.out, "wb").write(b"".join(data))
    elif a.host:
        send_bands(a.host, a.port, data)
