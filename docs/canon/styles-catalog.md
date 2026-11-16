---
type: catalog
created: 2026-09-16
updated: 2026-11-16
tags: [montage-style, catalog]
---

# Montage styles catalog

All the styles that exist and will exist. None of them is "the main one": the style is chosen
to fit the meaning of the reel. In the original catalog every row has a real engine frame from
the owner's first reel; mock-ups have a layout sketch (images are not included in this package).

**How to use.** Want a specific style — write "edit it in the Workshop style". If you do not
name one, the montage agent chooses by the rules table below and explains in the report why it
chose this one. The social-media agent chooses the same way.

**Statuses.** "In engine" — renders right away. "Mock-up" — the layout is approved, the engine
components are still being written.

| Style | Code | Status | When to use |
|---|---|---|---|
| Workshop | `cex` | in engine | Numbers and scale: how many posts, how many pages, how many times more views. Proof through a system. Selling the course about the farm. |
| Light breakdown | `light-talk` | in engine | Explaining a tool, a step-by-step scheme, a course lesson, calm expertise. |
| Warm studio | `warm-studio` | in engine | Expert talk to camera, a personal story, calm delivery. |
| Bold orange | `bold-orange` | in engine | Straight selling, unboxing, a find, hype. |
| Clean minimal | `clean-minimal` | in engine | Instructions, a guide, explaining without pressure. |
| Night neon | `neon-night` | in engine | Tech, gadgets, a dark frame, AI. |
| Fresh mint | `fresh-mint` | in engine | Cleanliness, before/after, water, household goods. |
| Soft cream | `soft-cream` | in engine | Care, home, a light soft frame. |
| Mono contrast | `mono-punch` | in engine | A strict breakdown, comparison, premium without decoration. |
| Night gold | `night-gold` | in engine | A premium product, a gift, an expensive look. |
| Gloss | `gloss` | mock-up | When you need to look "the way it's done" in the info-business — a breakdown, expertise with graphics. |
| Typography, no face | `tipo` | mock-up | News, numbers, breakdowns, short lessons where a face is not needed. |
| Glass and volume | `glass` | mock-up | An announcement, a "wow" reel about technology, when you need brightness. |
| Retro poster | `retro` | mock-up | A provocative headline, a meme, a high-contrast reel that has to stand out in the feed. |

## Rules for the agent's choice of style

The style is chosen from the meaning breakdown of the reel (`smysl.json`), not by taste.
The first match from top to bottom wins:

1. The reel has numbers, scale, "before → after" in figures → **Workshop**.
2. A tool or a sequence of steps is explained, it is a lesson → **Light breakdown**.
3. There is no face in the frame or it is not needed, the reel stands on facts → **Typography**
   (while it is a mock-up — Light breakdown until it is ready).
4. A personal story, emotion, a heart-to-heart talk → **Warm studio**.
5. A provocative headline, a meme, the reel has to stand out in the feed → **Retro poster**
   (while it is a mock-up — Mono contrast until it is ready).
6. A strict comparison or an exposé → **Mono contrast**.
7. Tech and AI without numbers → **Night neon**.
8. A product reel — by the "when to use" field of the product preset.

Two reels in a row by the same author in the same style — fine; three in a row — the agent
proposes a change if the meaning allows it: the feed must not look like one picture.

## Where the styles come from

- **Workshop**, **Light breakdown** — created on 16.09.2026 for the owner's blog.
- **Gloss**, **Typography**, **Glass**, **Retro poster** — techniques from 12 of the owner's
  reference reels, broken down in the canon playbook (`docs/canon/playbook.md`).
- The other eight — the product-reel presets from August.

The style code is the value of `style` in the reel's `spec.json`; the engine's presets live in
`src/styles.ts`.
