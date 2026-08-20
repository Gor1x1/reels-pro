# Раскладка агентов по моделям

Решение владельца 13.08.2026: **мелких моделей не держим — Haiku не
используется нигде.** Качество важнее цены токенов.

| Модель | Кто | Почему |
|---|---|---|
| **Opus** | вся секция 5 · Постинг (posting-lead, plan-keeper, packager, device-medic, wave-runner, post-verifier, ramp-keeper, seeding-agent) | цена ошибки — банк аккаунтов; решение владельца 13.08.2026 |
| **Opus** | zavod-orchestrator · retro-critic · angle-builder · tz-writer · hook-smith · format-learner | решения размножаются на девять роликов; предложения критика меняют всю систему |
| **Opus** | секция 2 · Сценарии: scenarii-lead, line-router | оркестратор секции и маршрутизация бюджета на девять роликов; решение владельца 14.08.2026 |
| **Sonnet** | секция 2 · Сценарии: persona-adapter, scene-prompter, creator-tz, dedup-check, frames-visual-check, angle-builder-check, tz-writer-check, persona-adapter-check, scene-prompter-check | массовые параллельные (×9, ×7) и проверяющие |
| **Sonnet** | секция монтажа (montage-lead, raw-editor, cut-planner, frame-fixer, speech-splitter, shot-finder) и остальные рабочие агенты | основная рабочая лошадь |
| **Opus** | секция 1 · Тренды: trend-critic | судит, хватит ли материала на неделю ТЗ; его вердикт останавливает или пропускает весь пакет. Решение владельца 20.08.2026 |
| **Sonnet** | секция 1 · Тренды: trendy-lead, ref-analyst, ref-downloader, pain-hunter, pain-marketplace, pain-forum, pain-comments, pain-social, pain-cluster, stock-reels, ref-analyst-check, pain-cluster-check, bank-keeper, combo-keeper, hook-scorer | по руководству 14.08.2026: вся секция на Sonnet — решения секции фильтруются гейтами сценариев |

Три хранителя банков (`bank-keeper`, `combo-keeper`, `hook-scorer`) добавлены
20.08.2026: работают по жёстким правилам записи и нумерации, решений
не принимают — Sonnet. Критик вынесен в строку Opus.

| ~~Sonnet~~ | ~~секция 4 · Качество: qc-vision, qc-fit, gatekeeper~~ | **ЗАМОРОЖЕНА 19.08.2026** решением владельца: ролики смотрим вручную. Файлы — `.claude\agents\_frozen\`, условия разморозки там же. Технический контроль `qc.py` продолжает работать в монтаже |
| **Sonnet** | секция 6 · Метрики: metriki-lead, metrics-writer, bonus-calc, report-writer | счёт и раскладка по правилам; решающий агент секции — format-learner, он в строке Opus |
| **Sonnet** | секция 7 · Операции: product-keeper, product-research, product-claims, product-planner, account-keeper, creator-manager | справочный слой (каталог, банк аккаунтов, креаторы) — по таблице моделей руководства от 14.08.2026 |
| **Sonnet** | секция 0 · Оркестрация: run-logger, budget-guard, cost-writer (сам zavod-orchestrator — в строке Opus) | журналы и счёт по правилам; вместо Haiku из исходного руководства |
| **Sonnet** | все проверяющие `*-check`, журналы | вместо Haiku из исходного руководства — по решению владельца |
| Haiku | — | не используется |

Агенты `zavod-*` (плейбучные) работают с `model: inherit` — наследуют
модель сессии.

Менять модель агента — только по решению владельца; фиксировать здесь
и во frontmatter агента одновременно.
