# Arabic on thermal receipt printers (ESC/POS) — a troubleshooting guide

> Maintained by the team that builds [RAWA](https://rawaerp.com), a Jordanian restaurant POS. What follows is what
> we learned shipping Arabic receipts, kitchen tickets and QR labels to real printers over the network, USB and
> Bluetooth. It describes what our own code does; test on **your** printer model.

**The short version:** stop sending Arabic as text. Render the receipt to an image on the host, send it as
an ESC/POS **raster bitmap** in small **bands**, one short connection per band. Garbled Arabic, question marks,
reversed words and half-printed receipts almost always disappear.

## Symptoms → causes

| What you see | Usual cause | Fix |
|---|---|---|
| `?????` or random Latin letters instead of Arabic | The printer has no Arabic code page selected (or none at all) | Rasterise (this guide) or select the printer's Arabic code page (CP864 / WPC1256) **and** shape the text yourself |
| Arabic letters are disconnected (isolated forms) | Text was sent without *shaping* — printers do not join letters | Shape on the host (`arabic-reshaper`) or rasterise |
| Words come out in reverse order / numbers jump sides | No bidirectional (RTL) reordering | Apply the Unicode bidi algorithm (`python-bidi`) before drawing, or rasterise |
| First part of the receipt is fine, then garbage, or the printer hangs | One large job overran the cheap printer's small receive buffer | Send bands of ≤128 rows, one connection per band, ~50 ms pause |
| Prints, but the cut/drawer does not fire | Missing/incorrect command for that model | `GS V 66 0` partial cut, `ESC p 0 25 250` drawer pulse; some models need pin 5 (`ESC p 1 …`) |
| Works on Wi-Fi tablet, not on the PC (or vice-versa) | Printer on another subnet / client isolation / wrong port | Same subnet, disable AP client isolation, use TCP **9100** |
| Prints for the first hour, then stops until power-cycled | Idle TCP connection dropped by the printer | Connect per job (or per band) instead of holding one socket open |
| Image is cut off on the right | Width not matched to the paper | 80 mm head: 576 dots; 58 mm head: 384 dots; width must be a multiple of 8 |

## Why raster instead of a code page?

Text mode needs: (1) the printer to have an Arabic code page, (2) you to select it, (3) shaping, (4) RTL
reordering, (5) the same behaviour across every brand you support. Rasterising removes all five — the host draws
exactly what the paper should look like. The trade-offs are honest ones: more bytes per receipt (a few tens of KB),
and slower on very slow links (Bluetooth), which is why it pays to keep receipts compact.

## The recipe

1. **Shape + reorder** the text: `get_display(arabic_reshaper.reshape(text))`.
2. **Draw** onto a white image the width of the paper in dots (576 / 384) using a font with Arabic glyphs.
3. **Binarise** to 1 bit and encode as `GS v 0 m xL xH yL yH <data>` (normal density), **128 rows at a time**.
4. First band begins with `ESC @` (initialise); optionally `ESC p 0 25 250` to pulse the cash drawer.
5. After the last band: `LF LF LF` then `GS V 66 0` (feed and partial cut).
6. **Network**: open a TCP connection to `printer:9100`, send one band, close, wait ~50 ms, repeat.

Working code: [`examples/raster_receipt.py`](examples/raster_receipt.py) — it runs without a printer
(`--out receipt.bin --png preview.png`) so you can inspect the result first.

```bash
pip install pillow arabic-reshaper python-bidi
python examples/raster_receipt.py --out receipt.bin --png preview.png
python examples/raster_receipt.py --host 192.168.1.50 --port 9100
```

## Network checklist (before blaming software)

- [ ] Printer has a **static IP** (or a DHCP reservation). A changing address looks like "it randomly stops".
- [ ] Printer and POS device are on the same subnet; guest Wi-Fi isolation is off.
- [ ] `telnet <ip> 9100` (or `Test-NetConnection <ip> -Port 9100` on Windows) connects.
- [ ] Print the printer's self-test page (usually hold FEED while powering on) and check the paper width and code page.
- [ ] Use a printer from the same family for kitchen and receipt, so one fix covers both.

## USB and Bluetooth notes

- **USB** from a browser/app usually needs a native bridge (WebUSB or an app plugin). Claim the printer's
  interface, write the same raw bytes. Keep one writer at a time.
- **Bluetooth** serial links are slow and drop easily: prefer smaller images, and do not hold the connection open
  between jobs.

## Kitchen tickets and labels

Kitchen tickets use the same raster path, which is why Arabic dish names and modifiers ("بدون بصل") print
reliably. Label printers speak TSPL/ZPL rather than ESC/POS — a different guide.

## Checklist for POS vendors

- [ ] Arabic prints correctly on the three printer brands your customers actually own.
- [ ] A failed print shows an on-screen error with a retry — it never silently falls back to a browser print dialog.
- [ ] Jobs are queued per printer so two terminals do not interleave bytes on one printer.
- [ ] The cash drawer opens on cash payments only.

RAWA prints Arabic receipts and kitchen tickets exactly this way (network, USB and Bluetooth) and supports standard
80 mm ESC/POS printers; hardware questions: sales@rawaerp.com. More: <https://rawaerp.com/guide/pos-hardware-jordan>.

## Further reading

- [Arabic ESC/POS reference paper (Telegraph)](https://telegra.ph/Arabic-on-ESCPOS-thermal-printers-a-reference-for-reliable-receipts-and-kitchen-tickets-11-09)
- [Gist: Arabic ESC/POS fix](https://gist.github.com/rawaerp/5ed4e3c165af1937ce8431fc2b661391)
- [Research portal](https://rawaerp.github.io/)
- [10 criteria for choosing a restaurant POS in Jordan](https://rawaerp.com/guide/restaurant-pos-jordan-10-criteria)
- [Hardware guide](https://rawaerp.com/guide/pos-hardware-jordan)

---
Licence: text CC BY 4.0, code MIT. Different model behaves differently? Open an issue with the model name and what you saw.
