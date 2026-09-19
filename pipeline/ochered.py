"""Очередь монтажа — закон М-44 механизмом, а не просьбой к агентам.

17.09.2026 прогон видео 10 перегрел компьютер до мерцания экрана: ffmpeg по 4K
HEVC и распознавание речи шли одновременно на всех 24 потоках, а после
остановки агента ffmpeg продолжал работать. Очередь закрывает эти дыры:

- одна тяжёлая работа за раз — именованный мьютекс Windows. Процесс умер —
  мьютекс освобождается сам, очередь не залипает;
- не весь процессор — работа и всё, что она запускает, живут в объекте
  задания (job), приоритет ниже обычного. Датчик температуры жив — 9 верхних
  физических ядер с их вторыми потоками (18 из 24, решение владельца
  17.09.2026); молчит — половина (12 из 24). Замолчал на ходу — работа
  сужается до половины. Нулевое ядро остаётся ферме, системе и экрану;
- без хвостов — очередь умерла (остановили агента, истёк срок инструмента) —
  Windows убивает всё дерево работы. Что работа оставила после себя, снимается;
- перегрев — два сторожа. Температура процессора по LibreHardwareMonitor
  (http://localhost:8085): от 95 °C работа снимается сразу с кодом 76, от 85 °C
  два замера подряд — замирает, пока процессор не остынет до 70 °C (не меньше
  30 секунд, не дольше 10 минут, не остыл — код 76). Частота ядер работы
  (троттлинг): ниже 70% эталона три замера подряд — замирает на две минуты.
  Паузы общие: на четвёртую работа снимается с кодом 76. Датчик молчит —
  остаётся сторож частоты. REELS_TEMP_STOP, REELS_TEMP_PAUZA и REELS_TEMP_OSTYT
  только понижают пороги — для проверки;
- вторая, лёгкая работа рядом с тяжёлой (решение владельца 17.09.2026) —
  `--lyogkaya`. Пускается, только если вторая работа включена файлом
  vtoraya-rabota-razreshena.txt в корне reels-pro, датчик температуры жив,
  тяжёлая не остывает и процессор холоднее 70 °C. Получает два физических ядра
  сразу над нулевым (4 потока, тяжёлая их не берёт) и низкий приоритет.
  Замирает раньше тяжёлой — от 80 °C, остывает до 70 °C; не остыла за 10 минут —
  код 75 (греет тяжёлая, повторить позже). Нельзя пустить — работа встаёт
  в общую очередь, как без флага. Одна лёгкая за раз.

Запуск из C:/Ferma/factory/reels-pro:

    python pipeline/ochered.py -- ffmpeg -i in.mov ... out.mp4
    python pipeline/ochered.py -- powershell -NoProfile -File build.ps1 -Master
    python pipeline/ochered.py --zhdat 120 -- python pipeline/qc.py out/x.mp4
    python pipeline/ochered.py --lyogkaya -- python pipeline/qc.py out/x.mp4
    python pipeline/ochered.py status            что идёт сейчас и последние работы
    python pipeline/ochered.py stop              снять тяжёлую работу со всем деревом
    python pipeline/ochered.py stop --lyogkaya   снять лёгкую

Очередь занята дольше --zhdat секунд (по умолчанию 540: инструмент агента
живёт 10 минут) — выход с кодом 75. Очередь не обходить: повторить ту же
команду позже. Работа дольше 10 минут запускается в фоне инструмента, и пока
она идёт, тяжёлое не запускается — лёгкое можно через --lyogkaya.

Тяжёлые скрипты pipeline/ первой строкой зовут v_ocheredi(): запущенные мимо
очереди, они перезапускают себя через неё. Внутри тяжёлой или лёгкой работы
они идут на месте. Хук Claude (ochered_hook.py) не даёт запустить мимо очереди
ffmpeg и прочее тяжёлое.

Состояние — %LOCALAPPDATA%/reels-pro-ochered: tekushchaya.json и
tekushchaya-lyogkaya.json (что идёт), zhurnal.jsonl (минуты, код, загрузка
процессора, частота, температура, паузы; у лёгкой — "lyogkaya": true).
"""
from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

MUTEX = "Local\\reels-pro-ochered"
JOB = "Local\\reels-pro-ochered-job"
MUTEX_L = "Local\\reels-pro-ochered-lyogkaya"
JOB_L = "Local\\reels-pro-ochered-lyogkaya-job"
PAPKA = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "reels-pro-ochered"
TEKUSHCHAYA = PAPKA / "tekushchaya.json"
TEKUSHCHAYA_L = PAPKA / "tekushchaya-lyogkaya.json"
ZHURNAL = PAPKA / "zhurnal.jsonl"
SNYATA = PAPKA / "snyata.flag"
SNYATA_L = PAPKA / "snyata-lyogkaya.flag"
SKRIPT = Path(__file__).resolve()
RAZRESHENIE_L = SKRIPT.parent.parent / "vtoraya-rabota-razreshena.txt"

ZHDAT_SEK = 540            # инструмент агента живёт 10 минут
KOD_ZANYATO = 75           # EX_TEMPFAIL: повторить ту же команду позже
KOD_PEREGREV = 76          # снята после трёх пауз на остывание
SHAG_SEK = 10              # как часто меряется процессор
PROGREV_SEK = 60           # эталон частоты набирается первую минуту работы
DOLYA_TROTTLINGA = 0.70    # частота ядер работы ниже 70% своего эталона —
PODRYAD = 3                # три замера подряд — троттлинг
PAUZA_SEK = 120
PAUZ_MAKS = 3              # паузы общие: частота и температура
TEMP_URL = "http://localhost:8085/data.json"  # LibreHardwareMonitor, задача планировщика
TEMP_DATCHIKI = ("CPU Package", "Core Max")   # Nuvoton на этой плате врёт: 111 и −55 °C
TEMP_STOP = 95.0           # °C — снять сразу; TjMax Xeon E5-2690 v3 — 100 °C
TEMP_PAUZA = 85.0          # °C TEMP_PODRYAD замеров подряд — замереть остыть
TEMP_PODRYAD = 2
TEMP_OSTYT = 70.0          # °C — до скольких остывать
OSTYT_MIN_SEK = 30
OSTYT_MAKS_SEK = 600       # не остыл за 10 минут — снять с кодом 76 (лёгкую — с 75)
DOCHISTKA_SEK = 30         # сколько ждать процессы, оставленные работой
ZANYATO_YADRO = 80.0       # ядро считается занятым от 80% времени
T_YADER = 9                # физических ядер тяжёлой при живом датчике — 18 потоков из 24
                           # (решение владельца 17.09.2026); датчик молчит — половина ядер
DATCHIK_MOLCHIT = 3        # замеров подряд без датчика — широкая работа сужается до половины
L_YADER = 2                # физических ядра лёгкой работе — 4 потока
L_TEMP_PUSK = 70.0         # °C — лёгкая пускается, только если процессор холоднее
L_TEMP_PAUZA = 80.0        # °C — лёгкая замирает раньше тяжёлой
POTOKOVYE = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
             "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")

WAIT_OBJECT_0, WAIT_ABANDONED, WAIT_TIMEOUT = 0x0, 0x80, 0x102
CREATE_SUSPENDED = 0x4
BELOW_NORMAL, IDLE = 0x4000, 0x40
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


class Slot:
    """Место в очереди: тяжёлая работа или лёгкая рядом с ней."""

    def __init__(self, lyogkaya: bool) -> None:
        self.lyogkaya = lyogkaya
        self.imya = "лёгкая работа" if lyogkaya else "работа"
        self.mutex = MUTEX_L if lyogkaya else MUTEX
        self.job = JOB_L if lyogkaya else JOB
        self.tekushchaya = TEKUSHCHAYA_L if lyogkaya else TEKUSHCHAYA
        self.snyata = SNYATA_L if lyogkaya else SNYATA
        self.prioritet = IDLE if lyogkaya else BELOW_NORMAL
        self.prioritet_slovami = "низкий" if lyogkaya else "ниже обычного"
        self.temp_pauza = L_TEMP_PAUZA if lyogkaya else TEMP_PAUZA

    def maska(self) -> int:
        return maska_lyogkoy() if self.lyogkaya else maska_raboty(temperatura() is not None)


TYAZHELAYA, LYOGKAYA = Slot(False), Slot(True)


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


def temperatura() -> float | None:
    """Самое горячее из CPU Package и Core Max по LibreHardwareMonitor, °C.

    Датчики ищутся по имени и SensorId процессора, а не по месту в дереве: у
    CPU Package есть и одноимённый датчик мощности. Значение приходит строкой
    «42,0 °C» с запятой. Любая ошибка — None: сторож не должен ронять работу."""
    try:
        otkryt = urllib.request.build_opener(urllib.request.ProxyHandler({})).open
        with otkryt(TEMP_URL, timeout=2) as r:
            stek = [json.loads(r.read().decode("utf-8"))]
        znach: list[float] = []
        while stek:
            uzel = stek.pop()
            if not isinstance(uzel, dict):
                continue
            deti = uzel.get("Children")
            stek.extend(deti if isinstance(deti, list) else [])
            sid = str(uzel.get("SensorId") or "")
            if uzel.get("Text") not in TEMP_DATCHIKI or "cpu/" not in sid or "/temperature/" not in sid:
                continue
            try:
                t = float(str(uzel.get("Value") or "").split()[0].replace(",", "."))
            except (ValueError, IndexError):
                continue
            if 0 < t < 110:  # вне этого — сбой чтения, а не температура
                znach.append(t)
        return max(znach) if znach else None
    except Exception:
        return None


def _porog(imya: str, obychnyy: float) -> float:
    """Порог из REELS_TEMP_*: только ниже обычного — для проверки, ослабить нельзя."""
    try:
        return min(obychnyy, float(os.environ.get(imya, "").replace(",", ".")))
    except ValueError:
        return obychnyy


# ---------------------------------------------------------------- задание

def _yadra() -> list[int]:
    """Маски физических ядер процесса (каждая — вместе со вторым потоком), по возрастанию."""
    svoya, sistema = ctypes.c_size_t(), ctypes.c_size_t()
    if not GetProcessAffinityMask(GetCurrentProcess(), ctypes.byref(svoya), ctypes.byref(sistema)):
        return []
    razmer = DW(0)
    GetLogicalProcessorInformation(None, ctypes.byref(razmer))
    n = razmer.value // ctypes.sizeof(SLPI)
    buf = (SLPI * max(n, 1))()
    if not n or not GetLogicalProcessorInformation(buf, ctypes.byref(razmer)):
        return []
    return sorted(m for m in (e.ProcessorMask & svoya.value for e in buf[:n] if e.Relationship == 0) if m)


def maska_raboty(s_datchikom: bool = False) -> int:
    """Верхние физические ядра с их вторыми потоками: датчик температуры жив —
    T_YADER ядер, молчит — половина. Нулевое ядро и ядра лёгкой не берутся."""
    yadra, maska = _yadra(), 0
    skolko = min(T_YADER, len(yadra) - 1 - L_YADER) if s_datchikom else 0
    for m in yadra[-max(1, len(yadra) // 2, skolko):]:
        maska |= m
    return maska


def maska_lyogkoy() -> int:
    """L_YADER физических ядра сразу над нулевым — под любой шириной тяжёлой работы."""
    yadra, maska = _yadra(), 0
    for m in yadra[1:1 + L_YADER]:
        maska |= m
    return maska


def vnutri_ocheredi() -> bool:
    """Процесс уже внутри задания очереди, тяжёлой или лёгкой, — вложенный вызов, ждать нечего."""
    for imya in (JOB, JOB_L):
        h = OpenJobObjectW(JOB_QUERY, False, imya)
        if not h:
            continue
        try:
            v = wintypes.BOOL()
            if IsProcessInJob(GetCurrentProcess(), h, ctypes.byref(v)) and v.value:
                return True
        finally:
            CloseHandle(h)
    return False


def _sozdat_zadanie(maska: int, slot: Slot) -> tuple[int | None, bool, str]:
    """(задание, приоритет задан заданием, что не вышло)."""
    staroe = OpenJobObjectW(JOB_QUERY | JOB_TERMINATE, False, slot.job)
    if staroe:  # мьютекс наш, а задание живо — хвост оборванной работы
        TerminateJobObject(staroe, 1)
        CloseHandle(staroe)
    h = CreateJobObjectW(None, slot.job)
    if not h:
        return None, False, f"задание не создано (ошибка {ctypes.get_last_error()})"
    if _potolki(h, maska, slot, True):
        return h, True, ""
    if _potolki(h, maska, slot, False):  # приоритет без привилегии не ставится — зададим процессу
        return h, False, ""
    oshibka = ctypes.get_last_error()
    CloseHandle(h)
    return None, False, f"потолки заданию не выставлены (ошибка {oshibka})"


def _potolki(zadanie, maska: int, slot: Slot, s_prioritetom: bool) -> bool:
    """Ядра и приоритет заданию. Зовётся и на ходу: датчик замолчал — работа сужается."""
    info = EXTENDED_LIMIT()
    info.Basic.Affinity = maska
    info.Basic.PriorityClass = slot.prioritet
    info.Basic.LimitFlags = (LIMIT_KILL_ON_CLOSE | LIMIT_DIE_ON_EXCEPTION | (LIMIT_AFFINITY if maska else 0)
                             | (LIMIT_PRIORITY if s_prioritetom else 0))
    return bool(SetInformationJobObject(zadanie, JOB_EXTENDED_LIMIT, ctypes.byref(info), ctypes.sizeof(info)))


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

def _tekushchaya(slot: Slot = TYAZHELAYA) -> dict | None:
    try:
        return json.loads(slot.tekushchaya.read_text(encoding="utf-8"))
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


def _zapisat(slot: Slot, tek: dict, **izmeneniya) -> None:
    tek.update(izmeneniya)
    try:
        slot.tekushchaya.write_text(json.dumps(tek, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def lyogkoy_nelzya() -> str:
    """Пусто — лёгкую работу можно пустить рядом с тяжёлой; иначе почему нельзя."""
    if not RAZRESHENIE_L.exists():
        return f"вторая работа не включена (нет файла {RAZRESHENIE_L.name})"
    if not maska_lyogkoy():
        return "ядер для второй работы нет"
    tek = _tekushchaya(TYAZHELAYA)
    if tek and (tek.get("pauza_do") or 0) > time.time():
        return "тяжёлая работа стоит на остывании"
    t = temperatura()
    if t is None:
        return f"датчик температуры молчит ({TEMP_URL})"
    if t >= L_TEMP_PUSK:
        return f"процессор {t:.0f} °C, вторая работа пускается до {L_TEMP_PUSK:.0f} °C"
    return ""


def _ostyvanie(slot: Slot, tek: dict, po_temperature: bool, temp: list[float], porog_stop: float,
               porog_ostyt: float) -> tuple[str, int]:
    """Работа заморожена — ждать. ("", 0) — пауза кончилась; иначе (за что снять, код).

    Пауза по частоте — PAUZA_SEK. По температуре — пока процессор не остынет до
    porog_ostyt, но не меньше OSTYT_MIN_SEK и не дольше OSTYT_MAKS_SEK. Датчик
    замолчал — пауза как по частоте. Лёгкая, не дождавшаяся остывания, снимается
    с кодом 75: процессор греет тяжёлая, это не авария."""
    nachalo = time.time()
    _zapisat(slot, tek, pauza_do=nachalo + (OSTYT_MAKS_SEK if po_temperature else PAUZA_SEK))
    try:
        while True:
            time.sleep(SHAG_SEK)
            t, proshlo = temperatura(), time.time() - nachalo
            if t is not None:
                temp.append(t)
                if t >= porog_stop:
                    return f"процессор {t:.0f} °C на паузе, предел {porog_stop:.0f} °C", KOD_PEREGREV
            if not po_temperature or t is None:
                if proshlo >= PAUZA_SEK:
                    return "", 0
            elif t <= porog_ostyt:
                if proshlo >= OSTYT_MIN_SEK:
                    return "", 0
            elif proshlo >= OSTYT_MAKS_SEK:
                return (f"процессор не остыл за {_srok(OSTYT_MAKS_SEK)}: {t:.0f} °C",
                        KOD_ZANYATO if slot.lyogkaya else KOD_PEREGREV)
    finally:
        _zapisat(slot, tek, pauza_do=None)


def _snyat(zadanie, proc: subprocess.Popen, v_zadanii: bool, chto: str, kod: int) -> None:
    if kod == KOD_PEREGREV:
        _vyvod(f"очередь: ПЕРЕГРЕВ — {chto}. Работа снята с кодом {KOD_PEREGREV}. Дай компьютеру "
               "остыть, проверь охлаждение и скажи владельцу; повторять сразу нельзя.")
    else:
        _vyvod(f"очередь: лёгкая работа снята с кодом {kod} — {chto}; процессор греет тяжёлая работа. "
               "Повтори эту же команду позже.")
    if v_zadanii:
        TerminateJobObject(zadanie, kod)
    else:
        proc.kill()


def _rabota(argv: list[str], zhdal: int, slot: Slot) -> int:
    PAPKA.mkdir(parents=True, exist_ok=True)
    slot.snyata.unlink(missing_ok=True)
    komanda = subprocess.list2cmdline(argv)
    maska = slot.maska()
    potoki = bin(maska).count("1") if maska else (os.cpu_count() or 1)
    vsego = os.cpu_count() or potoki
    zadanie, prioritet_zadaniem, beda = _sozdat_zadanie(maska, slot)
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
        SetPriorityClass(hp, slot.prioritet)  # класс приоритета наследуют дети
    NtResumeProcess(hp)

    tek = {"t0": t0, "start": datetime.fromtimestamp(t0).isoformat(timespec="seconds"),
           "komanda": komanda, "papka": os.getcwd(), "pid_ocheredi": os.getpid(),
           "pid_raboty": proc.pid, "potoki": potoki, "vsego_potokov": vsego, "pauza_do": None,
           "lyogkaya": slot.lyogkaya}
    _zapisat(slot, tek)
    _vyvod(f"очередь: {slot.imya} пошла — {potoki} из {vsego} потоков, приоритет {slot.prioritet_slovami}"
           + (" (рядом с тяжёлой)" if slot.lyogkaya else ""))

    zagruzka, chastota = Zagruzka(), Chastota(maska)
    porog_stop, porog_pauza = _porog("REELS_TEMP_STOP", TEMP_STOP), _porog("REELS_TEMP_PAUZA", slot.temp_pauza)
    porog_ostyt = _porog("REELS_TEMP_OSTYT", TEMP_OSTYT)
    zagr, perf, temp = [], [], []
    etalon, podryad, goryachih, pauzy, kod, prichina = None, 0, 0, 0, None, ""
    datchik_molchal, molchit, suzhena_do = False, 0, None
    try:
        while kod is None:
            try:
                kod = proc.wait(timeout=SHAG_SEK)
                break
            except subprocess.TimeoutExpired:
                pass
            z, p, t = zagruzka.zamer(), chastota.zamer(), temperatura()
            if z is not None:
                zagr.append(z)
            snyat, kod_snyatiya, pauza, po_temperature = "", KOD_PEREGREV, "", False
            if t is None:
                goryachih, molchit = 0, molchit + 1
                if not datchik_molchal:
                    datchik_molchal = True
                    _vyvod(f"очередь: датчик температуры молчит ({TEMP_URL}) — слежу только за частотой "
                           "ядер. LibreHardwareMonitor запускает задача планировщика от администратора.")
                uzkaya = maska_raboty()
                if (molchit == DATCHIK_MOLCHIT and v_zadanii and not slot.lyogkaya and not suzhena_do
                        and potoki > bin(uzkaya).count("1") and _potolki(zadanie, uzkaya, slot, prioritet_zadaniem)):
                    suzhena_do = bin(uzkaya).count("1")
                    _zapisat(slot, tek, potoki=suzhena_do)
                    _vyvod(f"очередь: датчик замолчал под широкой работой — оставляю ей {suzhena_do} из {vsego} "
                           "потоков. Шире — только при живом датчике (ярлык «Датчик температуры»).")
            else:
                molchit = 0
                temp.append(t)
                goryachih = goryachih + 1 if t >= porog_pauza else 0
                if t >= porog_stop:
                    snyat = f"процессор {t:.0f} °C, предел {porog_stop:.0f} °C"
                elif goryachih >= TEMP_PODRYAD:
                    pauza, po_temperature = f"процессор {t:.0f} °C {goryachih} замера подряд", True
            if p is None:
                podryad = 0
            else:
                perf.append(p)
                if time.time() - t0 < PROGREV_SEK or etalon is None:
                    etalon = max(etalon or 0.0, p)
                else:
                    etalon = max(etalon, p)
                    podryad = podryad + 1 if p < DOLYA_TROTTLINGA * etalon else 0
                    if podryad >= PODRYAD and not pauza:
                        pauza = f"ядра сбросили частоту ({p:.0f}% при эталоне {etalon:.0f}%)"
            if pauza and v_zadanii and not snyat:
                podryad = goryachih = 0
                if pauzy >= PAUZ_MAKS:
                    snyat = f"{pauza}, остывать в {pauzy + 1}-й раз"
                else:
                    pauzy += 1
                    _vyvod(f"очередь: {pauza} — {slot.imya} замерла остыть "
                           + (f"до {porog_ostyt:.0f} °C" if po_temperature else f"на {PAUZA_SEK // 60} мин")
                           + f" (пауза {pauzy} из {PAUZ_MAKS})")
                    zamorozheny = _zamorozit(zadanie)
                    snyat, kod_snyatiya = _ostyvanie(slot, tek, po_temperature, temp, porog_stop, porog_ostyt)
                    if not snyat:
                        _razmorozit(zamorozheny)
                        _vyvod(f"очередь: пауза кончилась — {slot.imya} идёт дальше")
                        zagruzka.zamer()
                        chastota.zamer()
            if snyat:
                prichina = (f"перегрев: {snyat}" if kod_snyatiya == KOD_PEREGREV else f"не остыла: {snyat}")
                kod = kod_snyatiya
                _snyat(zadanie, proc, v_zadanii, snyat, kod)
                break
    except KeyboardInterrupt:
        prichina, kod = "прервано", 130
    finally:
        if kod is None:  # исключение внутри цикла
            prichina, kod = prichina or "сбой очереди", 1
        if slot.snyata.exists():
            prichina = "снята командой stop"
            slot.snyata.unlink(missing_ok=True)
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
            "chastota_sred": _sred(perf), "temp_maks": max(temp) if temp else None,
            "temp_sred": _sred(temp), "pauzy": pauzy, "hvosty_snyaty": ostalos,
        }
        if slot.lyogkaya:
            zapis["lyogkaya"] = True
        if suzhena_do:
            zapis["suzhena_do"] = suzhena_do
        try:
            with ZHURNAL.open("a", encoding="utf-8") as f:
                f.write(json.dumps(zapis, ensure_ascii=False) + "\n")
            slot.tekushchaya.unlink(missing_ok=True)
        except OSError:
            pass
        _vyvod(f"очередь: {'лёгкая работа ' if slot.lyogkaya else ''}готово за {minut} мин, код {kod}; "
               f"процессор ср {zapis['zagruzka_sred']}% пик {zapis['zagruzka_pik']}%"
               + (f"; процессор до {max(temp):.0f} °C" if temp else "")
               + (f"; пауз на остывание {pauzy}" if pauzy else "")
               + (f"; снято оставленных процессов: {ostalos}" if ostalos else ""))
    return kod


def _v_slote(argv: list[str], zhdat: int, slot: Slot) -> int | None:
    """Дождаться места и выполнить. None — лёгкой, пока ждала, пускать стало нельзя."""
    mutex = CreateMutexW(None, False, slot.mutex)
    if not mutex:
        _vyvod(f"очередь: мьютекс не создан (ошибка {ctypes.get_last_error()})")
        return 70
    chya = "лёгкая очередь" if slot.lyogkaya else "очередь"
    t0 = time.time()
    try:
        otvet = WaitForSingleObject(mutex, 0)
        if otvet == WAIT_TIMEOUT:
            _vyvod(f"{chya} занята: {_opisanie(_tekushchaya(slot))} — жду до {_srok(zhdat)}")
            otvet = WaitForSingleObject(mutex, zhdat * 1000)
        if otvet == WAIT_TIMEOUT:
            _vyvod(f"{chya} занята дольше {_srok(zhdat)}: {_opisanie(_tekushchaya(slot))}.\n"
                   "Очередь НЕ обходить и тяжёлое мимо неё не запускать. Повтори эту же команду позже. "
                   f"Что идёт: python {SKRIPT.as_posix()} status")
            return KOD_ZANYATO
        if otvet not in (WAIT_OBJECT_0, WAIT_ABANDONED):
            _vyvod(f"очередь: ожидание сорвалось (ответ {otvet}, ошибка {ctypes.get_last_error()})")
            return 70
        try:
            if slot.lyogkaya and lyogkoy_nelzya():
                return None
            return _rabota(argv, round(time.time() - t0), slot)
        finally:
            ReleaseMutex(mutex)
    finally:
        CloseHandle(mutex)


def zapusk(argv: list[str], zhdat: int = ZHDAT_SEK, lyogkaya: bool = False) -> int:
    """Выполнить команду в очереди и вернуть её код. lyogkaya — рядом с тяжёлой, если можно."""
    if vnutri_ocheredi():  # очередь уже держит родитель
        return subprocess.call(argv)
    t0 = time.time()
    if lyogkaya:
        nelzya = lyogkoy_nelzya()
        if not nelzya:
            kod = _v_slote(argv, zhdat, LYOGKAYA)
            if kod is not None:
                return kod
            nelzya = lyogkoy_nelzya() or "пока ждала место, пускать стало нельзя"
        _vyvod(f"очередь: лёгкая работа встаёт в общую очередь — {nelzya}")
    return _v_slote(argv, max(0, zhdat - round(time.time() - t0)), TYAZHELAYA)


def v_ocheredi() -> None:
    """Сторож тяжёлого скрипта: запущен мимо очереди — перезапускает себя через неё."""
    if vnutri_ocheredi():
        return
    flagi = subprocess._args_from_interpreter_flags()  # -X utf8 и прочее переживут перезапуск
    sys.exit(zapusk([sys.executable, *flagi, os.path.abspath(sys.argv[0]), *sys.argv[1:]]))


# ---------------------------------------------------------------- команды

def _svobodno(slot: Slot) -> bool:
    mutex = CreateMutexW(None, False, slot.mutex)
    svobodna = bool(mutex) and WaitForSingleObject(mutex, 0) in (WAIT_OBJECT_0, WAIT_ABANDONED)
    if svobodna:
        ReleaseMutex(mutex)
    if mutex:
        CloseHandle(mutex)
    return svobodna


def _stroki_zanyato(slot: Slot, tek: dict | None) -> list[str]:
    stroki = []
    if tek:
        stroki.append(f"  папка: {tek.get('papka')}")
        stroki.append(f"  PID очереди {tek.get('pid_ocheredi')}, работы {tek.get('pid_raboty')}; "
                      f"{tek.get('potoki')} из {tek.get('vsego_potokov')} потоков")
        if tek.get("pauza_do"):
            stroki.append(f"  работа замерла остыть, не дольше ещё {max(0, tek['pauza_do'] - time.time()):.0f} с")
    h = OpenJobObjectW(JOB_QUERY, False, slot.job)
    if h:
        u = _uchet(h)
        CloseHandle(h)
        if u:
            stroki.append(f"  процессов в работе: {u.ActiveProcesses}, "
                          f"процессорных секунд: {(u.TotalUserTime + u.TotalKernelTime) / 1e7:.0f}")
    return stroki


def status() -> int:
    stroki = []
    if _svobodno(TYAZHELAYA):
        stroki.append("Очередь свободна.")
    else:
        tek = _tekushchaya(TYAZHELAYA)
        stroki.append(f"Очередь занята: {_opisanie(tek)}")
        stroki.extend(_stroki_zanyato(TYAZHELAYA, tek))
    if _svobodno(LYOGKAYA):
        nelzya = lyogkoy_nelzya()
        stroki.append("Вторая (лёгкая) работа: место свободно; "
                      + ("пустить сейчас можно." if not nelzya else f"сейчас не пускается — {nelzya}."))
    else:
        tek = _tekushchaya(LYOGKAYA)
        stroki.append(f"Вторая (лёгкая) работа идёт: {_opisanie(tek)}")
        stroki.extend(_stroki_zanyato(LYOGKAYA, tek))
    z = Zagruzka()
    time.sleep(1)
    stroki.append(f"Процессор сейчас: {z.zamer()}%")
    t = temperatura()
    stroki.append(f"Температура процессора: {t:.0f} °C (замереть от {TEMP_PAUZA:.0f} °C, лёгкой — от "
                  f"{L_TEMP_PAUZA:.0f} °C, снять от {TEMP_STOP:.0f} °C)"
                  if t is not None else f"Температура процессора: датчик молчит ({TEMP_URL})")
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
                          f"частота мин {r['chastota_min']}%  t° макс {r.get('temp_maks')}  пауз {r['pauzy']}  "
                          + ("лёгкая  " if r.get("lyogkaya") else "") + f"{r['komanda'][:90]}")
    _vyvod("\n".join(stroki), sys.stdout)
    return 0


def stop(slot: Slot = TYAZHELAYA) -> int:
    h = OpenJobObjectW(JOB_QUERY | JOB_TERMINATE, False, slot.job)
    if not h:
        _vyvod(("Лёгкой работы нет" if slot.lyogkaya else "Очередь свободна") + " — снимать нечего.", sys.stdout)
        return 0
    u = _uchet(h)
    try:
        slot.snyata.write_text("stop", encoding="utf-8")
    except OSError:
        pass
    TerminateJobObject(h, 1)
    CloseHandle(h)
    chislo = u.ActiveProcesses if u else "?"
    _vyvod(f"Снято: {_opisanie(_tekushchaya(slot))}; процессов: {chislo}.", sys.stdout)
    return 0


def main(args: list[str]) -> int:
    if not args or args[0] in ("-h", "--help"):
        _vyvod(__doc__, sys.stdout)
        return 0 if args else 2
    if args[0] == "status":
        return status()
    if args[0] == "stop":
        return stop(LYOGKAYA if "--lyogkaya" in args[1:] else TYAZHELAYA)
    zhdat, lyogkaya = ZHDAT_SEK, False
    while args and args[0] in ("--zhdat", "--lyogkaya"):
        if args[0] == "--lyogkaya":
            lyogkaya, args = True, args[1:]
            continue
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
    return zapusk([exe, *args[1:]], zhdat, lyogkaya)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
