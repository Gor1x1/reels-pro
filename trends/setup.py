# -*- coding: utf-8 -*-
r"""Установка одной командой: зависимости, агенты, рабочая папка.

    python setup.py                       поставить всё
    python setup.py --workdir D:\моё      выбрать рабочую папку
    python setup.py --check               ничего не менять, только проверить

Что делает:
  1. ставит Python-пакеты: yt-dlp (ночная сборка), faster-whisper, OpenCV;
  2. находит ffmpeg или подсказывает, как поставить;
  3. копирует 19 агентов в папку агентов Claude Code;
  4. раскладывает config и lib в рабочую папку, создаёт products и runs;
  5. говорит, что осталось сделать руками — это только ключ Virlo.

Ключи и пароли скрипт не трогает: ключ Virlo вставляется отдельно,
через Claude или руками в .claude.json.
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
AGENTS_DST = os.path.join(os.path.expanduser("~"), ".claude", "agents")
PACKAGES = [
    (["-U", "--pre", "yt-dlp[default]"], "yt_dlp", "качает чужие ролики"),
    (["faster-whisper"], "faster_whisper", "расшифровывает речь"),
    (["opencv-python", "numpy"], "cv2", "считает ритм планов"),
]
done, todo = [], []


def say(line=""):
    try:
        print(line)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((line + "\n").encode("utf-8"))


def have(mod):
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


def install_packages(check_only):
    for args, mod, why in PACKAGES:
        if have(mod):
            done.append("%s уже стоит" % mod)
            continue
        if check_only:
            todo.append("поставить %s (%s)" % (args[-1], why))
            continue
        say("ставлю %s — %s…" % (args[-1], why))
        code = subprocess.call([sys.executable, "-m", "pip", "install", "-q"] + args)
        if code == 0 and have(mod):
            done.append("%s поставлен" % mod)
        else:
            todo.append("поставить вручную: python -m pip install %s" % " ".join(args))


def find_ffmpeg(check_only):
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        done.append("ffmpeg найден в PATH")
        return
    # запасной путь: бинарник, который тянет за собой imageio-ffmpeg
    if not check_only and not have("imageio_ffmpeg"):
        say("ставлю запасной ffmpeg…")
        subprocess.call([sys.executable, "-m", "pip", "install", "-q", "imageio-ffmpeg"])
    if have("imageio_ffmpeg"):
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        folder = os.path.dirname(exe)
        done.append("ffmpeg есть через imageio-ffmpeg: %s" % exe)
        todo.append('добавить в PATH папку с ffmpeg: setx PATH "%%PATH%%;' + folder + '"')
        todo.append("ffprobe в комплект imageio не входит — для полного разбора "
                    "поставьте ffmpeg целиком: winget install Gyan.FFmpeg")
    else:
        todo.append("поставить ffmpeg: winget install Gyan.FFmpeg "
                    "(или скачать с ffmpeg.org и добавить в PATH)")


def copy_agents(check_only):
    src = os.path.join(HERE, "agents")
    if not os.path.isdir(src):
        todo.append("нет папки agents — репозиторий скачан не полностью")
        return
    files = [f for f in os.listdir(src) if f.endswith(".md")]
    if check_only:
        missing = [f for f in files if not os.path.exists(os.path.join(AGENTS_DST, f))]
        (todo if missing else done).append(
            "агенты: не скопировано %d из %d" % (len(missing), len(files)) if missing
            else "агенты на месте (%d)" % len(files))
        return
    os.makedirs(AGENTS_DST, exist_ok=True)
    for f in files:
        shutil.copy2(os.path.join(src, f), os.path.join(AGENTS_DST, f))
    done.append("скопировано агентов: %d → %s" % (len(files), AGENTS_DST))


def lay_out_workdir(workdir, check_only):
    if check_only:
        done.append("рабочая папка: %s" % workdir)
        return
    for sub in ("config", "lib", "products", "runs"):
        os.makedirs(os.path.join(workdir, sub), exist_ok=True)
    for folder in ("config", "lib"):
        src = os.path.join(HERE, folder)
        if not os.path.isdir(src):
            continue
        for f in os.listdir(src):
            s = os.path.join(src, f)
            d = os.path.join(workdir, folder, f)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)
    # шаблоны нового товара кладём рядом с конфигами
    tsrc = os.path.join(HERE, "templates")
    if os.path.isdir(tsrc):
        shutil.copytree(tsrc, os.path.join(workdir, "config", "templates-product"),
                        dirs_exist_ok=True)
    done.append("рабочая папка разложена: %s" % workdir)
    if workdir != r"C:\Ferma\factory":
        todo.append('запомнить путь: setx FACTORY_DIR "%s"' % workdir)


def check_virlo():
    cfg = os.path.join(os.path.expanduser("~"), ".claude.json")
    if os.path.exists(cfg):
        try:
            import json
            data = json.load(open(cfg, encoding="utf-8"))
            servers = dict(data.get("mcpServers") or {})
            for proj in (data.get("projects") or {}).values():
                servers.update(proj.get("mcpServers") or {})
            if any("virlo" in k.lower() for k in servers):
                done.append("Virlo подключён")
                return
        except Exception:
            pass
    todo.append("подключить Virlo: завести аккаунт на virlo.ai, взять ключ "
                "в разделе API и сказать Claude «подключи Virlo как MCP-сервер»")


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--workdir", default=os.environ.get("FACTORY_DIR") or r"C:\Ferma\factory")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    say("Установка анализа трендов")
    say("=" * 52)
    install_packages(a.check)
    find_ffmpeg(a.check)
    copy_agents(a.check)
    lay_out_workdir(a.workdir, a.check)
    check_virlo()

    say()
    say("Готово:")
    for d in done:
        say("  + " + d)
    if todo:
        say()
        say("Осталось сделать:")
        for t in todo:
            say("  ! " + t)
        say()
        say("Не понимаете, что делать, — покажите этот вывод Claude,")
        say("он доведёт установку до конца.")
    else:
        say()
        say("Всё готово. Расскажите Claude про свой товар и скажите:")
        say("«проанализируй <товар>».")
    say("=" * 52)
    say("Перезапустите Claude Code, чтобы он увидел новых агентов.")


if __name__ == "__main__":
    main()
