"""
Клонирование голоса — перенос тембра живого человека на нашу озвучку.

Готовых клонирующих TTS с армянским не существует: XTTS, F5, ElevenLabs-клоны
работают на своём списке языков, армянского там нет. Поэтому задача решается
в два шага, и второй шаг от языка не зависит вообще:

    текст → синтез (tts.py, hy_AM-gor-medium) → перенос тембра (этот модуль)

Тембр берётся из образца креатора: конвертер слушает запись, снимает с неё
«отпечаток голоса» и надевает его на синтезированную речь. Слова и интонация
остаются наши, звучание — человека.

    python voiceclone.py --cp CP-01 --in voice.wav --out voice-cp01.wav
    python voiceclone.py --ref sample.wav --in voice.wav --out clone.wav
    python voiceclone.py --all --in voice.wav --outdir clones/

Основа — ToneColorConverter из OpenVoice v2. Взят только конвертер: его TTS
тянет за собой английскую и китайскую фонемизацию и старые версии librosa
с numpy, которые сломали бы остальной конвейер.

Водяной знак (wavmark) не ставим — это метка сервиса в чужой звуковой дорожке,
нам она не нужна.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

OPENVOICE = Path(r"C:\Ferma\tools\OpenVoice")
MODEL_DIR = Path(r"C:\Ferma\factory\assets\voiceclone")
PERSONAS = Path(r"C:\Ferma\factory\personas")
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

# Сколько секунд образца брать на отпечаток. Больше не значит лучше: длинная
# запись усредняет голос по разным условиям съёмки, и тембр смазывается.
REF_SEC = 30.0
# Сила переноса. Ниже — ближе к исходной дикции, выше — ближе к образцу,
# но растёт хрип. 0.3 — то, что рекомендуют авторы, и на наших голосах
# держится ровно.
TAU = 0.3


def load_converter():
    """ToneColorConverter без TTS-части OpenVoice."""
    if str(OPENVOICE) not in sys.path:
        sys.path.insert(0, str(OPENVOICE))

    import torch
    from openvoice import utils
    from openvoice.mel_processing import spectrogram_torch
    from openvoice.models import SynthesizerTrn

    cfg = MODEL_DIR / "config.json"
    ckpt = MODEL_DIR / "checkpoint.pth"
    if not ckpt.exists():
        raise SystemExit(f"нет модели конвертера: {ckpt}\n"
                         "  скачать: myshell-ai/OpenVoiceV2 → converter/")

    hps = utils.get_hparams_from_file(str(cfg))
    model = SynthesizerTrn(
        len(getattr(hps, "symbols", [])),
        hps.data.filter_length // 2 + 1,
        n_speakers=hps.data.n_speakers,
        **hps.model,
    ).to("cpu")
    model.eval()
    state = torch.load(str(ckpt), map_location="cpu", weights_only=False)
    model.load_state_dict(state["model"], strict=False)
    return model, hps, spectrogram_torch


def one_voice(audio, sr: float, register: str = "auto"):
    """
    Оставить в образце один голос.

    Образцы собраны из роликов креатора, и в кадр попадает не только он:
    в записи CP-03 нашлись два человека — 42% отрезков в мужском регистре,
    45% в женском. Отпечаток с такой записи усредняет обоих и даёт голос,
    которого нет ни у кого: высота промахнулась мимо образца на 39%.

    Режем на окна, меряем высоту тона, оставляем окна одного регистра.
    `auto` берёт тот, которого в записи больше.
    """
    import librosa
    import numpy as np

    win = int(sr * 3.0)
    spans: list[tuple[np.ndarray, float]] = []
    for i in range(0, len(audio) - win, win):
        chunk = audio[i:i + win]
        f0, _, _ = librosa.pyin(chunk, fmin=60, fmax=400, sr=sr, frame_length=1024)
        f0 = f0[~np.isnan(f0)]
        if len(f0) > 20:
            spans.append((chunk, float(np.median(f0))))

    if len(spans) < 3:
        return audio, None

    pitches = np.array([p for _, p in spans])
    # 165 Гц — граница мужского и женского регистра
    low = [(c, p) for c, p in spans if p < 165]
    high = [(c, p) for c, p in spans if p >= 165]
    mixed = min(len(low), len(high)) / len(spans) > 0.2

    if register == "low":
        keep = low
    elif register == "high":
        keep = high
    elif mixed:
        keep = low if len(low) >= len(high) else high
        print(f"    в образце два голоса — беру тот, которого больше "
              f"({len(keep)} отрезков из {len(spans)})")
    else:
        return audio, float(np.median(pitches))

    if len(keep) < 3:
        return audio, float(np.median(pitches))

    return np.concatenate([c for c, _ in keep]), float(np.median([p for _, p in keep]))


def voice_print(wav: Path, model, hps, spectrogram_torch, seconds: float = REF_SEC,
                register: str = "auto", clean: bool = True):
    """Отпечаток голоса из образца."""
    import librosa
    import torch

    # Читаем с запасом: после отбора одного голоса материала должно остаться
    # не меньше, чем берём на отпечаток.
    audio, _ = librosa.load(str(wav), sr=hps.data.sampling_rate,
                            duration=seconds * 3 if clean else seconds)
    if clean:
        audio, pitch = one_voice(audio, hps.data.sampling_rate, register)
        audio = audio[:int(hps.data.sampling_rate * seconds)]
        if pitch:
            print(f"    образец: {len(audio) / hps.data.sampling_rate:.0f} с, "
                  f"высота тона {pitch:.0f} Гц")

    y = torch.FloatTensor(audio).unsqueeze(0)
    spec = spectrogram_torch(
        y, hps.data.filter_length, hps.data.sampling_rate,
        hps.data.hop_length, hps.data.win_length, center=False,
    )
    with torch.no_grad():
        return model.ref_enc(spec.transpose(1, 2)).unsqueeze(-1).detach()


def convert(src: Path, out: Path, src_se, tgt_se, model, hps, spectrogram_torch, tau: float = TAU) -> None:
    import librosa
    import soundfile
    import torch

    audio, _ = librosa.load(str(src), sr=hps.data.sampling_rate)
    y = torch.FloatTensor(audio).unsqueeze(0)
    spec = spectrogram_torch(
        y, hps.data.filter_length, hps.data.sampling_rate,
        hps.data.hop_length, hps.data.win_length, center=False,
    )
    lengths = torch.LongTensor([spec.size(-1)])
    with torch.no_grad():
        res = model.voice_conversion(spec, lengths, sid_src=src_se, sid_tgt=tgt_se, tau=tau)
        wav = res[0][0, 0].data.cpu().float().numpy()

    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "conv.wav"
        soundfile.write(str(raw), wav, hps.data.sampling_rate)
        # Конвертер отдаёт 22 кГц и заметно тише исходника: приводим к тому же
        # уровню, что и остальная озвучка, иначе мастеринг ролика промахнётся.
        r = subprocess.run(
            [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw),
             "-af", "highpass=f=70,loudnorm=I=-16:TP=-1.5:LRA=11",
             "-ar", "48000", "-ac", "1", str(out)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if r.returncode != 0:
            sys.stderr.write((r.stderr or "")[-600:])
            raise SystemExit("ffmpeg не смог привести громкость")


def persona_sample(cp: str) -> Path:
    found = sorted((PERSONAS / cp).glob("voice-*.wav"))
    if not found:
        raise SystemExit(f"нет образца голоса для {cp} в {PERSONAS / cp}")
    return found[0]


def main() -> int:
    ap = argparse.ArgumentParser(description="перенос тембра личности на озвучку")
    ap.add_argument("--in", dest="src", required=True, help="что озвучено (wav)")
    ap.add_argument("--out", help="куда положить результат")
    ap.add_argument("--outdir", help="папка для --all")
    ap.add_argument("--cp", help="личность: CP-01 … CP-07")
    ap.add_argument("--ref", help="образец голоса напрямую")
    ap.add_argument("--all", action="store_true", help="все семь личностей разом")
    ap.add_argument("--tau", type=float, default=TAU)
    ap.add_argument("--register", default="auto", choices=["auto", "low", "high"],
                    help="какой голос брать, если в образце их несколько")
    args = ap.parse_args()

    src = Path(args.src)
    if not src.exists():
        raise SystemExit(f"нет файла: {src}")

    print("загружаю конвертер тембра…")
    model, hps, spec_fn = load_converter()

    # Отпечаток самой озвучки — от чего конвертер отталкивается.
    # Её чистить не нужно: там один синтезированный голос.
    src_se = voice_print(src, model, hps, spec_fn, clean=False)

    targets: list[tuple[str, Path]] = []
    if args.all:
        targets = [(cp.name, persona_sample(cp.name))
                   for cp in sorted(PERSONAS.glob("CP-0*")) if cp.is_dir()]
    elif args.ref:
        targets = [(Path(args.ref).stem, Path(args.ref))]
    elif args.cp:
        targets = [(args.cp, persona_sample(args.cp))]
    else:
        raise SystemExit("нужен --cp, --ref или --all")

    outdir = Path(args.outdir) if args.outdir else None
    for name, ref in targets:
        out = (outdir / f"voice-{name}.wav") if outdir else Path(
            args.out or src.with_name(f"{src.stem}-{name}.wav"))
        print(f"  {name}: {ref.name}")
        tgt_se = voice_print(ref, model, hps, spec_fn, register=args.register)
        convert(src, out, src_se, tgt_se, model, hps, spec_fn, args.tau)
        print(f"    → {out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
