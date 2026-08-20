# Reels Pro — скилл для Claude Code

**Что это.** Скилл, который превращает сырое видео в готовый к публикации
вертикальный ролик (Reels / TikTok / Shorts) — без ручного редактора вроде
CapCut или Premiere.

Claude читает исходники, разбирает речь, вырезает лишнее, собирает ролик из
нескольких файлов по сценарию, ставит титры и графику, сводит звук и рендерит
финал. Монтаж описывается спецификацией `spec.json`, внешний вид переключается
одной строкой — стилем.

**Зачем.** Ручной монтаж одного ролика занимает часы. Здесь тот же результат
собирается за минуты и повторяется на следующем видео без переделки.

## Установка

```powershell
git clone https://github.com/Gor1x1/reels-pro C:\Ferma\factory\reels-pro
cd C:\Ferma\factory\reels-pro
npm install
New-Item -ItemType Junction -Path "$env:USERPROFILE\.claude\skills\reels-pro" -Target (Get-Location)
```

Нужны Node 18+, Python 3.10+, ffmpeg. Инструкции для агента — в [SKILL.md](SKILL.md).

---

## Что умеет

| Этап | Чем делается |
|---|---|
| Сценарий от сценариста → спека монтажа и субтитры | `pipeline/script2spec.py` |
| Речь автора против закадровой подсказки | `pipeline/speechsplit.py` |
| Субтитры: выравнивание известного текста по звуку | `pipeline/align.py` |
| Кадрирование горизонтали с трекингом | `pipeline/smartcrop.py` |
| Варианты ролика для разных аккаунтов | `pipeline/uniquify.py` |
| Голоса личностей: поиск, образцы, привязка | `voicescan.py`, `voicebank.py`, `personas.py` |
| Разбор исходников: длительность, паузы, громкость, чужие склейки, кадры | `pipeline/scan.py` |
| Приведение разных файлов к 1080×1920 30 fps h264+aac | `pipeline/prep.py shots` |
| Сборка одного ролика из 3–5 источников по таймкодам | сцены `clip` в спеке |
| Работа с чужими рилсами: зум со сдвигом кадра, звук исходника | `pan`, `mute` в сцене |
| Замена фона | `pipeline/matte.py` — AI-матирование, работает там, где хромакей рвёт лицо |
| Субтитры | девять видов анимации, привязка к безопасным зонам площадок |
| Товарная графика | до/после, оффер, указатель, шаги, отзыв, счётчик |
| Музыка и эффекты | `pipeline/music.py`, `pipeline/sfx.py` — свои, без чужих лицензий |
| Звук | чистка речи, мастеринг −14 LUFS, музыка проседает под голос |
| Проверка спеки до рендера | `pipeline/validate.py` — ловит брак до того, как он стоил минут |
| Проверка перед публикацией | `pipeline/qc.py` — числами, а не на глаз |
| Сборка и рендер | Remotion |

---

## Быстрый старт

```powershell
# сценарий от сценариста → спека монтажа и субтитры
python pipeline\script2spec.py runs\2026-08-12\M1-K1-ГЕЛ-001\script.json

# разобрать исходники и посмотреть, что в них
python pipeline\scan.py full raw\*.mp4 --frames-dir runs\frames --out runs\map.json

# привести к общему формату
python pipeline\prep.py shots raw\a.mp4 raw\b.mp4 raw\c.mp4 --out public\src

# музыка под длину ролика
python pipeline\music.py --sec 28 --mood energetic --out public\music.mp3

# проверить спеку до рендера — ловит брак за секунды вместо минут
python pipeline\validate.py

# собрать и проверить
.\build.ps1 -Out out\master.mp4 -Master
```

Рендер запускать только через `build.ps1`: Remotion ищет `public/` и точку
входа относительно рабочего каталога, из другой папки все файлы отдадут 404.

Предпросмотр всех стилей и всех анимаций субтитров: `npx remotion studio`.

---

## Спецификация ролика

```jsonc
{
  "style": "bold-orange",
  "lang": "hy",
  "platform": "multi",
  "captionAnim": "word-pop",
  "music": "music.mp3",
  "duck": true,
  "scenes": [
    { "type": "hook", "sec": 2.6, "src": "src/a.mp4", "isVideo": true, "in": 1.0,
      "title": "ԲԻԾԸ ՉԻ ՀԵՌԱՆՈՒՄ" },
    { "type": "clip", "sec": 4.0, "src": "src/b.mp4", "in": 3.0, "enter": "whip" },
    { "type": "compare", "sec": 4.0,
      "before": { "src": "src/b.mp4", "isVideo": true, "label": "ՄԻՆՉ" },
      "after":  { "src": "src/d.mp4", "isVideo": true, "label": "ՀԵՏՈ" } },
    { "type": "cta", "sec": 3, "line1": "ՊԱՏՎԻՐԻՐ", "line2": "ՀԻՄԱ" }
  ]
}
```

`in` — с какой секунды исходника берётся кусок. Резка происходит на рендере,
исходные файлы не портятся.

Полный справочник сцен, накладок и анимаций — в [SKILL.md](SKILL.md).

---

## Стили и темп

Восемь стилей: `warm-studio` · `bold-orange` · `clean-minimal` · `neon-night` ·
`fresh-mint` · `soft-cream` · `mono-punch` · `night-gold`.

Темп монтажа — отдельная ось: `calm` · `normal` · `fast` · `punch`. Он задаёт
скорость склеек, зумов и появления титров, поэтому одна и та же палитра
работает и в спокойном обзоре, и в быстром продающем ролике.

Эмодзи выключены во всех стилях: они удешевляют картинку. Логотип бренда
появляется только если он явно задан в спеке — значений по умолчанию нет.

---

## Папки товаров

```powershell
python pipeline\product.py new гель-дюрин --title "Гель для стирки Дюрин"
python pipeline\product.py list
```

Создаёт раскладку в `C:\Ferma\factory\products\<товар>\`: карточка, фото,
банк рилсов, музыка и по папке на каждого из девяти креаторов —
`raw` (сырьё), `ready` (мастера), `published` (что уже ушло в сети).

---

## Требования

Node.js 18+, Python 3.10+, ffmpeg. Для матирования — модель
[RobustVideoMatting](https://github.com/PeterL1n/RobustVideoMatting)
(`rvm_mobilenetv3_fp32.onnx`).

## Лицензия

MIT
