"""Ունիկալիզացիա 7-րդ հեռախոսի համար (ռուս.: уникализация для 7-го телефона): только ускорение 1.25x.

    python unik_video.py --out "C:/Users/User/Desktop/7-րդ հեռախոս/վիդեո" --log unik-log.json RL-01 RL-02 ...
Повторный запуск пропускает уже сделанное. Тяжёлое — только через ochered (М-44).
"""
from __future__ import annotations
if __name__ == "__main__":
    import ochered
    ochered.v_ocheredi()

import json, subprocess, sys, argparse, time
from pathlib import Path
from uniquify import make, duration, FFMPEG, FFPROBE
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT = Path(r"C:\Ferma\factory\montazh-cloud\out")
SPEED = 1.25


VARIANT = ""  # "-բ": ռիլի «բ» տարբերակի վարպետը (RL-NN-հրապարակման-բ.mp4), ելքի անունը նույնն է


def master(rl: str):
    for d in (OUT / "հրապարակված", OUT):
        p = d / f"{rl}-հրապարակման{VARIANT}.mp4"
        if p.exists():
            return p
    return None


def has_audio(p: Path) -> bool:
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type",
                        "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return "audio" in r.stdout


def sheet(p: Path, dst: Path, dur: float) -> None:
    ts = [dur * k for k in (0.15, 0.5, 0.85)]
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error"]
    for t in ts:
        cmd += ["-ss", f"{t:.2f}", "-i", str(p)]
    cmd += ["-filter_complex", "[0:v][1:v][2:v]hstack=3,scale=1080:-1", "-frames:v", "1", str(dst)]
    cmd2 = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error"]
    for t in ts:
        cmd2 += ["-ss", f"{t:.2f}", "-i", str(p)]
    cmd2 += ["-filter_complex", "[0:v]scale=360:-2[a];[1:v]scale=360:-2[b];[2:v]scale=360:-2[c];[a][b][c]hstack=3",
             "-frames:v", "1", str(dst)]
    subprocess.run(cmd2, capture_output=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--variant", default="", help="վարպետի վերջածանց, օր.՝ -բ")
    ap.add_argument("rl", nargs="+")
    a = ap.parse_args()
    global VARIANT
    VARIANT = a.variant
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    sh = out.parent / "թերթեր"; sh.mkdir(exist_ok=True)
    log_p = Path(a.log)
    log = json.loads(log_p.read_text(encoding="utf-8")) if log_p.exists() else {"files": []}
    done = {f["output"] for f in log["files"]}
    bad = 0
    for rl in a.rl:
        src = master(rl)
        if not src:
            print(f"{rl}: ՀՐԱՊԱՐԱԿՄԱՆ ՎԱՐՊԵՏ ՉԿԱ"); bad += 1; continue
        dst = out / f"{rl}-1.25x.mp4"
        if dst.name in done and dst.exists():
            print(f"{rl}: արդեն արված, բաց թողնվեց"); continue
        d0 = duration(str(src))
        if d0 / SPEED < 15:
            print(f"{rl}: ԿԱՐՃ — {d0/SPEED:.1f} վրկ < 15, չեմ անում"); bad += 1; continue
        t = time.time()
        if not make(str(src), dst, f"setpts=PTS/{SPEED}", f"atempo={SPEED}"):
            print(f"{rl}: ձախողվեց"); bad += 1; continue
        d1 = duration(str(dst))
        ok_dur = abs(d1 - d0 / SPEED) <= 0.1
        aud = has_audio(dst)
        sheet(dst, sh / f"{rl}-1.25x.png", d1)
        print(f"{rl}: {d0:.2f} → {d1:.2f} (սպասվում {d0/SPEED:.2f}) տևողություն={'OK' if ok_dur else 'ՍԽԱԼ'} ձայն={'կա' if aud else 'ՉԿԱ'} {time.time()-t:.0f}վ")
        log["files"] = [f for f in log["files"] if f["output"] != dst.name]
        log["files"].append({"type": "video", "source": str(src), "output": dst.name,
                             "changed": "արագացում 1.25× (վիդեո setpts, ձայն atempo), սուբտիտրը վառված է",
                             "params": {"speed": SPEED, "src_sec": round(d0, 2), "out_sec": round(d1, 2),
                                        "duration_ok": ok_dur, "audio": aud}})
        log_p.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
