"""Очередь монтажа — закон М-44 механизмом, а не просьбой к агентам.

17.09.2026 прогон видео 10 перегрел компьютер до мерцания экрана: ffmpeg по 4K
HEVC и распознавание речи шли одновременно на всех 24 потоках, а после
остановки агента ffmpeg продолжал работать. Очередь закрывает эти дыры:

- одна тяжёлая работа за раз — именованный мьютекс Windows. Процесс умер —
  мьютекс освобождается сам, очередь не залипает;
- не весь процессор — работа и всё, что она запускает, живут в объекте
  задания (job): половина физических ядер вместе с их вторыми потоками,
  приоритет ниже обычного. Нулевые ядра остаются ферме, системе и экрану;
- без хвостов — очередь умерла (остановили агента, истёк срок инструмента) —
  Windows убивает всё дерево работы. Что работа оставила после себя, снимается;
- перегрев — ядра работы сбрасывают частоту (троттлинг): работа замирает на
  две минуты остыть, на четвёртый раз снимается с кодом 76.

Запуск из C:/Ferma/factory/reels-pro:

    python pipeline/ochered.py -- ffmpeg -i in.mov ... out.mp4
    python pipeline/ochered.py -- powershell -NoProfile -File build.ps1 -Master
    python pipeline/ochered.py --zhdat 120 -- python pipeline/qc.py out/x.mp4
    python pipeline/ochered.py status    что идёт сейчас и последние работы
    python pipeline/ochered.py stop      снять текущую работу со всем деревом

Очередь занята дольше --zhdat секунд (по умолчанию 540: инструмент агента
живёт 10 минут) — выход с кодом 75. Очередь не обходить: повторить ту же
команду позже. Работа дольше 10 минут запускается в фоне инструмента, и пока
она идёт, ничего тяжёлого не запускается.

Тяжёлые скрипты pipeline/ первой строкой зовут v_ocheredi(): запущенные мимо
очереди, они перезапускают себя через неё. Хук Claude (ochered_hook.py) не
даёт запустить мимо очереди ffmpeg и прочее тяжёлое.

Состояние — %LOCALAPPDATA%/reels-pro-ochered: tekushchaya.json (что идёт)
и zhurnal.jsonl (минуты, код, загрузка процессора, частота, паузы).
"""
from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

MUTEX = "Local\\reels-pro-ochered"
JOB = "Local\\reels-pro-ochered-job"
PAPKA = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "reels-pro-ochered"
TEKUSHCHAYA = PAPKA / "tekushchaya.json"
ZHURNAL = PAPKA / "zhurnal.jsonl"
SNYATA = PAPKA / "snyata.flag"
SKRIPT = Path(__file__).resolve()

ZHDAT_SEK = 540            # инструмент агента живёт 10 минут
KOD_ZANYATO = 75           # EX_TEMPFAIL: повторить ту же команду позже
KOD_PEREGREV = 76          # снята после трёх пауз на остывание
SHAG_SEK = 10              # как часто меряется процессор
PROGREV_SEK = 60           # эталон частоты набирается первую минуту работы
DOLYA_TROTTLINGA = 0.70    # частота ядер работы ниже 70% своего эталона —
PODRYAD = 3                # три замера подряд — троттлинг
PAUZA_SEK = 120
PAUZ_MAKS = 3
DOCHISTKA_SEK = 30         # сколько ждать процессы, оставленные работой
ZANYATO_YADRO = 80.0       # ядро считается занятым от 80% времени
POTOKOVYE = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
             "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")

WAIT_OBJECT_0, WAIT_ABANDONED, WAIT_TIMEOUT = 0x0, 0x80, 0x102
CREATE_SUSPENDED = 0x4
BELOW_NORMAL = 0x4000
JOB_QUERY, JOB_TERMINATE = 0x0004, 0x0008
PROCESS_SUSPEND_RESUME = 0x0800
LIMIT_AFFINITY, LIMIT_PRIORITY = 0x10, 0x20
LIMIT_DIE_ON_EXCEPTION, LIMIT_KILL_ON_CLOSE = 0x400, 0x2000
JOB_ACCOUNTING, JOB_PID_LIST, JOB_EXTENDED_LIMIT = 1, 3, 9
PDH_MORE_DATA = 0x800007D2
PDH_FMT_DOUBLE_NOCAP = 0x00000200 | 0x00008000

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
ntdll = ctypes.WinDLL("ntdll")
pdh = ctypes.WinDLL("pdh")
H = wintypes.HANDLE
DW = wintypes.DWORD


def _fn(dll, name, res, *args):
    f = getattr(dll, name)
    f.restype, f.argtypes = res, list(args)
    return f


CreateMutexW = _fn(k32, "CreateMutexW", H, ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
WaitForSingleObject = _fn(k32, "WaitForSingleObject", DW, H, DW)
ReleaseMutex = _fn(k32, "ReleaseMutex", wintypes.BOOL, H)
CloseHandle = _fn(k32, "CloseHandle", wintypes.BOOL, H)
CreateJobObjectW = _fn(k32, "CreateJobObjectW", H, ctypes.c_void_p, wintypes.LPCWSTR)
OpenJobObjectW = _fn(k32, "OpenJobObjectW", H, DW, wintypes.BOOL, wintypes.LPCWSTR)
SetInformationJobObject = _fn(k32, "SetInformationJobObject", wintypes.BOOL,
                              H, ctypes.c_int, ctypes.c_void_p, DW)
QueryInformationJobObject = _fn(k32, "QueryInformationJobObject", wintypes.BOOL,
                                H, ctypes.c_int, ctypes.c_void_p, DW, ctypes.POINTER(DW))
AssignProcessToJobObject = _fn(k32, "AssignProcessToJobObject", wintypes.BOOL, H, H)
TerminateJobObject = _fn(k32, "TerminateJobObject", wintypes.BOOL, H, wintypes.UINT)
IsProcessInJob = _fn(k32, "IsProcessInJob", wintypes.BOOL, H, H, ctypes.POINTER(wintypes.BOOL))
GetCurrentProcess = _fn(k32, "GetCurrentProcess", H)
GetProcessAffinityMask = _fn(k32, "GetProcessAffinityMask", wintypes.BOOL, H,
                             ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t))
SetProcessAffinityMask = _fn(k32, "SetProcessAffinityMask", wintypes.BOOL, H, ctypes.c_size_t)
SetPriorityClass = _fn(k32, "SetPriorityClass", wintypes.BOOL, H, DW)
GetLogicalProcessorInformation = _fn(k32, "GetLogicalProcessorInformation", wintypes.BOOL,
                                     ctypes.c_void_p, ctypes.POINTER(DW))
GetSystemTimes = _fn(k32, "GetSystemTimes", wintypes.BOOL, ctypes.POINTER(wintypes.FILETIME),
                     ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME))
OpenProcess = _fn(k32, "OpenProcess", H, DW, wintypes.BOOL, DW)
NtSuspendProcess = _fn(ntdll, "NtSuspendProcess", ctypes.c_long, H)
NtResumeProcess = _fn(ntdll, "NtResumeProcess", ctypes.c_long, H)
PdhOpenQueryW = _fn(pdh, "PdhOpenQueryW", DW, wintypes.LPCWSTR, ctypes.c_size_t,
                    ctypes.POINTER(ctypes.c_void_p))
PdhAddEnglishCounterW = _fn(pdh, "PdhAddEnglishCounterW", DW, ctypes.c_void_p, wintypes.LPCWSTR,
                            ctypes.c_size_t, ctypes.POINTER(ctypes.c_void_p))
PdhCollectQueryData = _fn(pdh, "PdhCollectQueryData", DW, ctypes.c_void_p)
PdhGetFormattedCounterArrayW = _fn(pdh, "PdhGetFormattedCounterArrayW", DW, ctypes.c_void_p, DW,
                                   ctypes.POINTER(DW), ctypes.POINTER(DW), ctypes.c_void_p)
PdhCloseQuery = _fn(pdh, "PdhCloseQuery", DW, ctypes.c_void_p)


class BASIC_LIMIT(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", DW), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", DW),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", DW), ("SchedulingClass", DW)]


class EXTENDED_LIMIT(ctypes.Structure):
    _fields_ = [("Basic", BASIC_LIMIT), ("Io", ctypes.c_uint64 * 6),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


class ACCOUNTING(ctypes.Structure):
    _fields_ = [("TotalUserTime", ctypes.c_int64), ("TotalKernelTime", ctypes.c_int64),
                ("PeriodUserTime", ctypes.c_int64), ("PeriodKernelTime", ctypes.c_int64),
                ("PageFaults", DW), ("TotalProcesses", DW), ("ActiveProcesses", DW),
                ("TerminatedProcesses", DW)]


class PID_LIST(ctypes.Structure):
    _fields_ = [("Assigned", DW), ("InList", DW), ("Ids", ctypes.c_size_t * 512)]


class SLPI(ctypes.Structure):  # SYSTEM_LOGICAL_PROCESSOR_INFORMATION, 32 байта
    _fields_ = [("ProcessorMask", ctypes.c_size_t), ("Relationship", ctypes.c_int),
                ("Union", ctypes.c_uint64 * 2)]


class PDH_ITEM(ctypes.Structure):  # PDH_FMT_COUNTERVALUE_ITEM_W, значение как double
    _fields_ = [("Name", wintypes.LPWSTR), ("CStatus", DW), ("Value", ctypes.c_double)]


def _vyvod(tekst: str, potok=None) -> None:
    """Печать в UTF-8 мимо кодировки консоли: cp1251 роняет «→» и «×»."""
    potok = potok or sys.stderr
    try:
        potok.flush()
        potok.buffer.write((tekst + "\n").encode("utf-8", "replace"))
        potok.buffer.flush()
    except Exception:
        pass


# ---------------------------------------------------------------- замеры

def _vremena() -> tuple[int, int] | None:
    idle, kern, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
    if not GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user)):
        return None
    ft = lambda f: (f.dwHighDateTime << 32) | f.dwLowDateTime  # noqa: E731
    return ft(idle), ft(kern) + ft(user)  # время ядра включает простой


class Zagruzka:
    """Загрузка всего процессора между замерами, %."""

    def __init__(self) -> None:
        self.prev = _vremena()

    def zamer(self) -> float | None:
        cur, prev = _vremena(), self.prev
        self.prev = cur
        if not cur or not prev or cur[1] <= prev[1]:
            return None
        return round(100.0 * (1 - (cur[0] - prev[0]) / (cur[1] - prev[1])), 1)


class Chastota:
    """Производительность занятых ядер работы, % от номинальной частоты.

    Троттлинг от перегрева роняет её при той же загрузке. Свободные ядра не
    считаются: в простое они стоят на низкой частоте и врут."""

    def __init__(self, maska: int) -> None:
        self.maska, self.ok = maska, False
        self.q, self.perf, self.vremya = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        try:
            self.ok = (maska != 0
                       and PdhOpenQueryW(None, 0, ctypes.byref(self.q)) == 0
                       and PdhAddEnglishCounterW(self.q, "\\Processor Information(*)\\% Processor Performance",
                                                 0, ctypes.byref(self.perf)) == 0
                       and PdhAddEnglishCounterW(self.q, "\\Processor Information(*)\\% Processor Time",
                                                 0, ctypes.byref(self.vremya)) == 0
                       and PdhCollectQueryData(self.q) == 0)
        except Exception:
            self.ok = False

    def _massiv(self, schetchik) -> dict[int, float]:
        razmer, chislo = DW(0), DW(0)
        if PdhGetFormattedCounterArrayW(schetchik, PDH_FMT_DOUBLE_NOCAP, ctypes.byref(razmer),
                                        ctypes.byref(chislo), None) != PDH_MORE_DATA:
            return {}
        buf = (ctypes.c_byte * razmer.value)()
        if PdhGetFormattedCounterArrayW(schetchik, PDH_FMT_DOUBLE_NOCAP, ctypes.byref(razmer),
                                        ctypes.byref(chislo), buf) != 0:
            return {}
        items = ctypes.cast(buf, ctypes.POINTER(PDH_ITEM))
        out = {}
        for i in range(chislo.value):
            chasti = (items[i].Name or "").split(",")  # «0,17» — группа, номер потока
            if len(chasti) == 2 and chasti[1].isdigit() and items[i].CStatus in (0, 1):
                out[int(chasti[1])] = items[i].Value
        return out

    def zamer(self) -> float | None:
        if not self.ok or PdhCollectQueryData(self.q) != 0:
            return None
        perf, vremya = self._massiv(self.perf), self._massiv(self.vremya)
        znach = [perf[n] for n, t in vremya.items()  # 0 — замер без интервала, не частота
                 if self.maska >> n & 1 and t >= ZANYATO_YADRO and perf.get(n, 0) > 0]
        return round(sum(znach) / len(znach), 1) if znach else None

    def zakryt(self) -> None:
        if self.ok:
            PdhCloseQuery(self.q)


# ---------------------------------------------------------------- задание

def maska_raboty() -> int:
    """Половина физических ядер с их вторыми потоками — верхняя половина."""
    svoya, sistema = ctypes.c_size_t(), ctypes.c_size_t()
    if not GetProcessAffinityMask(GetCurrentProcess(), ctypes.byref(svoya), ctypes.byref(sistema)):
        return 0
    razmer = DW(0)
    GetLogicalProcessorInformation(None, ctypes.byref(razmer))
    n = razmer.value // ctypes.sizeof(SLPI)
    buf = (SLPI * max(n, 1))()
    if not n or not GetLogicalProcessorInformation(buf, ctypes.byref(razmer)):
        return 0
    yadra = sorted(m for m in (e.ProcessorMask & svoya.value for e in buf[:n] if e.Relationship == 0) if m)
    maska = 0
    for m in yadra[-max(1, len(yadra) // 2):]:
        maska |= m
    return maska


def vnutri_ocheredi() -> bool:
    """Процесс уже внутри задания очереди — вложенный вызов, ждать нечего."""
    h = OpenJobObjectW(JOB_QUERY, False, JOB)
    if not h:
        return False
    try:
        v = wintypes.BOOL()
        return bool(IsProcessInJob(GetCurrentProcess(), h, ctypes.byref(v)) and v.value)
    finally:
        CloseHandle(h)


def _sozdat_zadanie(maska: int) -> tuple[int | None, bool, str]:
    """(задание, приоритет задан заданием, что не вышло)."""
    staroe = OpenJobObjectW(JOB_QUERY | JOB_TERMINATE, False, JOB)
    if staroe:  # мьютекс наш, а задание живо — хвост оборванной работы
        TerminateJobObject(staroe, 1)
        CloseHandle(staroe)
    h = CreateJobObjectW(None, JOB)
    if not h:
        return None, False, f"задание не создано (ошибка {ctypes.get_last_error()})"
    info = EXTENDED_LIMIT()
    flagi = LIMIT_KILL_ON_CLOSE | LIMIT_DIE_ON_EXCEPTION | (LIMIT_AFFINITY if maska else 0)
    info.Basic.Affinity = maska
    info.Basic.PriorityClass = BELOW_NORMAL
    info.Basic.LimitFlags = flagi | LIMIT_PRIORITY
    if SetInformationJobObject(h, JOB_EXTENDED_LIMIT, ctypes.byref(info), ctypes.sizeof(info)):
        return h, True, ""
    info.Basic.LimitFlags = flagi  # приоритет без привилегии не ставится — зададим процессу
    if SetInformationJobObject(h, JOB_EXTENDED_LIMIT, ctypes.byref(info), ctypes.sizeof(info)):
        return h, False, ""
    oshibka = ctypes.get_last_error()
    CloseHandle(h)
    return None, False, f"потолки заданию не выставлены (ошибка {oshibka})"


def _uchet(zadanie) -> ACCOUNTING | None:
    a = ACCOUNTING()
    if zadanie and QueryInformationJobObject(zadanie, JOB_ACCOUNTING, ctypes.byref(a), ctypes.sizeof(a), None):
        return a
    return None


def _pids(zadanie) -> list[int]:
    spisok = PID_LIST()
    if not QueryInformationJobObject(zadanie, JOB_PID_LIST, ctypes.byref(spisok), ctypes.sizeof(spisok), None):
        return []
    return [int(spisok.Ids[i]) for i in range(min(spisok.InList, 512))]


def _zamorozit(zadanie) -> list[int]:
    """Заморозить все процессы задания. Два прохода: второй ловит рождённых во время
    первого. Каждый процесс замораживается ровно раз — иначе одного resume мало."""
    zamorozheny: list[int] = []
    for _ in range(2):
        for pid in _pids(zadanie):
            if pid in zamorozheny:
                continue
            h = OpenProcess(PROCESS_SUSPEND_RESUME, False, pid)
            if h:
                if NtSuspendProcess(h) == 0:
                    zamorozheny.append(pid)
                CloseHandle(h)
    return zamorozheny


def _razmorozit(pids: list[int]) -> None:
    for pid in pids:
        h = OpenProcess(PROCESS_SUSPEND_RESUME, False, pid)
        if h:
            NtResumeProcess(h)
            CloseHandle(h)


# ---------------------------------------------------------------- работа

def _tekushchaya() -> dict | None:
    try:
        return json.loads(TEKUSHCHAYA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _opisanie(tek: dict | None) -> str:
    if not tek:
        return "работа без записи"
    minut = (time.time() - tek.get("t0", time.time())) / 60
    return f"«{tek.get('komanda', '?')[:160]}», идёт {minut:.0f} мин"


def _srok(sek: int) -> str:
    return f"{sek} с" if sek < 120 else f"{sek // 60} мин"


def _sred(spisok: list[float]) -> float | None:
    return round(sum(spisok) / len(spisok), 1) if spisok else None


def _rabota(argv: list[str], zhdal: int) -> int:
    PAPKA.mkdir(parents=True, exist_ok=True)
    SNYATA.unlink(missing_ok=True)
    komanda = subprocess.list2cmdline(argv)
    maska = maska_raboty()
    potoki = bin(maska).count("1") if maska else (os.cpu_count() or 1)
    vsego = os.cpu_count() or potoki
    zadanie, prioritet_zadaniem, beda = _sozdat_zadanie(maska)
    if beda:
        _vyvod(f"очередь: {beda} — ядра и приоритет выставлю процессу, но дерево при обрыве не снимется")

    env = dict(os.environ, REELS_OCHERED="1")
    for k in POTOKOVYE:
        bylo = env.get(k, "")
        env[k] = str(min(potoki, int(bylo))) if bylo.isdigit() and int(bylo) > 0 else str(potoki)

    t0 = time.time()
    try:
        proc = subprocess.Popen(argv, env=env, creationflags=CREATE_SUSPENDED)
    except OSError as e:
        _vyvod(f"очередь: команда не запустилась: {e}")
        if zadanie:
            CloseHandle(zadanie)
        return 127
    hp = H(int(proc._handle))
    v_zadanii = bool(zadanie) and bool(AssignProcessToJobObject(zadanie, hp))
    if zadanie and not v_zadanii:
        _vyvod(f"очередь: задание не приняло процесс (ошибка {ctypes.get_last_error()})")
    if not v_zadanii and maska:
        SetProcessAffinityMask(hp, maska)
    if not (v_zadanii and prioritet_zadaniem):
        SetPriorityClass(hp, BELOW_NORMAL)  # класс ниже обычного наследуют дети
    NtResumeProcess(hp)

    tek = {"t0": t0, "start": datetime.fromtimestamp(t0).isoformat(timespec="seconds"),
           "komanda": komanda, "papka": os.getcwd(), "pid_ocheredi": os.getpid(),
           "pid_raboty": proc.pid, "potoki": potoki, "vsego_potokov": vsego, "pauza_do": None}
    try:
        TEKUSHCHAYA.write_text(json.dumps(tek, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    _vyvod(f"очередь: работа пошла — {potoki} из {vsego} потоков, приоритет ниже обычного")

    zagruzka, chastota = Zagruzka(), Chastota(maska)
    zagr, perf = [], []
    etalon, podryad, pauzy, kod, prichina = None, 0, 0, None, ""
    try:
        while kod is None:
            try:
                kod = proc.wait(timeout=SHAG_SEK)
                break
            except subprocess.TimeoutExpired:
                pass
            z, p = zagruzka.zamer(), chastota.zamer()
            if z is not None:
                zagr.append(z)
            if p is None:
                podryad = 0
                continue
            perf.append(p)
            if time.time() - t0 < PROGREV_SEK or etalon is None:
                etalon = max(etalon or 0.0, p)
                continue
            etalon = max(etalon, p)
            podryad = podryad + 1 if p < DOLYA_TROTTLINGA * etalon else 0
            if podryad < PODRYAD or not v_zadanii:
                continue
            podryad = 0
            pauzy += 1
            if pauzy > PAUZ_MAKS:
                prichina = "перегрев"
                _vyvod(f"очередь: ПЕРЕГРЕВ — ядра в {PAUZ_MAKS + 1}-й раз сбросили частоту "
                       f"({p:.0f}% при эталоне {etalon:.0f}%). Работа снята. Дай компьютеру остыть, "
                       "проверь охлаждение и скажи владельцу; повторять сразу нельзя.")
                TerminateJobObject(zadanie, KOD_PEREGREV)
                kod = KOD_PEREGREV
                break
            _vyvod(f"очередь: ядра сбросили частоту ({p:.0f}% при эталоне {etalon:.0f}%) — "
                   f"похоже на перегрев; работа замерла на {PAUZA_SEK // 60} мин остыть (пауза {pauzy})")
            zamorozheny = _zamorozit(zadanie)
            try:
                tek["pauza_do"] = time.time() + PAUZA_SEK
                TEKUSHCHAYA.write_text(json.dumps(tek, ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass
            time.sleep(PAUZA_SEK)
            _razmorozit(zamorozheny)
            tek["pauza_do"] = None
            zagruzka.zamer()
            chastota.zamer()
    except KeyboardInterrupt:
        prichina, kod = "прервано", 130
    finally:
        if kod is None:  # исключение внутри цикла
            prichina, kod = prichina or "сбой очереди", 1
        if SNYATA.exists():
            prichina = "снята командой stop"
            SNYATA.unlink(missing_ok=True)
        ostalos = 0
        if zadanie and prichina:  # оборвалась — ждать нечего
            TerminateJobObject(zadanie, 1)
        if zadanie:
            konec_ozhidaniya = time.time() + DOCHISTKA_SEK
            while time.time() < konec_ozhidaniya:
                u = _uchet(zadanie)
                ostalos = u.ActiveProcesses if u else 0
                if not ostalos:
                    break
                time.sleep(1)
            uchet = _uchet(zadanie)
            TerminateJobObject(zadanie, 1)  # хвосты работы снимаются, мьютекс ещё наш
            CloseHandle(zadanie)
        else:
            uchet = None
        chastota.zakryt()
        minut = round((time.time() - t0) / 60, 2)
        zapis = {
            "start": tek["start"], "minuty": minut, "zhdal_sek": zhdal, "kod": kod,
            "prichina": prichina, "komanda": komanda[:600], "papka": tek["papka"],
            "potoki": potoki, "v_zadanii": v_zadanii,
            "zagruzka_sred": _sred(zagr), "zagruzka_pik": max(zagr) if zagr else None,
            "cpu_sek": round((uchet.TotalUserTime + uchet.TotalKernelTime) / 1e7) if uchet else None,
            "chastota_etalon": etalon, "chastota_min": min(perf) if perf else None,
            "chastota_sred": _sred(perf), "pauzy": pauzy, "hvosty_snyaty": ostalos,
        }
        try:
            with ZHURNAL.open("a", encoding="utf-8") as f:
                f.write(json.dumps(zapis, ensure_ascii=False) + "\n")
            TEKUSHCHAYA.unlink(missing_ok=True)
        except OSError:
            pass
        _vyvod(f"очередь: готово за {minut} мин, код {kod}; процессор ср {zapis['zagruzka_sred']}% "
               f"пик {zapis['zagruzka_pik']}%" + (f"; пауз на остывание {pauzy}" if pauzy else "")
               + (f"; снято оставленных процессов: {ostalos}" if ostalos else ""))
    return kod


def zapusk(argv: list[str], zhdat: int = ZHDAT_SEK) -> int:
    """Выполнить команду в очереди и вернуть её код."""
    if vnutri_ocheredi():  # очередь уже держит родитель
        return subprocess.call(argv)
    mutex = CreateMutexW(None, False, MUTEX)
    if not mutex:
        _vyvod(f"очередь: мьютекс не создан (ошибка {ctypes.get_last_error()})")
        return 70
    t0 = time.time()
    try:
        otvet = WaitForSingleObject(mutex, 0)
        if otvet == WAIT_TIMEOUT:
            _vyvod(f"очередь занята: {_opisanie(_tekushchaya())} — жду до {_srok(zhdat)}")
            otvet = WaitForSingleObject(mutex, zhdat * 1000)
        if otvet == WAIT_TIMEOUT:
            _vyvod(f"очередь занята дольше {_srok(zhdat)}: {_opisanie(_tekushchaya())}.\n"
                   "Очередь НЕ обходить и тяжёлое мимо неё не запускать. Повтори эту же команду позже. "
                   f"Что идёт: python {SKRIPT.as_posix()} status")
            return KOD_ZANYATO
        if otvet not in (WAIT_OBJECT_0, WAIT_ABANDONED):
            _vyvod(f"очередь: ожидание сорвалось (ответ {otvet}, ошибка {ctypes.get_last_error()})")
            return 70
        try:
            return _rabota(argv, round(time.time() - t0))
        finally:
            ReleaseMutex(mutex)
    finally:
        CloseHandle(mutex)


def v_ocheredi() -> None:
    """Сторож тяжёлого скрипта: запущен мимо очереди — перезапускает себя через неё."""
    if vnutri_ocheredi():
        return
    flagi = subprocess._args_from_interpreter_flags()  # -X utf8 и прочее переживут перезапуск
    sys.exit(zapusk([sys.executable, *flagi, os.path.abspath(sys.argv[0]), *sys.argv[1:]]))


# ---------------------------------------------------------------- команды

def status() -> int:
    mutex = CreateMutexW(None, False, MUTEX)
    svobodna = bool(mutex) and WaitForSingleObject(mutex, 0) in (WAIT_OBJECT_0, WAIT_ABANDONED)
    if svobodna:
        ReleaseMutex(mutex)
    if mutex:
        CloseHandle(mutex)
    tek = _tekushchaya()
    stroki = []
    if svobodna:
        stroki.append("Очередь свободна.")
    else:
        stroki.append(f"Очередь занята: {_opisanie(tek)}")
        if tek:
            stroki.append(f"  папка: {tek.get('papka')}")
            stroki.append(f"  PID очереди {tek.get('pid_ocheredi')}, работы {tek.get('pid_raboty')}; "
                          f"{tek.get('potoki')} из {tek.get('vsego_potokov')} потоков")
            if tek.get("pauza_do"):
                stroki.append(f"  пауза на остывание ещё {max(0, tek['pauza_do'] - time.time()):.0f} с")
        h = OpenJobObjectW(JOB_QUERY, False, JOB)
        if h:
            u = _uchet(h)
            CloseHandle(h)
            if u:
                stroki.append(f"  процессов в работе: {u.ActiveProcesses}, "
                              f"процессорных секунд: {(u.TotalUserTime + u.TotalKernelTime) / 1e7:.0f}")
    z = Zagruzka()
    time.sleep(1)
    stroki.append(f"Процессор сейчас: {z.zamer()}%")
    try:
        posled = ZHURNAL.read_text(encoding="utf-8").splitlines()[-5:]
    except OSError:
        posled = []
    if posled:
        stroki.append("Последние работы:")
        for s in posled:
            try:
                r = json.loads(s)
            except ValueError:
                continue
            stroki.append(f"  {r['start'][5:16].replace('T', ' ')}  {r['minuty']:>6} мин  код {r['kod']}  "
                          f"ср {r['zagruzka_sred']}% пик {r['zagruzka_pik']}%  "
                          f"частота мин {r['chastota_min']}%  пауз {r['pauzy']}  {r['komanda'][:90]}")
    _vyvod("\n".join(stroki), sys.stdout)
    return 0


def stop() -> int:
    h = OpenJobObjectW(JOB_QUERY | JOB_TERMINATE, False, JOB)
    if not h:
        _vyvod("Очередь свободна — снимать нечего.", sys.stdout)
        return 0
    u = _uchet(h)
    try:
        SNYATA.write_text("stop", encoding="utf-8")
    except OSError:
        pass
    TerminateJobObject(h, 1)
    CloseHandle(h)
    chislo = u.ActiveProcesses if u else "?"
    _vyvod(f"Снято: {_opisanie(_tekushchaya())}; процессов: {chislo}.", sys.stdout)
    return 0


def main(args: list[str]) -> int:
    if not args or args[0] in ("-h", "--help"):
        _vyvod(__doc__, sys.stdout)
        return 0 if args else 2
    if args[0] == "status":
        return status()
    if args[0] == "stop":
        return stop()
    zhdat = ZHDAT_SEK
    if args[0] == "--zhdat":
        if len(args) < 2 or not args[1].isdigit():
            _vyvod("очередь: --zhdat <секунды>")
            return 2
        zhdat, args = int(args[1]), args[2:]
    if args and args[0] == "--":
        args = args[1:]
    if not args:
        _vyvod("очередь: после -- нужна команда")
        return 2
    exe = args[0]
    if not os.path.dirname(exe):
        exe = shutil.which(exe) or exe  # npx → npx.cmd
    return zapusk([exe, *args[1:]], zhdat)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
