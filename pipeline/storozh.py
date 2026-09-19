"""
Вотчдог студии монтажа — обнаруживает смерть студии СНАРУЖИ чата, который
её ведёт.

Дважды студия умирала от лимита сессии (HTTP 429), и час-десять часов никто
не замечал: сторожа прошлых чатов (storozh-studii.sh, zhdat-studiyu.sh) сами
умирают вместе с чатом-студией, для внешнего наблюдения не годятся. Этот
скрипт запускает scheduled task (mcp__scheduled-tasks__create_scheduled_task,
не CronCreate — тот session-only): каждый прогон — свежая независимая сессия,
переживает закрытие чата-студии.

    python pipeline/storozh.py [--zhivoy ПУТЬ ...]

Печатает первым словом ЖИВА / НЕТ / УМЕРЛА и код возврата 0/0/1 — вызывающий
может судить и по тексту, и по коду. Только обнаружение и отчёт, без
авто-воскрешения: риск столкнуться с ещё живой, просто медленной студией
и задвоить тяжёлую работу (вопреки М-44) не оправдан этим приростом пользы.

Признак жизни — самое свежее из: хода `rezhisser-hod.json`, любого файла в
папке прогона и (если переданы) журналов субагентов `--zhivoy` (файл или
папка с `*.jsonl`). Один ход-файл не годится: он пополняется по окончании шага,
а шаг «смысл» идёт десятки минут — 18.09.2026 сторож объявил живую студию
мёртвой на 27-й минуте, хотя отдел писал журнал и файлы прогона (М-51, поправка).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ochered  # переиспользуем _svobodno — вторая проверка очереди не нужна

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"

# те же числа, что уже дважды работали как рабочие в сторожах прошлых чатов
MIN_SVOBODNO = 20   # минут тишины при свободной очереди — студия должна что-то делать
MIN_ZANYATO = 45    # минут тишины при занятой очереди — тяжёлый шаг мог идти долго
MIN_POTOLOK = 180   # минут тишины в любом случае, независимо от очереди


def nezakrytye() -> list[Path]:
    """Папки прогона: rezhisser-hod.json есть, doklad-studii.md — нет (студия не закрыла работу)."""
    if not RUNS.exists():
        return []
    return sorted(
        p.parent for p in RUNS.glob("*/*/rezhisser-hod.json")
        if not (p.parent / "doklad-studii.md").exists()
    )


def _svezhest(papka: Path, zhivoy: list[Path]) -> tuple[float, str]:
    """(метка времени, чем подтверждена жизнь): самое свежее из хода, файлов прогона и журналов субагентов."""
    luchshee = ((papka / "rezhisser-hod.json").stat().st_mtime, "ход")
    kandidaty: list[Path] = [f for f in papka.rglob("*") if f.is_file()]
    for p in zhivoy:
        kandidaty += list(p.glob("*.jsonl")) if p.is_dir() else [p]
    for f in kandidaty:
        try:
            m = f.stat().st_mtime
        except OSError:  # файл исчез между обходом и чтением
            continue
        if m > luchshee[0]:
            luchshee = (m, f.name)
    return luchshee


def proverit(zhivoy: list[Path] | None = None) -> tuple[int, str]:
    """(код, отчёт). Код 0 — жива или нет активного прогона, 1 — УМЕРЛА."""
    papki = nezakrytye()
    if not papki:
        return 0, "НЕТ активного прогона"

    # несколько незакрытых сразу — смотрим на самую свежую; более старые
    # молчат заведомо дольше потолка и не добавляют новой информации
    papka = max(papki, key=lambda p: _svezhest(p, zhivoy or [])[0])
    mtime, chem = _svezhest(papka, zhivoy or [])
    tishina = (time.time() - mtime) / 60

    zanyato = not ochered._svobodno(ochered.TYAZHELAYA)
    porog = MIN_ZANYATO if zanyato else MIN_SVOBODNO
    sostoyanie = "очередь занята" if zanyato else "очередь свободна"

    if tishina >= MIN_POTOLOK:
        return 1, (f"УМЕРЛА: {papka.name} молчит {tishina:.0f} мин "
                    f"(потолок {MIN_POTOLOK} мин независимо от очереди)")
    if tishina >= porog:
        return 1, f"УМЕРЛА: {papka.name} молчит {tishina:.0f} мин, {sostoyanie} (порог {porog} мин)"
    return 0, (f"ЖИВА: {papka.name}, тишина {tishina:.0f} мин (последнее: {chem}), "
               f"{sostoyanie} (порог {porog} мин)")


def main(argv: list[str]) -> int:
    zhivoy: list[Path] = []
    it = iter(argv)
    for a in it:
        if a == "--zhivoy":
            zhivoy.append(Path(next(it, "")))
    kod, text = proverit(zhivoy)
    ochered._vyvod(text, sys.stdout)
    return kod


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
