"""Ունիկալիզացիա նկարների (Pillow): եզրերից կտրում 1–2%, վերադարձ նույն չափին, լույս/գույն ±2%, առանց մետատվյալների.
Նույն կարուսելի սլայդներին՝ նույն պարամետրերը (սերմը = կարուսելի անունը). Արածը բաց է թողնվում."""
import json, sys, hashlib, random
from pathlib import Path
from PIL import Image, ImageEnhance

SRC = Path(r"C:\Users\User\Desktop\Պոստ")
DST = Path(r"C:\Users\User\Desktop\Հրապարակում\2 · 7-րդ հեռախոս")
LOG = DST / "unik-log.json"


def params(key: str) -> dict:
    r = random.Random(int(hashlib.sha256(key.encode()).hexdigest(), 16))
    return {"crop_pct": {s: round(r.uniform(1.0, 2.0), 2) for s in "lrtb"},
            "brightness": round(1 + r.uniform(-0.02, 0.02), 4),
            "saturation": round(1 + r.uniform(-0.02, 0.02), 4),
            "red_gain": round(1 + r.uniform(-0.01, 0.01), 4)}


def apply(src: Path, dst: Path, p: dict):
    im = Image.open(src).convert("RGB"); w, h = im.size
    c = p["crop_pct"]
    box = (round(w*c["l"]/100), round(h*c["t"]/100), w-round(w*c["r"]/100), h-round(h*c["b"]/100))
    im = im.crop(box).resize((w, h), Image.LANCZOS)
    im = ImageEnhance.Brightness(im).enhance(p["brightness"])
    im = ImageEnhance.Color(im).enhance(p["saturation"])
    r, g, b = im.split(); r = r.point(lambda v: min(255, round(v * p["red_gain"])))
    im = Image.merge("RGB", (r, g, b))
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, "PNG")  # новый Image без info -> метаданные не переносятся
    return (w, h), box


def main():
    log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {"files": []}
    done = {f["output"] for f in log["files"]}
    n_post = n_slide = 0
    jobs = []
    for d in sorted(SRC.iterdir(), key=lambda x: x.name):
        if d.is_dir() and d.name.lower().startswith("կառուսել"):
            num = d.name.split()[-1]
            for f in sorted(d.glob("*.png")):
                jobs.append((f, DST / "Կարուսելներ" / f"կառուսել {num}" / f.name, f"carousel-{num}", "carousel"))
        elif d.is_file() and d.suffix.lower() == ".png" and d.name.startswith("hf_"):
            jobs.append((d, DST / "Պոստեր" / d.name, d.name, "post"))
    for f, dst, key, kind in jobs:
        rel = str(dst.relative_to(DST))
        if rel in done and dst.exists():
            continue
        p = params(key)
        size, box = apply(f, dst, p)
        log["files"].append({"type": kind, "source": str(f), "output": rel,
                             "changed": "եզրերից կտրում + վերադարձ նույն չափին, լույս/գույն ±2%, մետատվյալներ հանված",
                             "params": {**p, "size": size, "crop_box": box}})
        print("ok", rel)
    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
