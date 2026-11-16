"""Ունիկալիզացիա Ռիլեր-7-ի համար (7-րդ հեռախոս, CP-07), 19.10.2026.

Ռիլեր-7-ի մաստերներն արդեն 1.15× են (jumpcut --speed 1.15). 13.10-ի կանոնով
7-րդ հեռախոսի տարբերակը = 1.25× հում նյութից, այսինքն մաստերի վրա 1.25/1.15.
Միայն արագացում (կտրվածք, գույն, հայելի՝ ոչ), ձայնը՝ atempo (տոնը նույնն է).

    python unik_r7.py --src "…/Ռիլեր-7" --out "…/Ռիլեր-7-ՈՒՆԻԿ-7րդ-հեռախոս" IMG_0272 IMG_0275 ...
Կրկնելի է. աղբյուրը չի փոխվել (չափ+mtime log-ում) → բաց է թողնում, փոխվել է → նորից.
Ծանրը՝ միայն ochered-ով (М-44).
"""
from __future__ import annotations
if __name__ == "__main__":
    import ochered
    ochered.v_ocheredi()

import argparse, json, subprocess, sys, time
from pathlib import Path
from uniquify import duration, FFMPEG
from unik_video import has_audio, sheet
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SPEED = round(1.25 / 1.15, 4)  # 1.087


def make(src: Path, dst: Path) -> bool:
    tmp = dst.with_suffix(".tmp.mp4")
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
           "-vf", f"setpts=PTS/{SPEED}", "-af", f"atempo={SPEED}", "-map_metadata", "-1",
           "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(tmp)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-1200:])
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(dst)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("img", nargs="+")
    a = ap.parse_args()
    src_d, out = Path(a.src), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    sh = out / "թերթեր"; sh.mkdir(exist_ok=True)
    log_p = out / "unik-log.json"
    log = json.loads(log_p.read_text(encoding="utf-8")) if log_p.exists() else {"files": []}
    bad = 0
    for n in a.img:
        src = src_d / f"{n}.mp4"
        if not src.exists():
            print(f"{n}: ԱՂԲՅՈՒՐ ՉԿԱ"); bad += 1; continue
        st = src.stat()
        dst = out / f"{n}-7րդ.mp4"
        prev = next((f for f in log["files"] if f["output"] == dst.name), None)
        if prev and dst.exists() and prev["src_size"] == st.st_size and prev["src_mtime"] == int(st.st_mtime):
            print(f"{n}: արդեն արված, աղբյուրը չի փոխվել"); continue
        d0 = duration(str(src)); t = time.time()
        if not make(src, dst):
            print(f"{n}: ձախողվեց"); bad += 1; continue
        d1 = duration(str(dst))
        ok = abs(d1 - d0 / SPEED) <= 0.1
        aud = has_audio(dst)
        sheet(dst, sh / f"{n}-7րդ.png", d1)
        print(f"{n}: {d0:.2f} → {d1:.2f} (սպասվում {d0/SPEED:.2f}) տևողություն={'OK' if ok else 'ՍԽԱԼ'} "
              f"ձայն={'կա' if aud else 'ՉԿԱ'}{'' if d1 >= 15 else ' ԿԱՐՃ<15'} {time.time()-t:.0f}վ")
        log["files"] = [f for f in log["files"] if f["output"] != dst.name]
        log["files"].append({"type": "video", "source": str(src), "output": dst.name,
                             "src_size": st.st_size, "src_mtime": int(st.st_mtime),
                             "changed": f"արագացում {SPEED}× մաստերի վրա (ընդհանուր 1.25×), ձայն atempo, մետատվյալներ հանված, սուբտիտրը վառված է",
                             "params": {"speed": SPEED, "crf": 16, "src_sec": round(d0, 2), "out_sec": round(d1, 2),
                                        "duration_ok": ok, "audio": aud}})
        log_p.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
