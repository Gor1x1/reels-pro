"""Хук Claude Code (PreToolUse, Bash|PowerShell): тяжёлое мимо очереди монтажа не запускается.

Закон М-44, приказ владельца 17.09.2026: пока идёт монтаж, в каждый момент
работает одна тяжёлая задача. ffmpeg по 4K и распознавание речи одновременно
перегрели компьютер до мерцания экрана. Очередь — pipeline/ochered.py; хук не
даёт агенту по ошибке пройти мимо неё и отвечает готовой командой.

Тяжёлым считается:
- ffmpeg с -i, whisper, rembg, demucs и прочие медиакомбайны — всегда;
- remotion render/still/benchmark и node-скрипты с @remotion/renderer — всегда;
- python-код со словами ffmpeg, whisper, torch, onnxruntime, cv2, rembg, moviepy
  (файл, -c, heredoc, stdin) — только в работе монтажа: папка reels-pro или слова
  «reels-pro», «видео ферма» в команде или в коде. OCR фермы на cv2 не трогается;
- ручная установка переменной REELS_OCHERED (ею очередь метит свои процессы).

Пропускается: запуск через ochered.py; скрипт со сторожем очереди v_ocheredi() и
build.ps1 — встанут в очередь сами; ffprobe, grep, git и прочее лёгкое.

Команда режется на сегменты с учётом кавычек (; && || | & скобки, перевод строки,
do/then), bash -c, cmd /c, powershell -Command, Start-Process, heredoc разбираются
рекурсивно. Любая ошибка хука — выход 0 без ответа: сломанный хук не должен
останавливать работу во всех сессиях.

Рабочая копия — ~/.claude/tools/ochered-hook.py, исходник — здесь.
"""
import base64
import json
import os
import re
import sys

OCHERED = "C:/Ferma/factory/reels-pro/pipeline/ochered.py"
REELS = "c:/ferma/factory/reels-pro"
MONTAZH = re.compile(r"reels-pro|видео\s+ферма", re.I)
SLOVA_PY = re.compile(r"\b(ffmpeg|whisper|faster_whisper|whisperx|torch|onnxruntime|cv2|rembg|moviepy"
                      r"|mediapipe|demucs)\b")
MODULI_PY = {"whisper", "faster_whisper", "whisperx", "demucs", "rembg", "spleeter"}
RENDER_JS = re.compile(r"@remotion/renderer|\brender(Media|Still|Frames)\s*\(")
STOROZH = "v_ocheredi("
PODMENA = re.compile(r"REELS_OCHERED[\"'\]]*\s*(=(?!=)|:\s*[\"']?1|,)", re.I)
KOMBAINY = {"whisper", "whisperx", "faster-whisper", "whisper-ctranslate2", "rembg", "demucs",
            "spleeter", "handbrakecli", "x264", "x265", "backgroundremover"}
PYTHONY = re.compile(r"^(python|pythonw|py)(\d+(\.\d+)*)?$")
PREFIKSY = {"do", "then", "else", "elif", "if", "while", "until", "!", "time", "exec", "nohup",
            "env", "sudo", "command", "builtin", "call", "nice", "ionice", "timeout", "stdbuf",
            "xargs", "measure-command", "foreach-object", "%", "invoke-command", "start-job",
            "trace-command", "wsl", ".", "parallel", "watch"}
GLUBINA = 5


class Kontekst:
    def __init__(self, cwd: str, komanda: str) -> None:
        self.cwd = norm(cwd)
        self.komanda = komanda
        self.tela: list[str] = []          # тела heredoc по номерам меток
        self.faily: dict[str, str] = {}    # файлы, записанные heredoc в этой же команде
        self.peremennye: dict[str, str] = {}
        self.kavychki: list[str] = []      # строки в кавычках — то, что могло уйти в stdin

    def telo(self, metka: str) -> str:
        try:
            return self.tela[int(metka[1:])]
        except (ValueError, IndexError):
            return ""


def norm(put: str) -> str:
    p = (put or "").strip().strip("\"'").replace("\\", "/")
    m = re.match(r"^/([a-zA-Z])(/|$)", p)  # /c/Ferma из Git Bash
    if m:
        p = m.group(1) + ":/" + p[3:]
    return p.rstrip("/").lower()


def polnyy(put: str, k: Kontekst) -> str:
    p = norm(os.path.expanduser(put.strip().strip("\"'")))
    if not re.match(r"^[a-z]:", p):
        p = norm(os.path.join(k.cwd, p))
    return norm(os.path.normpath(p))


def prochitat(put: str, k: Kontekst, limit: int = 2_000_000) -> str | None:
    p = polnyy(razvernut(put, k), k)
    if p in k.faily:
        return k.faily[p]
    try:
        with open(p, "rb") as f:
            return f.read(limit).decode("utf-8", "ignore")
    except OSError:
        return None


def programma(slovo: str) -> str:
    s = slovo.strip().replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].lower()
    for rassh in (".exe", ".cmd", ".bat", ".com"):
        if s.endswith(rassh):
            return s[: -len(rassh)]
    return s


def opciya(a: str) -> bool:
    return (a.startswith("-") and a != "-") or bool(re.fullmatch(r"/[A-Za-z?]{1,2}", a))


def razvernut(slovo: str, k: Kontekst) -> str:
    m = re.fullmatch(r"\$\{?(?:env:)?(\w+)\}?", slovo.strip(), re.I)
    if m and m.group(1).lower() in k.peremennye:
        return k.peremennye[m.group(1).lower()]
    return slovo


def montazh(k: Kontekst, *teksty: str) -> bool:
    return k.cwd.startswith(REELS) or any(MONTAZH.search(t or "") for t in (k.komanda, *teksty))


# ---------------------------------------------------------------- разбор текста

HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_][\w.-]*)\1")


def vyrezat_heredoc(tekst: str, k: Kontekst) -> str:
    """Тела heredoc — в k.tela, в тексте на их месте слово-метка \\x01N."""
    stroki, out, i = tekst.split("\n"), [], 0
    while i < len(stroki):
        s = stroki[i]
        metki = [m for m in HEREDOC.finditer(s) if m.start() == 0 or s[m.start() - 1] != "<"]
        if not metki:
            out.append(s)
            i += 1
            continue
        novaya, poz, j = [], 0, i + 1
        for m in metki:
            telo = []
            while j < len(stroki) and stroki[j].lstrip("\t").rstrip("\r") != m.group(2):
                telo.append(stroki[j])
                j += 1
            j += 1
            novaya += [s[poz:m.start()], f" \x01{len(k.tela)} "]
            k.tela.append("\n".join(telo))
            poz = m.end()
        out.append("".join(novaya) + s[poz:])
        i = j
    return "\n".join(out)


def tokeny(tekst: str, ps: bool) -> list[tuple[str, str, bool, int, int]]:
    """Слова ('w') и разделители ('s'): (вид, текст, слово целиком в кавычках, начало, конец)."""
    out: list[tuple[str, str, bool, int, int]] = []
    buf: list[str] = []
    sost = {"kav": None, "nachalo": -1}  # kav: None — слова нет; True — пока только кавычки
    n, i = len(tekst), 0

    def sbros(konec: int) -> None:
        if sost["kav"] is not None:
            out.append(("w", "".join(buf), bool(sost["kav"]), sost["nachalo"], konec))
        buf.clear()
        sost["kav"], sost["nachalo"] = None, -1

    def dobavit(kusok: str, v_kavychkah: bool, poz: int) -> None:
        if sost["kav"] is None:
            sost["kav"], sost["nachalo"] = v_kavychkah, poz
        elif not v_kavychkah:
            sost["kav"] = False
        buf.append(kusok)

    while i < n:
        c = tekst[i]
        if ps and c == "@" and tekst[i + 1:i + 2] in ("'", '"') and tekst[i + 2:i + 3] in ("\n", "\r"):
            j = tekst.find("\n" + tekst[i + 1] + "@", i + 2)  # here-string до «'@» с начала строки
            j = n if j < 0 else j
            dobavit(tekst[i + 3:j].lstrip("\n"), True, i)
            i = min(n, j + 3)
            continue
        if c in " \t\r":
            sbros(i)
            i += 1
        elif c == "\n":
            sbros(i)
            out.append(("s", "\n", False, i, i + 1))
            i += 1
        elif c == "#" and sost["kav"] is None:
            j = tekst.find("\n", i)
            i = n if j < 0 else j
        elif c in "'\"":
            j, chast = i + 1, []
            while j < n:
                d = tekst[j]
                if d == c:
                    if ps and tekst[j + 1:j + 2] == c:
                        chast.append(c)
                        j += 2
                        continue
                    break
                if c == '"' and not ps and d == "\\" and tekst[j + 1:j + 2] in ('"', "\\", "$", "`"):
                    chast.append(tekst[j + 1])
                    j += 2
                    continue
                if c == '"' and ps and d == "`" and j + 1 < n:
                    chast.append(tekst[j + 1])
                    j += 2
                    continue
                chast.append(d)
                j += 1
            dobavit("".join(chast), True, i)
            i = j + 1
        elif (c == "\\" and not ps or c == "`" and ps) and i + 1 < n:
            if tekst[i + 1] not in "\r\n":  # иначе перенос строки команды
                dobavit(tekst[i + 1], False, i)
            i += 2
        elif tekst.startswith(("&&", "||"), i):
            sbros(i)
            out.append(("s", tekst[i:i + 2], False, i, i + 2))
            i += 2
        elif c in ";|&(){}":
            if c == "&" and (buf and buf[-1].endswith(">") or tekst[i + 1:i + 2] == ">") \
                    or c in "{}" and sost["kav"] is not None and not ps:
                dobavit(c, False, i)  # 2>&1, &>file, ${f%.mov}
            else:
                sbros(i)
                out.append(("s", c, False, i, i + 1))
            i += 1
        else:
            dobavit(c, False, i)
            i += 1
    sbros(n)
    return out


def segmenty(tokens):
    seg = []
    for t in tokens:
        if t[0] == "s":
            if seg:
                yield seg
            seg = []
        else:
            seg.append(t)
    if seg:
        yield seg


def bez_perenapravleniy(args: list[str]) -> list[str]:
    """Убрать >file, 2>&1 и цели перенаправлений; «< file» оставить файлом."""
    out, j = [], 0
    while j < len(args):
        a = args[j]
        if re.fullmatch(r"[\d*]?>>?(&\d)?|&>>?", a):
            j += 1 if a.endswith(tuple("0123456789")) else 2
        elif re.match(r"^[\d*]?>>?\S|^&>>?\S", a):
            j += 1
        elif a == "<":
            j += 1
        elif a.startswith("<") and len(a) > 1 and not a.startswith("<<"):
            out.append(a[1:])
            j += 1
        else:
            out.append(a)
            j += 1
    return out


def proverit_tekst(tekst: str, k: Kontekst, ps: bool, glubina: int) -> str | None:
    if not tekst or glubina > GLUBINA:
        return None
    if not ps:
        tekst = vyrezat_heredoc(tekst, k)
    tokens = tokeny(tekst, ps)
    k.kavychki += [t[1] for t in tokens if t[0] == "w" and t[2]]
    for seg in segmenty(tokens):
        prichina = razobrat([t[1] for t in seg], [t[2] for t in seg], k, glubina, ps)
        if prichina:
            return prichina
    return None


# ---------------------------------------------------------------- разбор сегмента

def razobrat(slova: list[str], kav: list[bool], k: Kontekst, glubina: int, ps: bool) -> str | None:
    """Причина, если сегмент — тяжёлая работа мимо очереди, иначе None."""
    if not slova or glubina > GLUBINA:
        return None
    if len(slova) >= 3 and slova[0].startswith("$") and slova[1] == "=":
        k.peremennye[slova[0][1:].lower().removeprefix("env:")] = " ".join(slova[2:])
        return None
    m = re.fullmatch(r"\$(?:env:)?(\w+)=(.*)", slova[0], re.I | re.S)  # $ff="...ffmpeg.exe" без пробелов
    if m:
        k.peremennye[m.group(1).lower()] = " ".join([m.group(2), *slova[1:]]).strip()
        return None
    i = 0
    while i < len(slova):
        if not kav[i] and re.match(r"^[A-Za-z_]\w*=", slova[i]):
            imya, _, znach = slova[i].partition("=")
            k.peremennye[imya.lower()] = znach
            i += 1
        elif slova[i].lower() in PREFIKSY:
            i += 1
            while i < len(slova) and (opciya(slova[i]) or re.fullmatch(r"\d+(\.\d+)?[smhd]?", slova[i])):
                i += 1
        else:
            break
    if i >= len(slova):
        return None
    slovo = razvernut(slova[i], k)
    prog = programma(slovo)
    if re.search(r"(^|[\\/\s\"'])ffmpeg(\.exe)?[\"']?$", slovo, re.I):
        prog = "ffmpeg"
    syrye = slova[i + 1:]
    args = bez_perenapravleniy(syrye)
    nizh = [a.lower() for a in args]

    if prog in ("cd", "set-location", "sl", "chdir", "pushd", "push-location"):
        cel = next((a for a in args if not opciya(a)), None)
        if cel:
            k.cwd = polnyy(razvernut(cel, k), k)
        return None
    if prog in ("cat", "tee"):
        zapomnit_fayl(prog, syrye, k)
        return None
    if prog == "ffmpeg":
        return "ffmpeg" if "-i" in args else None
    if prog in KOMBAINY:
        return None if {"-h", "--help", "--version", "-version"} & set(nizh) else prog
    if prog in ("npx", "pnpm", "yarn", "bunx", "npm", "remotion"):
        cep = ([prog] if prog == "remotion" else []) + nizh
        for j, a in enumerate(cep):
            if programma(a) == "remotion" or a == "@remotion/cli":
                dalee = [b for b in cep[j + 1:] if not opciya(b)]
                if dalee and dalee[0] in ("render", "still", "benchmark"):
                    return f"remotion {dalee[0]}"
        return None
    if prog in ("node", "bun", "deno"):
        return razobrat_node(args, k)
    if PYTHONY.match(prog):
        return razobrat_python(args, k)
    if prog in ("bash", "sh", "zsh", "dash"):
        return razobrat_bash(args, k, glubina)
    if prog == "cmd":
        for j, a in enumerate(nizh):
            if a in ("/c", "/k"):
                return proverit_tekst(" ".join(args[j + 1:]), k, True, glubina + 1)
        return None
    if prog in ("powershell", "pwsh"):
        return razobrat_powershell(args, k, glubina)
    if prog in ("invoke-expression", "iex"):
        return proverit_tekst(" ".join(args), k, True, glubina + 1)
    if prog in ("start-process", "saps") or prog == "start" and ps:
        return razobrat_start_process(args, k, glubina, ps)
    if prog == "start":
        ostatok = [a for a in args if a and not opciya(a)]
        return razobrat(ostatok, [False] * len(ostatok), k, glubina + 1, ps)
    if prog == "find":
        for j, a in enumerate(nizh):
            if a in ("-exec", "-execdir", "-ok", "-okdir"):
                hvost = args[j + 1:]
                return razobrat(hvost, [False] * len(hvost), k, glubina + 1, ps)
        return None
    konec = slovo.lower()
    if konec.endswith((".ps1", ".sh", ".bat", ".cmd")):
        tekst = prochitat(slovo, k)
        if not tekst or "ochered" in tekst.lower():  # build.ps1 встаёт в очередь сам
            return None
        return proverit_tekst(tekst, k, not konec.endswith(".sh"), glubina + 1)
    return None


def zapomnit_fayl(prog: str, syrye: list[str], k: Kontekst) -> None:
    """cat > x.py <<EOF … EOF — запомнить, что лежит в x.py, до записи на диск."""
    metka = next((a for a in syrye if a.startswith("\x01")), None)
    if not metka:
        return
    cel = None
    for j, a in enumerate(syrye):
        if a in (">", ">>") and j + 1 < len(syrye):
            cel = syrye[j + 1]
        elif re.match(r"^>>?[^>&]", a):
            cel = a.lstrip(">")
    if cel is None and prog == "tee":
        cel = next((a for a in syrye if not opciya(a) and not a.startswith("\x01")), None)
    if cel:
        k.faily[polnyy(cel, k)] = k.telo(metka)


def razobrat_node(args: list[str], k: Kontekst) -> str | None:
    for j, a in enumerate(args):
        if a in ("-e", "--eval", "-p", "--print"):
            return "node-рендер" if j + 1 < len(args) and RENDER_JS.search(args[j + 1]) else None
        if not a.startswith("-"):
            tekst = prochitat(a, k)
            return "node-рендер" if tekst and RENDER_JS.search(tekst) else None
    return None


def razobrat_python(args: list[str], k: Kontekst) -> str | None:
    j = 0
    while j < len(args):
        a = args[j]
        if a.startswith("\x01"):
            j += 1
        elif a == "-c" or a.startswith("-c") and not a.startswith("--"):
            kod = (args[j + 1] if j + 1 < len(args) else "") if a == "-c" else a[2:]
            return prichina_koda(kod, k, "python -c")
        elif a == "-m":
            modul = args[j + 1] if j + 1 < len(args) else ""
            return f"python -m {modul}" if modul.split(".")[0].lower() in MODULI_PY else None
        elif a in ("-W", "-X"):
            j += 2
        elif a == "-":
            return prichina_stdin(args, k)
        elif a.startswith("-"):
            j += 1
        else:
            if programma(a) in ("ochered.py", "ochered_hook.py"):
                return None  # запуск через очередь пропускается целиком
            tekst = prochitat(a, k)
            if tekst is None or STOROZH in tekst:
                return None
            if SLOVA_PY.search(tekst) and (montazh(k, tekst) or polnyy(a, k).startswith(REELS)):
                return f"python-скрипт {os.path.basename(a)} с тяжёлыми библиотеками"
            return None
    return prichina_stdin(args, k)


def prichina_koda(kod: str, k: Kontekst, kak: str) -> str | None:
    if STOROZH not in kod and SLOVA_PY.search(kod) and montazh(k, kod):
        return f"{kak} с тяжёлыми библиотеками"
    return None


def prichina_stdin(args: list[str], k: Kontekst) -> str | None:
    tela = [k.telo(a) for a in args if a.startswith("\x01")] or k.kavychki
    return prichina_koda("\n".join(tela), k, "python-код из stdin")


def razobrat_bash(args: list[str], k: Kontekst, glubina: int) -> str | None:
    for j, a in enumerate(args):
        if re.fullmatch(r"-[a-zA-Z]*c[a-zA-Z]*", a) and j + 1 < len(args):
            return proverit_tekst(args[j + 1], k, False, glubina + 1)
    for a in args:
        if a.startswith("\x01"):
            prichina = proverit_tekst(k.telo(a), k, False, glubina + 1)
            if prichina:
                return prichina
    skript = next((a for a in args if not a.startswith(("-", "\x01"))), None)
    tekst = prochitat(skript, k) if skript else None
    return proverit_tekst(tekst, k, False, glubina + 1) if tekst else None


def razobrat_powershell(args: list[str], k: Kontekst, glubina: int) -> str | None:
    for j, a in enumerate(args):
        al = a.lower()
        if re.fullmatch(r"-c(o(m(m(a(n(d)?)?)?)?)?)?", al):
            return proverit_tekst(" ".join(args[j + 1:]), k, True, glubina + 1)
        if re.fullmatch(r"-e(c|n(c(o(d(e(d(c(o(m(m(a(n(d)?)?)?)?)?)?)?)?)?)?)?)?)?", al) and j + 1 < len(args):
            try:
                kod = base64.b64decode(args[j + 1]).decode("utf-16-le")
            except (ValueError, UnicodeDecodeError):
                return None
            return proverit_tekst(kod, k, True, glubina + 1)
        if re.fullmatch(r"-f(i(l(e)?)?)?", al) and j + 1 < len(args):
            tekst = prochitat(args[j + 1], k)
            if not tekst or "ochered" in tekst.lower():
                return None
            return proverit_tekst(tekst, k, True, glubina + 1)
    ostatok = [a for a in args if not a.startswith("-")]
    return proverit_tekst(" ".join(ostatok), k, True, glubina + 1) if ostatok else None


def razobrat_start_process(args: list[str], k: Kontekst, glubina: int, ps: bool) -> str | None:
    fayl, argi, pozicii, j = None, [], [], 0
    while j < len(args):
        a, al = args[j], args[j].lower()
        if al.startswith("-f"):
            fayl = args[j + 1] if j + 1 < len(args) else None
            j += 2
        elif al.startswith("-a"):
            argi.append(args[j + 1] if j + 1 < len(args) else "")
            j += 2
        elif al == "-wait" or al.startswith(("-n", "-p", "-l", "-u")):
            j += 1
        elif al.startswith("-"):
            j += 2
        else:
            pozicii.append(a)
            j += 1
    if fayl is None and pozicii:
        fayl = pozicii.pop(0)
    if not argi:
        argi = pozicii
    if fayl is None:
        return None
    if programma(razvernut(fayl, k)) == "ffmpeg":
        return "ffmpeg через Start-Process"
    psevdo = [fayl] + " ".join(argi).replace(",", " ").split()
    return razobrat(psevdo, [False] * len(psevdo), k, glubina + 1, ps)


# ---------------------------------------------------------------- ответ

def proverit(komanda: str, cwd: str, ps: bool) -> str | None:
    """Текст отказа для Claude или None, если команду можно запускать."""
    if PODMENA.search(komanda):
        return ("Очередь монтажа (закон М-44): переменную REELS_OCHERED руками не выставлять — ею очередь "
                "метит свои процессы, подмена пускает тяжёлое мимо очереди. Запускай через очередь:\n"
                f"python {OCHERED} -- <команда>")
    k = Kontekst(cwd, komanda)
    tekst = komanda if ps else vyrezat_heredoc(komanda, k)
    tokens = tokeny(tekst, ps)
    k.kavychki = [t[1] for t in tokens if t[0] == "w" and t[2]]
    for seg in segmenty(tokens):
        prichina = razobrat([t[1] for t in seg], [t[2] for t in seg], k, 0, ps)
        if prichina:
            kusok = tekst[seg[0][3]:seg[-1][4]].strip()
            kusok = re.sub(r"^((do|then|else|time|nohup|exec|if|while|until|!)\s+)+", "", kusok)
            heredoc = "\x01" in kusok
            kusok = re.sub(r"\x01\d+", "<<heredoc", kusok)
            return (
                f"Очередь монтажа (закон М-44): «{kusok[:300]}» — тяжёлая работа ({prichina}), мимо очереди "
                "не запускается. 17.09.2026 две такие работы одновременно перегрели компьютер до мерцания "
                "экрана.\nЗапусти через очередь — она дождётся своей очереди, даст 18 из 24 потоков (без датчика — 12) и снимет "
                f"хвосты:\npython {OCHERED} -- {kusok if not heredoc else '<команда>'}\n"
                + ("Код из heredoc сначала сохрани в файл (Write), потом запусти файл через очередь.\n"
                   if heredoc else "")
                + "Работа дольше 10 минут — в фоне инструмента (run_in_background), и пока она идёт, "
                "ничего тяжёлого не запускать. Очередь занята дольше 9 минут — код 75: не обходить, "
                f"повторить ту же команду позже. Что идёт сейчас: python {OCHERED} status"
            )
    return None


def main() -> None:
    try:
        dannye = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
        instrument = dannye.get("tool_name", "")
        if instrument not in ("Bash", "PowerShell"):
            return
        komanda = (dannye.get("tool_input") or {}).get("command") or ""
        if not komanda.strip():
            return
        otkaz = proverit(komanda, dannye.get("cwd") or os.getcwd(), instrument == "PowerShell")
        if otkaz:
            sys.stdout.write(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": otkaz,
            }}))
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
