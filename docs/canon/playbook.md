---
type: playbook
created: 2026-09-16
updated: 2026-11-09
tags: [playbook, montage, video, reels]
status: working
owner: montage
---

# Playbook: montage

The canon for montage of short vertical videos: how a professional assembly differs
from an amateur one, which numbers are used to check it, and which techniques have
already been dissected on other people's working videos.

**Maintained by:** the `montage` agent (until 09.11.2026 — `montaj`). **Read before:** any assembly of a video, any breakdown of a
reference, any argument about whether something is "beautiful" or not. **The section "Montage thinking" comes
first:** it decides where and why a cut goes, the remaining rules cover how to make it.

Created 16.09.2026 at the owner's request: the montage agent must first
learn the techniques of professionals, and only then cut. The sources of the rules are open
materials on montage and a frame-by-frame breakdown of 12 references sent by the owner.

---

## Montage thinking

Created 17.09.2026 at the owner's request: the agent must not only know
the rules of cutting but also think like a director. Theory and sources —
[[монтажное-мышление]]. Raw material — the owner's explanation
[[src-2026-09-16-montazhnoe-myshlenie-georgi]] and four studies
`src-2026-09-17-montazh-issledovanie-A…D`.

> [!info] Owner's decisions, 17.09.2026 — the answer to the trial of reel 1 v5
> - **v5 is the benchmark:** "we keep this style". Speech, cutting, inserts, background, captions and
>   call to action are the same in v4 and v5; the only difference is montage thinking. Therefore the
>   choice of v5 counts as confirmation of M-32…M-38. The benchmark lives in
>   `reels-pro/runs/2026-09-17/R1-myshlenie/` (`zamysel.json`, `spec-v5.json`),
>   the video is `reels-pro/out/R1-cex-v5.final.mp4`.
> - The owner re-shoots all reels in good quality on a green background (M-12).
> - M-40 accepted. M-41 — we try it. M-42 accepted on condition that the pause is not audible.
>   Tempo 1.15× — without checking (M-23). Background — from stock, but good quality (M-43).
> - Two calls to action at the end of the trial (the spoken "subscribe" and the card "write FERMA") —
>   "fine". In new reels the call to action is built into the script.
> - The owner called the v5 background poor quality: behind the person — a picture or high-quality
>   animation instead of moving video (M-43).
> - The studio's first run (video 10) overheated the computer until the screen flickered:
>   all montage jobs strictly one at a time (M-44, law).
> - **Speech recognition — local whisper through the queue** (the owner's decision
>   17.09.2026 20:40 cancelled the cloud: "the cloud is slow and inconvenient"; with ElevenLabs
>   Scribe v2 the word timing is broken — words stick together). The ban was lifted by the file
>   `reels-pro/lokalnoe-raspoznavanie-razresheno.txt`, `transcribe.py` defaults
>   to `--engine local`; `align.py` and `speechsplit.py` are open.
> - **The background behind the person — only from the owner's library** `Desktop\Contennt
>   Forge LLC\Фоны` (decision 17.09.2026 21:15, catalog
>   `reels-pro/config/fony-vladelca.md`); stock footage is for inserts, not for the background.
> - Around 19:40 the owner turned off Turbo Boost: "Maximum processor state"
>   99% (`powercfg /q SCHEME_CURRENT SUB_PROCESSOR PROCTHROTTLEMAX`,
>   AC index 0x63; 0x64 is 100%). Since then the reference frequency in the queue is about
>   100%, not 117%.

**The owner's logic.**
- A cut "sticks" when the viewer does not notice the join.
- About 70% of the glue is emotion: for the sake of its accent any rule may be broken.
- 15–20% — the attention point: the main object of the next shot stands in the same place on the
  screen, and the eye does not search for the hero. (Cancelled by the owner — see M-34.)
- 10–15% — shot size: it changes by one step; the same on the same does not stick.
- Schools mostly teach the third, but the essence is in the first two.

**What the research added.**
- The owner's shares and Murch's weights are estimates of masters, not measurements. For Murch emotion is
  51, story 23, rhythm 10, eye trace 7, two-dimensional plane 5, three-dimensional space 4.
  What works is not the weight but the order (M-32).
- The second glue after engagement with the content is continuous sound. Without sound
  viewers notice almost all cuts (Smith, 2017).
- Even when all the rules are followed, a viewer who is looking for cuts misses only a quarter
  or a third of them. The goal is that the join does not knock the viewer out of the meaning, not complete
  invisibility.

Tools: `pipeline/akcenty.py` — the emotion map, `pipeline/skleyki.py` —
the shot-size plan and the check of the cuts of a finished video. In the `talk` scene —
`zooms` with a shot-size cut `[second, scale, 0]`, `faces` and `lock` (the `faces` and `lock` parts belong to the cancelled attention point — see M-34).

### M-32 · A cut is checked from top to bottom

- **Status:** working · confirmations: 1 · refutations: 0
- **Rule:** at every cut, six questions in order:
  1. **emotion** — what the viewer should feel right now and whether the cut helps;
  2. **meaning** — whether the cut moves the thought forward;
  3. **rhythm** — the cut falls on the boundary of a thought or at the start of a key phrase, not in the middle
     of a phrase;
  4. **attention point** (M-34) — **CANCELLED by the owner (13.10.2026 and 16.11.2026): the agent skips this question and does not measure the point**;
  5. **shot size** (M-35);
  6. **space** — the pieces are not mirrored, the insert's object stands on the side of
     the author's gaze.

  Violations are allowed only from the bottom up and only for the sake of a named higher item.
  The plan says so explicitly: "jump over a step — accent „բազմապատկում ես“".
  Emotion and meaning are not sacrificed at the same time. Pure emotion without meaning —
  briefly.
- **Source:** the owner's explanation of 16.09.2026. Murch's Rule of Six: order matters more than
  weights, "sacrifice from the bottom". Kuleshov, "Fundamentals of Film Directing" (1941): first
  montage by meaning, then formal features. The owner chose v5 over v4
  of reel 1 (17.09.2026).
- **What would refute it:** over 30+ cuts "sacrifice for the sake of an accent" produces a retention drop
  deeper than smooth cuts, with no gain in watch-through.

### M-33 · Every cut has a named glue

- **Status:** working · confirmations: 2 · refutations: 0
- **Rule:** in the montage plan every cut has its glue recorded, and
  `skleyki.py audit` checks it. The glue comes in four kinds:
  1. **emotion** — an accent of the emotion map (M-37) no further than 0.35 s from the cut;
  2. **shot-size step with the point in place** (M-34, M-35; the "point in place" part is cancelled — the step alone counts);
  3. **window or insert** — the cut is hidden by a transition, the insert's main object stands
     where the gaze was (M-39);
  4. **sound inside a thought** — the same shot size, point ≤0.5° (cancelled), the voice is continuous
     (M-40).

  At any cut the loudness of voice and music does not drop. A cut without glue is
  a defect, even if it "looks fine".
- **Source:**
  - the owner;
  - Smith and Henderson 2008: cuts are missed because of attention to the content;
  - Smith and Martin-Portugues Santacreu 2017: movement after a cut and sound
    hide the join; without sound the effect disappears;
  - reel 1 v4, 17.09.2026: of 15 cuts 12 are hidden by windows, 3 in the full frame
    have the same shot size without emotion. All three sit
    on meaning turns where an accent was called for;
  - reel 1 v5 (trial of the trained director, same material): cuts that
    "do not stick" — 0. Glue: emotion on the main thought (×1.5), two steps
    (×1.60 and back ×1.64), anchor shift 0.3° on all. Lesson of the trial: the echo word
    removed under M-38 had been covering a phrase without a caption, and on the close-up someone else's
    caption was left hanging. When removing the layer at the peak, check that the phrase still
    has its own caption;
  - the owner chose v5 over v4 (17.09.2026): "simply a bomb".
- **What would refute it:** a blind test — viewers notice cuts without a named glue no
  more often than cuts with glue.

### M-34 · The attention point does not jump

> **CANCELLED by the owner (13.10.2026 and 16.11.2026).** The agent does not measure the attention point — it cost minutes and tokens for no gain. Kept for history only.

- **Status:** cancelled by the owner 13.10.2026 (the check of eyes at cuts) and 16.11.2026 (the attention point as a whole): wasted minutes and tokens, the agent does not measure
- **Rule:** the attention anchor on the face is the midpoint between the eyes and the mouth. The anchor shift
  between the last frame before the cut and the first after it was counted in degrees of visual angle at a
  strict phone profile: video width 7.5 cm, 25 cm to the eyes.
  - **≤0.5°** (2.9% of width, 1.6% of height) — the goal: the eye makes no saccades.
  - **≤1°** (5.8% of width, 3.3% of height) — tolerance.
  - **1–2°** — a corrective saccade.
  - **>2°** — the viewer searches for the hero, up to 0.85 s.

  The point could be changed on an emotion or a cue. A cue was one of three:
  the author's head or gesture points there 300 ms before the cut; the new point is no
  further than 2.5° from the screen center; there is movement toward it in the first 200 ms.

  After a shift of more than 1° the shot lasted at least 0.8 s, and the first 400 ms went without
  a new layer and a new cut. The engine: in the `talk` scene — `faces` (the eyes on each
  piece, `skleyki.py measure`) and `lock: true`, the push-in holds the anchor at the same
  point of the screen. (All of this is cancelled: do not run `skleyki.py measure/plan/audit` for the attention point and do not fill in `faces`.)
- **Source:**
  - the owner;
  - Kuleshov 1941: the main object in one place in the last and first frames
    gives a calm cut;
  - Tim Smith's AToCC (2012);
  - Wang 2012: 0.73–0.85 s before the point is captured;
  - Tseng 2009, Mital 2011: after an unexpected cut the gaze is pulled to the center;
  - Võ 2012: with a speaker the gaze holds on the nose;
  - engine check on reel 1, 17.09.2026: a cut with a push-in ×1.29, anchor
    shift 0.16°;
  - the owner chose v5 with `lock` on all cuts (shift 0.3°) over v4
    (17.09.2026).
- **What would refute it:** over 20+ videos retention in the seconds of the cuts does not differ at a
  shift of ≤1° and of 1–2° — then raise the tolerance to 2°.

### M-35 · Shot size — by a step, "slightly tighter" is forbidden

- **Status:** working · confirmations: 1 · refutations: 0
- **Rule:** shot size is measured as the ratio of the distances between the eyes in adjacent
  pieces, r ≥ 1.
  - r < 1.10 — the same shot size (M-40).
  - **1.10–1.40 — gray zone, forbidden:** the change is visible, but there is no new shot,
    the cut reads as a stutter.
  - 1.40–1.85 — a step, the default.
  - 1.85–2.9 — over a step, only on an accent.
  - More than 2.9 — only an emotional peak, no more often than once per 10 s.

  **Push-in ladder from the "waist-up" shot:** waist ×1.0 → chest ×1.6 → shoulders and face
  ×2.4.
  - The owner's scale (second medium → close-up → macro) has no "chest". It is
    an intermediate step, the most frequent one in a talking head.
  - Waist → face — over a step, on an accent.
  - After an accent the shot size returns by one step, not straight back to the waist.
  - No more than a third of the cuts are accent cuts.

  At a cut the shot size changes by a cut, in one frame: `[second, scale, 0]`.
  A smooth push-in `[second, scale]` is a different technique, for building up inside a piece.
- **Source:**
  - the owner;
  - Murch: the worst is a displacement that is "neither small nor full";
  - Thompson and Bowen, "Grammar of the Edit", practices No. 10–11;
  - Frame.io: for an interview, a push-in of 40–50%;
  - Kuleshov → Sokolov: a cut "across a shot", adjacent shot sizes — a jerk;
  - Leake 2017: the idiom "no more than one step";
  - body proportions of Drillis and Contini — for the ladder;
  - the accent budget: with Kuleshov most transitions are gradual, with Murch —
    a minimum of means;
  - the ladder ×1.0 → ×1.6 → ×2.4 in v5 of reel 1 — the owner chose v5 over v4
    (17.09.2026).
  - **Error of `skleyki.py audit`, measurement on video 10 (18.09.2026).** The tool
    measures the ratio by the distance between the eyes on adjacent frames of the finished
    video and systematically underestimates: on 16 cuts in the full frame the intentional
    ratio relative to the one set by the spec came out at 0.93–1.09, on average 0.97 (it measured 1.44 for a spec of
    1.50; 2.28 / 2.23 / 2.29 for 2.40; 0.58 for 0.625). The cause — the turn and
    tilt of the head between the frames before and after the cut change the visible distance
    between the eyes. **Consequence for the plan:** a step calculated right at
    the border (r = 1.45 against a threshold of 1.40) will come out in the report as a "gray zone" in about half the cases.
    Plan with a margin — r ≥ 1.5; if a smooth push-in comes before the cut, bring it no higher than ×1.05 from the base, otherwise it eats
    the step. Before reassembling a video because of the "gray zone", check the cut against the spec
    and look at the frames before and after with your eyes: the report is a reason to look, not
    a verdict. On video 10 that is how it went: the cut at 1.939 s was marked ×1.38 "gray zone",
    the spec has ×1.45 there, and `montaj-kritik-kadr` on frames 1.900 and 1.975 saw
    an honest step (the background leaves from both edges, shoulders and microphone are cropped) —
    there was no need to reassemble because of the report. The margin was raised anyway during
    reassembly for other findings: the push-in before the cut brought to ×1.05,
    the step became 1.52, and in the report it came out as "sticks" (1.45×).
- **What would refute it:** a blind test on a phone (≥5 viewers, ≥30 pairs): "it twitched" is marked
  at r 1.10–1.40 no more often than at r ≥ 1.40, and retention at the second of the
  cut does not drop.

### M-36 · A piece of speech is assembled at the source resolution

- **Status:** working · confirmations: 1 · refutations: 0
- **Rule:** u is the output height divided by the crop height in source pixels.
  - u ≤ 1.2 — allowed.
  - 1.2–1.5 — only if the sharpness in the eye zone is no worse than on the base.
  - More than 1.5 — not allowed.

  Hence:
  - vertical 4K (2160×3840) in a 1080×1920 output gives a clean push-in up to ×2.0 and
    the waist–chest–face ladder (×2.4 at u = 1.2);
  - horizontal 4K gives only ×1.125, no steps — shoot vertically.

  The clean speech cut and the background are assembled at 2160×3840:
  - the mask is computed at 1080p (`matte.py`);
  - `fon_compose.py` stretches it to the frame and rebuilds the edge over the full
    frame;
  - `jumpcut.py --from-edl` reassembles the same clean speech cut at a different resolution
    with frame-exact match.

  If the 1080p clean speech cut went through color correction, the 4K one is fitted to it by pairs of
  frames. Otherwise the wall substrate and the mask will diverge in color.
- **Source:** the research calculation of 17.09.2026; montage practices: safe
  enlargement 110–120%, in interviews the eyes go soft first (Creative COW). Reel 1 v4
  was assembled at 1080×1920, and any push-in above ×1.0 stretched pixels there.
  Reel 1 v5 was assembled in 4K by the 1080p mask. The processed 1080p clean speech cut differed
  from the raw 4K by 39 levels: vignette 0.98 → 0.44 and gamma per channel. After
  fitting by pairs of frames the difference is 3 levels. The background took 58 minutes to assemble
  (3.9 s per frame), the render of the video — 6 minutes. A close-up ×2.4 from 4K is noticeably
  sharper than from 1080p. The owner chose the 4K assembly of v5 over v4 (17.09.2026).
- **What would refute it:** a blind pairwise comparison on a phone: u = 1.5 is told apart from
  u = 1.0 no more than 60% of the time — raise the ceiling.

### M-37 · Emotion is accents on words, and there are few of them

- **Status:** hypothesis: weights and thresholds are starting values · confirmations: 2 · refutations: 0
- **Rule:** the emotion map `akcenty.json` is assembled before the montage plan.
  - **Meaning** is marked up by the meaning department: contrast („ոչ թե… այլ“, „բայց“),
    a number, an address or command, a rhetorical question, an unexpected
    statement, a resolution, the main thought.
  - **Voice** is computed by `akcenty.py` from the source before pauses are cut: pitch peak,
    loudness, elongation, a pause of 250 ms – 1.2 s before the word. "Peak and fall of
    2+ semitones within 300 ms" after a marked peak — that is how an Armenian word
    in focus sounds. A rise to the edge of a word without a fall is a phrase boundary, not an accent.
  - **Face** is computed by `akcenty.py` in the same way: the speed of the smile's build-up, eyebrows,
    wide-open eyes, head movement.

  Strength = 0.4·voice + 0.3·face + 0.3·meaning. A strong moment is two channels from 1.5σ
  or one from 2.5σ; between strong moments at least 5 s, expected 2–5 per
  30 s. Which accents the montage takes is decided by the director by meaning.
- **Source:**
  - research of 17.09.2026: wavelet prominence and 3PRO (Suni; Kakouros and
    Räsänen 2016);
  - Armenian prosody (Chakmakjian 2024);
  - facial expression predicts TikTok views better than text sentiment (2026
    preprint);
  - address and sound events raise attention (Rodero 2019);
  - reel 1, 17.09.2026: the map found three strong moments in 29 s — "5000"
    (smile, eyes), „ստեղից ա սկսվում իրական տարբերությունը“ (eyebrows +4σ),
    „բազմապատկում ես“ (the main thought). The first run without a ceiling on pauses and without
    a weight for the main thought picked pauses between takes and a question instead of the main thought;
  - the owner chose v5, assembled by this map, over v4 (17.09.2026).
- **What would refute it:** the owner marks accents blind on 10 videos, and the engine's top 5
  matches his marking no better than chance. Then rebuild the weights
  from his marking (logistic regression) or drop voice and face.

### M-38 · Accent: push-in before the hit, reaction after, nothing new at the peak

- **Status:** working · confirmations: 1 · refutations: 0
- **Rule:**
  - a shot-size change for an accent is placed on the **start of the phrase** with the key word,
    not on the word itself and not after it;
  - after a punchline or a facial peak the face holds **for 0.8 s or more** with no inserts and
    no new graphics: the viewer reads the reaction;
  - in the window of the strongest moments (top 10% of strength) a push-in in the same scene is allowed,
    but an insert, new graphics and a text block are not. Captions stay. No
    more than one new event per 2 s;
  - the first second of the video is the strongest statement and the first change of picture.
- **Source:**
  - what is said right after an orienting event is remembered better (Potter,
    Lang, Bolls 2008);
  - a close face is read faster (Cutting and Armstrong 2016);
  - a fast tempo on arousing content overloads (Lang 1999, 2007), while
    a shot-size change in the same scene is cheap (Lang 2000);
  - Murch: cut on a line — the viewer will believe the words; linger — they will read the
    subtext from the eyes;
  - the first seconds decide, per YouTube, Instagram and TikTok data;
  - in v5 of reel 1 the push-ins stand on phrase starts with „ստեղից ա սկսվում“ and
    „բազմապատկում ես“ — the owner chose v5 over v4 (17.09.2026).
- **What would refute it:** A/B on 20+ pairs: a push-in after the word is no worse in the slope of
  retention within 3 s after the event, and an overloaded peak is no worse in retention and
  saves.

### M-39 · An insert — by the attention point and by the sign of the phrase

> **CANCELLED by the owner (13.10.2026 and 16.11.2026).** The agent does not measure the attention point — it cost minutes and tokens for no gain. Kept for history only. The "sign of the phrase" part — the insert's emotional sign matches the phrase (Kuleshov effect) — still applies.

- **Status:** cancelled by the owner 13.10.2026 (the check of eyes at cuts) and 16.11.2026 (the attention point as a whole): wasted minutes and tokens, the agent does not measure
- **Rule:**
  - the main object of the first frame of the insert — no further than 2° from the place of the face before
    the insert; on return the face — no further than 2° from the main object of the last
    frame of the insert;
  - the speaker window is placed where the face was in the full frame, if the insert has no
    main object there;
  - pop-up text during speech — no further than 2.5° from the face or where
    the author pointed. Simultaneously with captions — no more than one new
    text layer;
  - an insert shifts the judgment of the face as "pleasant or unpleasant" (Kuleshov effect),
    so its sign must match the sign of the phrase. A specific emotion
    is set by the neighboring shot unreliably — do not count on that.
- **Source:**
  - AToCC (Smith 2012);
  - faces and text attract the gaze 16.6 and 11.1 times (2010);
  - replications of Kuleshov's experiment: Mobbs 2006, Barratt 2016, Cao 2024 — the sign
    shifts, not the category of emotion; Prince and Hensley 1992 — the effect was not
    confirmed.
- **What would refute it:** retention or agreement of gazes does not depend on
  the distance between the face and the insert's main object; viewers rate
  the author the same with an agreeing and a disagreeing insert.

### M-40 · A cut-out join inside a thought is held by sound alone

- **Status:** working (owner's decision 17.09.2026: "yes, you can") · confirmations: 0 · refutations: 0
- **Rule:** cutting end-to-end along the waveform (M-22) produces joins inside a single thought.
  - **Owner, 16.09:** "the same on the same does not stick".
  - **Research:** in the vlog genre such a join is the norm if the voice is continuous,
    and the shot size and point match exactly (r < 1.10, anchor ≤0.5° — the anchor part is cancelled). It is not a change
    of shot but removed air.
  - **How we do it:** the shot size changes by a step at the boundary of a thought (end of a
    sentence or of a meaning beat) and on an accent. Inside a thought the cut-out joins
    go at the same shot size, no more than three in a row, then a step. The glue of such
    a join is sound (M-33, kind 4).
  - At a **thought boundary** a join of the same shot size without emotion and without a window is
    still a defect (M-33).
- **Source:** the owner, 16.09.2026; Murch — change the image at the boundary of a thought
  (a blink); McMullan 2021, PremiumBeat — a vlog jump cut holds on
  continuous sound; shot-size research: no more than three of the same shot size
  in a row. Accepted by the owner 17.09.2026.
- **What would refute it:** in a blind test cut-out joins inside a thought are marked
  "it twitched" as often as joins in the gray zone.

### M-41 · Caption at the chin, one line, one place

- **Status:** hypothesis on trial — the owner allowed it 17.09.2026 ("yes, you can
  try it that way") · confirmations: 0 · refutations: 0
- **Rule:** the caption is one line in one place for the whole video, between the chin
  and the lower interface zone:
  - the center of the line no further than 5° from the mouth (in strict profile — no further than 16% of the frame
    height);
  - above the lower 35% and below the upper 14% of the frame — the Reels zones.

  Two lines take attention more strongly than one, a jumping position tires.

  **How we try it:** on new reels the caption is set as one line at the chin,
  not as two lines in the 0.63–0.77 band (M-08, M-19). If a phrase does not fit on one
  line — two cards in a row, as in M-16, not a second line. At the shot size
  ×2.4 the chin goes down — the line stays in its place, does not jump after
  the face. The result of the trial — by the owner's word.
- **Source:**
  - Kurzhals 2017: captions next to the speaker — more fixations on the face, shorter
    saccades;
  - Li 2026: in vertical video two lines are heavier than one;
  - Meta: Reels safe zones 14/35/6%;
  - currently the caption band is 0.63–0.77 (M-19): ≈9° from the mouth, and the bottom of the band lies
    in the Reels interface zone.
- **What would refute it:** the share of gaze on the face and comprehension do not grow with a caption at
  the chin compared with the lower band.

### M-42 · A pause before the main word

- **Status:** working with the owner's condition (17.09.2026: "yes, but it should not
  be felt") · confirmations: 0 · refutations: 0
- **Rule:** before the key word of one, at most two, of the strongest
  moments of the video a short silence is left. The owner's condition — **the pause is not heard
  as a pause**. The numbers are starting values:
  - length 250 ms, no more than 350 ms;
  - the pause stands where the speech breathes anyway — at a phrase boundary before the key
    word, not inside a word combination;
  - the music in the pause is neither cut off nor raised, but stays at the level of the
    ducking under speech (M-09): both a cut-off and a rise are heard as a glitch;
  - no new layer appears in the pause — only what has already begun continues (a push-in under
    an accent, M-38);
  - the sound critic listens to the ±2 s window: if the pause reads as a hesitation — shorten it to
    200 ms or remove it.

  Everything else — end-to-end per M-22.
- **Source:**
  - words after a quiet pause are recognized better (MacGregor 2010);
  - a filled pause before a plot point improves retelling (Fraundorf and
    Watson 2011);
  - cutting music into silence before key information raises memory
    (Olsen 1995). But the cut-off is audible, and the owner's condition matters more — the music is not
    cut off;
  - the owner's decision of 17.09.2026.
- **What would refute it:** the owner hears the pause on a finished video as a hesitation — on
  two videos in a row the rule is dropped. A/B on 20+ pairs: the variant with the pause
  wins neither in retention after the moment nor in the skip rate.

---

## Active rules

### M-01 · The first three seconds decide watch-through

- **Status:** working · confirmations: 0 · refutations: 0
- **Rule:** the first 3 seconds account for the main share of the spread
  in watch-through. Structure of the opening: 0–3 s — hook, 3–5 s — promise (what the viewer
  will get if they stay), then the body. Splash screens, logos and "hi,
  friends" never appear in this window.
- **Source:** 2026 reviews of retention editing; matches our engine rule
  "the hook is a frame from the material, not a splash screen".
- **What would refute it:** a series of videos with a slow entrance whose watch-through
  is no lower than that of videos with a hook in the first frame.

### M-02 · A significant change of picture every 2–3 seconds

- **Status:** hypothesis (downgraded 17.09.2026) · confirmations: 0 · refutations: 0
- **Rule:** every 2–3 seconds something noticeable must change in the frame:
  shot size, an insert, a caption, graphics, the speaker's position. It need not be
  a cut — see M-03.
- **Source:** 2026 vertical montage practice. Research of 17.09.2026: the figure
  "every 2–3 seconds" has no primary source. Frequent changes correlate with likes and
  reposts (Douyin, 12,842 videos), but the frequency of close-ups and loudness have
  an optimum, and at an emotional peak something new overloads (M-38).
- **What would refute it:** our videos with a steady frame without changes hold
  the same watch-through as those with a rhythm of changes.

### M-03 · Rhythm is made with layers, not with cutting

- **Status:** working · confirmations: 1 (reference measurement) · refutations: 0
- **Rule:** in professional vertical videos there are few hard cuts.
  Rhythm is created by layers appearing and leaving on top of a continuous frame:
  cards, captions, inserts, highlights. Chopping the speaker into pieces is
  the amateur path; it gives choppiness and visible jump cuts.
- **Source:** measurement of the references received (scene threshold 0.30):
  `reel13` — 5 cuts in 48 s (medium shot 8.0 s), `4534534` — 0 cuts
  in 19.8 s, `IMG_3435` — 2 cuts in 16.5 s. Yet visually there
  "something is happening" every 1–2 seconds.
- **What would refute it:** a video assembled with layers loses in watch-through
  to the same material chopped with frequent cuts.

### M-04 · A cut must be motivated

- **Status:** working · confirmations: 0 · refutations: 0
- **Rule:** every cut answers the question "why here". Motives:
  a change of thought, a change of location, an action in the frame (we cut on movement),
  the appearance of a new object of the conversation. A cut "to keep it dynamic" is
  not a motive.
- **Source:** basic principles of montage (motivated cut, cutting on action).
- **What would refute it:** viewers cannot tell a motivated cut
  from an arbitrary one in a blind comparison.

### M-05 · Sound crosses the cut ahead of the picture

- **Status:** working · confirmations: 0 · refutations: 0
- **Rule:** J-cut — the sound of the next scene arrives 0.2–0.5 s earlier than
  the picture, speeds up the tempo. L-cut — the sound of the previous scene stays over
  the new picture, softens the transition. A direct butt join of sound and picture
  at every cut is a sign of amateur assembly.
- **Source:** the classics of dialogue editing.
- **What would refute it:** on our videos J/L-cuts make no difference
  in the feeling of smoothness in a blind comparison.

### M-06 · Attention reset at the 25–35 second mark

- **Status:** hypothesis · confirmations: 0 · refutations: 0
- **Rule:** in a video longer than 30 seconds an "attention break" is placed at the 25–35 second mark:
  a change of setting, a sound accent, sharp graphics.
  Statistically that is where the second wave of viewers leaves.
- **Source:** 2026 retention editing.
- **What would refute it:** our measurements show no watch-through drop in this window.

### M-07 · The caption appears after the voice, not together with it

- **Status:** working · confirmations: 0 · refutations: 0
- **Rule:** the caption appears 0.2–0.4 s after the start of the phrase,
  holds 4–6 words, lives 1.5–2.5 s. A caption that is too early "speaks" the line
  for the author and kills the intrigue.
- **Source:** 2026 vertical montage practice; our validator already counts
  the reading speed and complains about short displays.
- **What would refute it:** videos with a caption level with the voice hold the same
  watch-through.

### M-08 · The caption must be readable on any background

- **Status:** working · confirmations: 1 (breakdown of `reel13`) · refutations: 0
- **Rule:** on a light or busy background the caption sits on a plate.
  The decision is made from the actual frame under the text, not from the style of the video.
  Two lines: the main one white, the key word in an accent color.
- **Source:** `reel13` — a caption on a black plate over macro footage,
  white without a plate on a plain dark background; `IMG_4137`, `4534534` — the same.
  **Decision of 17.09.2026:** the owner allowed a trial of one line at the chin
  (M-41). Two lines remain the fallback until the trial result.
- **What would refute it:** viewers read a caption without a plate
  on a busy background equally well.

### M-09 · Music is 15–20 dB quieter than the voice and ducks under speech

- **Status:** working · confirmations: 0 · refutations: 0
- **Rule:** background music is set 15–20 dB below speech, with automatic
  ducking on every phrase and a rise in the pauses. Additionally — a
  cut in the music in the 1–4 kHz band, where speech intelligibility lives. The music
  should be felt by the viewer, not heard.
- **Source:** the practice of mixing speech and music.
- **What would refute it:** videos with music level with the voice do not lose watch-through.

### M-10 · Audio processing order: noise → equalizer → compressor

- **Status:** working · confirmations: 0 · refutations: 0
- **Rule:** first noise reduction, then frequency correction, then compression,
  and only at the end — loudness mastering. The reverse order lifts the noise
  with the compressor and makes it audible.
- **Source:** the standard dialogue processing order.
- **What would refute it:** swapping the steps is not audible on our recordings.

### M-11 · The master's loudness is set by the platform

- **Status:** working · confirmations: 0 · refutations: 0
- **Rule:** −14 LUFS for YouTube and Instagram, TikTok tolerates louder
  (−10…−9). Our engine already measures in two passes and together with the compressor —
  a single-pass measurement is off by 2–3 LUFS.
- **Source:** platform benchmarks; our own pitfalls in the reels-pro `SKILL.md`.
- **What would refute it:** the platform normalizes everything the same way and there is no difference.

### M-12 · Green background: one and a half to three meters and separate lighting

- **Status:** working · confirmations: 0 · refutations: 0
- **Rule:** the person stands 1.5–3 m from the green cloth, the background is lit
  evenly by its own light sources, the person by their own, and a back light
  on the shoulders and head is mandatory. Then the key is clean and there is no
  green spill. Shooting right up against the cloth cannot be fixed by any processing.

  **Owner's decision 17.09.2026:** all reels are re-shot on a green background
  in good quality. Before mass shooting — a trial take of 10–15 s through
  `matte.py` and `fon_compose.py --despill` (M-20): the matte has not yet been
  tested on real green recordings. The spill is removed in the final assembly by
  `fon_compose.py`: before 17.09.2026 `--despill` existed only in the `matte.py` trial.
- **Source:** chroma-key practice; our `matte.py` already does despill and lightwrap.
  Trial on artificial green 17.09.2026: a piece of reel 1 with a known mask
  was placed onto an unevenly lit cloth with spill on the edge and noise, 90 frames,
  4:2:0 compression. The mask matched at 99.3% (IoU), holes 0.06%, no background inside the mask.
  Green on the edge: in the raw footage 0.044, in the assembly without `--despill` 0.012, with 0.6 —
  0.0009, with 0.9 — 0. Skin shifted by 1.3 levels out of 255 at 0.6. Shadows and
  folds of the cloth were not modeled — only a real take will test them.
  Files — `reels-pro/runs/2026-09-17/zelenyy-test/`.
- **What would refute it:** keying right up against the background gives an edge no worse.

### M-13 · The speaker moves into a window when we show something else

- **Status:** working · confirmations: 1 (reference breakdown) · refutations: 0
- **Rule:** when an insert, diagram, screenshot or card comes into the frame,
  the speaker does not disappear — they shrink into a window (a circle or a rectangle
  with an outline). The connection with the viewer is not broken, and room is freed up.
- **Source:** `IMG_4691` (circle at the bottom, graphics on top), `reel13`, `IMG_4137`,
  `4534534` (rectangle with a glow at the top, cards at the bottom).
- **What would refute it:** fully replacing the frame with an insert holds attention just as well.

### M-14 · A freeze frame at the end is a defect

- **Status:** law · confirmations: 2 · refutations: 0
- **Rule:** the last seconds of the video must be alive. Any static frame
  longer than two seconds gets a slow push-in. The final call to action is placed
  over a working product or an ongoing action.
- **Source:** our own mistakes (`qc.py` catches a frozen frame); confirmed
  on the August assemblies.
- **What would refute it:** videos with a static ending do not lose watch-through.

### M-15 · A caption is editing of the speech, not a transcript

- **Status:** working · confirmations: 0 · refutations: 0
- **Rule:** what goes on screen are the key words of the phrase, not everything said
  verbatim: shorter, bigger, more selling. The restriction is strict — **the meaning
  must not be changed**. The viewer hears the speech and reads the text at the same time;
  they notice any difference in meaning and lose trust.
- **Source:** owner's decision 16.09.2026; confirmed by all the analyzed
  references — they show 2–4 words on screen while 8–10 are spoken.
- **What would refute it:** verbatim captions give the same watch-through
  as shortened ones.

### M-16 · An Armenian caption is built differently from a Russian one

- **Status:** working · confirmations: 1 (native speaker's review 16.09.2026) · refutations: 0
- **Rule:** before going on screen, any Armenian caption passes six
  checks. They are mechanical, no intuition is needed:
  1. **Word order.** After the copula `ա / է / եմ / ես` only the participle
     may stand. If "where, with what, how much" trails after it — that is Russian
     word order, and the piece moves in front of the verb: not `հավաքում է հազար դիտում`,
     but `հազար դիտում ա հավաքում`.
  2. **After a numeral the noun is singular:**
     `100 էջում`, `5000 ռիլս`, `1000 դիտում` — without `-ներ`.
  3. **The question mark `՞` goes inside the word**, on the vowel of the stressed
     syllable: `ՈՐՏԵՂԻ՞Ց`, `ԻՆՉՈ՞Ւ`. A mark at the end of the line on the Russian pattern is
     the fastest way to give away a machine translation.
  4. **The full stop `։` is not used in captions** — it is the mark of a document. There is
     one exception: a card with a price, a condition or a guarantee.
  5. **The exclamation mark `՜` is never used** — caps already shout.
     The shesht `՛` — one per video, on the action verb (`ԳՐԻ՛Ր`).
     The but `՝` is a working mark for a micro-pause before a clarification.
  6. **A word longer than twelve letters cannot be read in two seconds:**
     `ԱՄԵՆ ԲԻԶՆԵՍԻ` instead of `ՅՈՒՐԱՔԱՆՉՅՈՒՐ ԲԻԶՆԵՍ`.
- **Separately on register:** the speech on screen is in colloquial `ա`
  (`ստեղից ա սկսվում`), the captions are in literary `է`. But **a caption must
  match what is heard**, word for word: these are different texts
  only when the caption is not a subtitle but an inscription.
- **A literary caption is literary throughout** (review by `hayeren-usucich`,
  17.09.2026). Along with `ա → է`, the colloquial words change: `ստեղ → այստեղ`,
  `էս → այս`, `էդ → այդ`, `ինչի → ինչու`, `ոնց → ինչպես`. "ՍՏԵՂԻՑ Է" is a half-fix.
  A long word from the speech (`ՏԱՐԲԵՐՈՒԹՅՈՒՆԸ`) is not replaced if there is no
  living short synonym: the phrase is cut into two cards between the predicate
  and the subject, and an adjective is not torn from its noun —
  `ԱՅՍՏԵՂԻՑ Է ՍԿՍՎՈՒՄ` / `ԻՐԱԿԱՆ ՏԱՐԲԵՐՈՒԹՅՈՒՆԸ`.
- **The call to action is an invitation:** `ՈՒԶՈ՞ՒՄ ԵՍ ՀԱՍԿԱՆԱԼ, ԹԵ ՈՆՑ Է ԱՇԽԱՏՈՒՄ` +
  `ԳՐԻ՛Ր՝ ՖԵՐՄԱ` (owner's decision 16.09.2026). The question mark in `ուզում` is
  over the `Ո` of the second syllable: `ՈՒԶՈ՞ՒՄ`. Shorter, if it does not fit: `ՈՒԶՈ՞ՒՄ ԵՍ ԻՄԱՆԱԼ՝ ՈՆՑ`.
- **Vocabulary checked by a native speaker:** a social-network account is `էջ`, not `հաշիվ`
  (`հաշիվ` is a bill-invoice). An approximate number goes with a hyphen:
  `երեսուն-քառասուն`. "Why not" is `ինչու չէ`, not `ինչու ոչ`.
  The genitive of `դիտում` is `դիտման`.
- **Source:** review by the `hayeren-usucich` agent of the owner's first reel,
  16.09.2026. Three of the eight lines contained the same word-order error.
- **What would refute it:** native speakers do not notice a difference between the captions before and after
  these fixes in a blind comparison.

### M-17 · Meaning first, picture second

- **Status:** law · confirmations: 1 · refutations: 0
- **Rule:** montage starts with the meaning breakdown (`smysl.json`): topic,
  message, audience, emotion, beats, and for each beat — which picture is needed and
  which is not allowed. Stock footage, background, graphics and captions are searched for only after it and only
  according to it. Stock search results respond to the words of the query, not to the meaning of the video —
  candidates are chosen by eye from a preview sheet.
- **Source:** owner's remark 16.09.2026 — the stock footage was downloaded before
  the speech transcript was ready. On the first reel Pixabay, for the query "person
  filming video", returned nature and a dog.
- **What would refute it:** videos with stock footage chosen before the breakdown are no worse
  in picture-to-speech match in a blind check.

### M-18 · Fix only what is broken

- **Status:** working · confirmations: 2 · refutations: 0
- **Rule:** before processing, the source is measured (`pipeline/quality.py`) on
  the face, like a colorist does: skin tone against the skin-tone line (about 123°),
  face exposure, noise in the shadows, sound without counting the microphone's digital silence.
  Fix only what went beyond the threshold. The color look of a style is a separate
  step, not a fix, and without sharpening.
- **Source:** measurement 16.09.2026. Owner's reel 1: skin 124.7°, face 0.52,
  sound clean — nothing to fix. "Long 4": shadow noise 2.0 against a threshold of 1.6 —
  only a denoiser is needed. The "strong grade" with sharpening drew a
  light halo along the edge of the white T-shirt.
- **What would refute it:** in a blind comparison the owner chooses videos with full
  processing of all sources more often than videos processed according to measurement.

### M-19 · Frame layout — before layers

- **Status:** working · confirmations: 1 · refutations: 0
- **Rule:** in the 720×1280 layout with `platform: multi` the following is occupied: the face (from the measurement),
  the caption strip 0.63–0.77, the top 9% and bottom 20% — the platform's
  interface zone. A layer does not lie over the face or over captions while they are on screen. A figure on
  light clothing or a wall goes only on a dark backing. The speaker window
  is placed where the insert has nothing important.
- **Source:** first assembly 16.09.2026: the circle overlapped the captions, a white figure
  got lost against the white T-shirt, an echo word ran off the edges of the frame, the call to action covered the
  face. All caught on studio frames before render. **Conflict 17.09.2026:** the strip
  0.63–0.77 is far from the mouth (≈9°) and its bottom reaches into the Reels interface zone (bottom
  35%) — see M-41. On 17.09.2026 the owner allowed a trial of a line near the chin: in
  the trial the 0.63–0.77 strip does not apply.
- **What would refute it:** viewers do not notice overlaps in a blind showing.

### M-20 · The background is changed only if the matte is clean

- **Status:** working · confirmations: 1 · refutations: 0
- **Rule:** before a full background replacement — a trial on 1–2 seconds and a close
  frame around the head. A halo, a "helmet" above the crown, a ragged shoulder edge — we do not
  change the background: an honest wall is better than a sticker. The best path to a perfect replacement is
  shooting on a green background per M-12 or right in front of the farm.
- **Source:** reel 1, 16.09.2026: a beige wall, skin-colored, AI matting
  gave a beige halo on the crown in three variants of settings.
- **What would refute it:** a stronger matting model on the same footage gives
  a clean edge.

### M-21 · Shooting at home on an iPhone 11: camera, frame rate, light

- **Status:** hypothesis (facts checked against sources, not measured on our videos) · confirmations: 0 · refutations: 1
- **Rule:**
  1. **Camera.** Only the main rear camera at 1×.
     - Front: ƒ/2.2, no optical stabilization, fixed focus —
       at 1.2 m the face is soft.
     - Ultra-wide 0.5×: ƒ/2.4, noisy in a room.
     - Digital zoom adds no resolution.
  2. **Frame rate.** In Armenia the mains is 50 Hz, lamps flicker 100 times a second.
     - In the built-in camera: "Record Video" → PAL formats → **4K 25 fps**.
       The shutter speed cannot be set there.
     - "Auto FPS (low light)" — turn off: it drops the frame rate to 24 fps.
     - 60 fps under lamps gives flicker and banding.
     - The iPhone 11 has no 50 fps either in the built-in camera or in Blackmagic Camera.
  3. **Exposure and focus.** Long press until "AE/AF LOCK"
     (exposure/focus lock), the sun slider slightly down.
     - Lock before recording: when a person in a white T-shirt enters the frame,
       the exposure jumps.
     - On reel 1 the empty frames and the talking part differed in brightness
       by a factor of 1.45.
  4. **The first 2–3 seconds are an empty frame** with the same light and locked
     settings. This is the clean wall plate (M-28), standard keying
     practice.
  5. **Light.**
     - A big window at the side-front at 45°; a window behind the back is not allowed.
     - Do not mix daylight with warm lamps.
     - The phone flashlight is a small hard source: glare on the skin and a flat
       face.
     - For shine on the forehead and bald head — blot and use a transparent mattifying powder.
     - Stand 1.5 m or more from the wall: no shadow on the wall.
  6. **Softness.** Wipe the lens with microfiber — that is Apple's first piece of advice.
     - In room light (100 lux) detail drops from roughly 90% to 70%: more light
       is needed.
     - Lock the focus.
  7. **Blackmagic Camera** (free, iOS 17+, iPhone 11 supported).
     - Gives shutter speed 1/50 or 1/100, "Flicker Free Shutter 50 Hz", manual
       white balance with lock, focus lock, bitrate up to Max.
     - **Sharpening and noise reduction cannot be turned off in the iOS version** — the earlier
       advice "the outline on the T-shirt will go away through Blackmagic" was not confirmed.
- **Source:** review of the owner's raw footage 16.09.2026 (angle from below, reading from a sheet,
  outline on the T-shirt already in the source); fact check 16.09.2026 against
  sources:
  - iPhone 11 specification and iOS help (Apple);
  - Blackmagic Camera technical specification and App Store;
  - DXOMARK, reviews of the iPhone 11 main and front cameras;
  - RED, lesson on flicker-free shooting;
  - visityerevan.am — 220–230 V, 50 Hz;
  - Videomaker, Georgetown University, Cambridge in Colour — light and makeup.
- **What would refute it:** the owner's shooting following these points does not give a noticeably
  sharper picture than his previous one (4K 60 fps, built-in camera, no
  lock) in a blind comparison.

### M-22 · Cut by the sound waveform, not by recognition

- **Status:** law · confirmations: 1 · refutations: 0
- **Rule:** a talking head is cut by the loudness envelope (`pipeline/jumpcut.py`):
  a clip starts where the voice rose, ends where it fell silent, margin 10–20 ms,
  pauses longer than 0.12 s are cut out entirely. Between phrases — straight cut, zero air.
  Speech recognition decides neither where to cut nor which speech to throw out (M-27).
  Check the zone at the end by the waveform: the last word is often longer than recognition
  thinks.
- **Source:** owner's remark 16.09.2026 on reel 1. Recognition got the boundaries wrong
  by 0.4–0.9 s: a second of silence remained before the second phrase; in
  total — 8 seconds of pauses on a 35-second video. By waveform — 12 pieces straight cut,
  26.4 s of speech. The owner's method from CapCut: cut by the audio track with a tightening
  on both sides. **Exception (owner's decision 17.09.2026):** one or two
  inaudible pauses before the main word (M-42). A straight cut inside a thought relies
  on a continuous voice (M-40).
- **What would refute it:** videos cut straight are watched through worse than ones with
  natural pauses.

### M-23 · Speed up the talking head by 1.1–1.2×

- **Status:** law (owner's decision 16.09 and 17.09.2026) · confirmations: 0 · refutations: 0
- **Rule:** after cutting, the clean speech cut is sped up by 1.15× preserving the voice
  pitch (`atempo`). Faster than 1.2× Armenian speech starts to sound unnatural.
  All layer and caption timings are recalculated through the cut table (`edl.json`),
  not carried over from the old version.
- **Source:** owner's decision 16.09.2026: "increase the speed so that viewing
  is more efficient". Research 17.09.2026: nobody has tested 1.15×; at 1.25×
  comprehension is the same, satisfaction slightly lower, and straight-cut editing speeds up the pace
  a second time. The proposed A/B of 1.0–1.05× against 1.15× was rejected by the owner
  on 17.09.2026: "no need to test, it's fine as is".
- **What would refute it:** — (law by the owner's decision; revised only by
  his word).

### M-24 · The ending is on the last word, no silent speaking

- **Status:** law · confirmations: 1 · refutations: 0
- **Rule:** if a call to action follows the speech, there can be no frame under it where
  the person speaks without sound — the viewer hears "the voice vanished". The call to action is placed
  on a background without the speaker, on an insert, or on a frame where the author is silent and looks
  into the camera. The text of the call to action is only what the author could say himself:
  an invitation ("Want to understand how it works? Write FERMA"), not a comprehension
  check ("Did you get how it works?").
- **Source:** owner's remarks 16.09.2026 on reel 1: the ending on a frame of the
  speaker with the sound off and an invented question that he never asked.
- **What would refute it:** —.

### M-26 · A glance at the notes is caught by the eyelids, not by the head tilt

- **Status:** working · confirmations: 1 · refutations: 0
- **Rule:** an author reading from a sheet barely tilts the head — only the
  eyes go down. Catch it by a face model with eyelids and pupils: `pipeline/gaze.py`
  on MediaPipe (the "eyes down" score). Speaking to the camera — 0.08–0.20, looking
  at the notes — 0.34–0.54; threshold 0.30, shorter than 0.3 s — a blink. What is found in the speech is
  cut out (`jumpcut.py --drop`) or covered with an insert.
- **Source:** reel 1, 16.09.2026. The five-point YuNet detector missed an obvious
  downward glance at 37.5 and 40.0 s; MediaPipe found 35.9–38.8 s and not a single
  prolonged glance in the remaining speech — which matched the check by eye.
- **What would refute it:** on other videos the detector misses a downward glance
  visible by eye, or flags a glance into the camera.

### M-27 · All the speech that was said goes into the video

- **Status:** law · confirmations: 1 · refutations: 0
- **Rule:** the owner shoots the full text he wants to get across.
  Only silence, a glance at the notes and a proven duplicate take of the same phrase may be cut.
  A piece of speech that recognition could not make out is speech that has to be
  recovered, not garbage. Before assembly — a reconciliation: the total of voice in the recording equals the
  total of voice in the clean speech cut; a discrepancy of more than 0.3 s — stop and ask the owner.
  `jumpcut.py` stops by itself if voice is left outside the zones.
- **Source:** a gross error 16.09.2026 on reel 1: raw footage 1:34, the video got
  speech only up to 1:14. 6.5 s were thrown out — four pieces at 77.3–90.7 s, because
  recognition produced nonsense there. The owner: "that's important".
- **What would refute it:** — (law by the owner's decision).

### M-28 · The wall plate — from empty frames

- **Status:** working · confirmations: 1 · refutations: 0
- **Rule:** the recording starts with 2–3 seconds of an empty frame: the camera is on,
  no person. From these frames the engine takes a clean wall plate
  (clean plate) and cuts the edge by the difference from it. If there are no empty frames,
  the plate is built from the talking part — by a robust polynomial of the smooth
  wall. Only samples that resemble the wall in both brightness and hue go into it.
  A plain per-pixel median over the pixels the network called wall does not catch defects.
- **Source:** reel 1, 16.09.2026. The network in a third of the frames took the white
  T-shirt for wall, the median drew the T-shirt on the plate, and the key
  punched holes in the chest. The recording contained 35 empty frames (the beginning and end
  of the take). Their difference from the wall in the talking part is 0.016, the deviation
  of the wall from a smooth surface is 0.009.
- **What would refute it:** a video where a plate from empty frames gives a worse edge
  than a plate built from the talking part.

### M-29 · Clean edge: key by the wall, protection of the middle, 1 px trim

- **Status:** working · confirmations: 1 · refutations: 0
- **Rule:** the edge on a skin-colored wall is assembled in order
  (`matte.py` v2 + `matte_core.py`):
  1. where the person is far from the wall in color (hair, clothes), alpha
     is computed by the mixing formula I = a·F + (1−a)·B; where close
     (skin), the neural network decides;
  2. the confident middle of the figure is not cut by the key — otherwise the background
     shows through the face;
  3. a pixel next to the figure that is clearly not the wall's color is the person: this is how
     holes on the white T-shirt are closed. "Next to" is counted from the silhouette with
     closed holes: everything not connected to the top, left or right edge of the
     frame is inside the person. A small closed hole (up to ~120×120 px)
     is closed entirely, except for pixels that exactly match the wall.
     Otherwise the middle of a wide hole drops out of the check, and the new background's lamp
     shines through the chest: these are the "flickering highlights";
  4. mask jitter is damped by optical flow, with no trail on the hands;
  5. edge color — "blur fusion" with radius 31. Dividing by alpha
     draws a green-blue rim; radius 91 takes color from the bright forehead and gives
     a light edge on dark hair;
  6. the mask is trimmed inward by 1 px: the network and smoothing make it wider than
     the person, and on a dark background the extra pixel is a light line of the old wall.

  Check — a close frame of the head and the bottom on an even dark background, not on
  a busy one: on a busy one a hole looks like a highlight. Holes are searched for by measurement over all
  mask frames (closed gaps not the wall's color), not by eye on two or three
  frames: in the trials there were none, and in the full video they appeared from the 14th second.
- **Source:** reel 1. v3 (16.09.2026): a ragged greenish outline,
  flicker at the bottom edge from row-by-row hole filling. v4 (evening of the same day):
  outline clean. The first v4 assembly passed the auto-check, but on frames 21.8 and 27.0 s
  a spot glowed on the chest. Mask measurement showed holes larger than 200 px in 446 frames
  out of 880, the biggest — 17,957 px. After closing the closed holes there are none. The first version's flags `--unmix`, `--fill-holes`
  were removed.
- **What would refute it:** the owner, on a phone screen, sees an edge or holes
  on a video assembled by this procedure.

### M-30 · Background without jerks: length, frame rate, grain

- **Status:** working · confirmations: 1 · refutations: 0
- **Rule:**
  - A background video is not looped end to end. The background is taken longer than the video;
    a short one is slowed down or goes back to the start through a dissolve
    1 s long.
  - Frame rate 25 → 30 fps is converted by frame blending, not by
    frame skipping.
  - Over the whole frame — identical grain, std. dev. 0.012: a clean blurred background
    behind noisy phone footage reads as a sticker.
  - Light vignette 0.25 and background light on the edge 0.25.
  - A cold blue background behind a warm face gives away the matte.
- **Source:** v3 measurement, 16.09.2026. The background frame jump at the loop cut —
  8.21 against a median of 0.65, 12 times stronger than usual, this is the very
  "flicker". A horizontal 1080p clip had been stretched to vertical
  by a factor of 1.8. In v4 the 13.9 s office is slowed down 2.2 times (30.5 s) — no loop.
- **What would refute it:** viewers cannot tell a looped background from one without a loop
  in a blind showing.

### M-31 · The key is computed once, the background is changed as many times as needed

- **Status:** working · confirmations: 1 · refutations: 0
- **Rule:** the matting goes in two steps.
  1. `matte.py` computes the mask once (neural network, ≈1.1 s per frame,
     20 minutes for a 30-second video) and writes it losslessly:
     `--alpha-out *.mkv`.
  2. `fon_compose.py --video` rebuilds the edge from the saved mask and
     substitutes the background in minutes. A background trial frame (`--still`) takes 2 s.

  Changing the background or editing the edge does not restart the neural network.
- **Source:** reel 1 v4, 16.09.2026: the edge trim was found after a full
  run and applied without re-matting.
- **What would refute it:** an assembly from the saved mask gives a worse edge than
  a full run with the same background.

### M-43 · Background — from the owner's library, and only good quality

- **Status:** working (owner decisions 16.09, 17.09.2026, 17.09.2026 21:15 and
  18.09.2026 — asked again directly after a complaint about the background build time,
  confirmed) · confirmations: 2 · refutations: 0
- **Rule:** the background behind the person is taken from the owner's library
  `Desktop\Contennt Forge LLC\Фоны` via the catalog `reels-pro/config/fony-vladelca.md`
  (decision of 17.09.2026 21:15: the background comes only from his folder; this is how R10
  was built — background No. 8). Stock sites (Pexels, Pixabay — `pipeline/stock.py`) remain for inserts
  matching the meaning of the speech (M-17), not for the background. "Good quality" is checked with numbers:
  - **A picture instead of moving video** (owner's decision of 17.09.2026): behind
    the person goes a good-quality photo or a suitable good-quality animation. A photo —
    at original size, not a preview. A `.gif` is almost always 256 colors with banding:
    an animation is taken as a seamless video loop that passes the thresholds below.
  - **Stretch at the video's largest shot-size step:** u = 1920 × shot size /
    height of the background piece in frame. With a ladder up to ×2.4 (M-35):
    - vertical 4K (piece 3840) — u = 1.2, can be sharp;
    - horizontal 4K (piece 2160) — u = 2.1, only under depth-of-field
      blur (`--bg-blur`);
    - horizontal 1080p (piece 1080) — u = 4.3, not allowed.

    The thresholds are starting values: u ≤ 1.2 — sharp background, 1.2–2.2 — blurred only, above —
    no.
  - No watermarks, logos, text or recognizable faces in focus.
  - No compression blocks — look at a large frame, not a preview.
  - Length, frame rate, grain and tone matched to the face — per M-30.
- **Source:**
  - owner decisions: Pexels and Pixabay stocks (16.09.2026); "download the background
    from open sources, it just has to be good quality" (17.09.2026);
  - reel 1 v5: the office behind the speaker — Pexels 1920×1080. At ×1.0 it is stretched 1.8 times,
    in the close-up at ×2.4 — 4.3 times;
  - the cause — `stock.py` took from Pexels a file no wider than 2160 px, i.e. a
    horizontal clip of no more than 1080p. Fixed 17.09.2026: selection up to 4K on the
    long side, the search "modern office" immediately gave 3840×2160 and 4096×2160;
  - the owner called the v5 background low quality (first confirmation) and allowed
    pictures: "behind you can put pictures, not video that moves,
    or a suitable gif, but of good quality" (17.09.2026).
- **What would refute it:** the owner, on a phone, blind, cannot tell a background with u = 2.1 without
  blur from a background with u = 1.2 — raise the threshold for a sharp background.

### M-44 · Montage runs in a queue: one job at a time

- **Status:** law (owner's order of 17.09.2026) · confirmations: 0 · refutations: 0
- **Rule:** while montage is running, exactly one heavy task runs at any moment.
  The next one starts only when the previous one has finished. Since the evening of
  17.09.2026 the law is held by a mechanism, not by the agent's memory.
  - **The queue** — `python pipeline/ochered.py -- <command>`. A named Windows mutex
    lets one job through; if busy for more than 9 minutes — exit code 75, repeat the same
    command later. The job and everything it launches live in a Windows job object:
    **18 of 24 threads while the temperature sensor is alive** (the 9 upper
    physical cores), 12 — without the sensor or if it went silent mid-run; core zero
    stays for the farm and the screen, priority below normal,
    `OMP/MKL/OPENBLAS_NUM_THREADS` by thread count (owner, 18.09.2026:
    "yes, do it" about 18 threads; "the computer doesn't heat up at all, you can give it more
    work" at 39–52 °C). **A light job as a second slot** —
    `ochered.py --lyogkaya` (ffprobe, frames, qc, stocks, `remotion still`):
    4 threads on cores 1–2, enabled by the file `vtoraya-rabota-razreshena.txt`,
    freezes from 80 °C. A heavy job freezes from 85 °C, resumes below 95 °C. If the queue dies, Windows kills
    the whole job tree; whatever the job left behind is cleaned up at the end.
  - **Overheating.** Every 10 seconds the queue measures the frequency of the cores busy with the job.
    Below 70% of its reference three measurements in a row — the job freezes for 2 minutes
    to cool down; the fourth time it is killed with code 76, and this is reported
    to the owner. The threshold is a starting value: throttling on this machine has not yet been measured.
  - **Watchdog and hook.** Heavy scripts `pipeline/*.py` and `build.ps1`, launched
    around the queue, get into it by themselves. The Claude hook (`PreToolUse`,
    `~/.claude/tools/ochered-hook.py`) rejects ffmpeg with `-i`, a Remotion render,
    recognition and python code with heavy libraries in the montage job, and
    answers with a ready command through the queue. The farm's OCR on cv2 is not touched.
  - **Departments** — one at a time, in the foreground: their work is heavy. **The critics
    after the build — all four in parallel** (speed-up of 18.09.2026 on the owner's words
    "speed up the process more boldly"): the critics read files and frames, and everything
    heavy they launch the queue lets through one at a time anyway — the law
    is held by the mechanism, not by the number of agents. What would refute it: parallel critics
    heat the processor above 80 °C or wait in the queue longer than they would take one by one.
  - **Long jobs** (more than 10 minutes) — in the tool's background, and while one runs, nothing
    heavy is launched: it is waited for.
  - **Log** — `%LOCALAPPDATA%\reels-pro-ochered\zhurnal.jsonl`: minutes, code,
    average and peak processor load, core frequency, pauses. The manual ceilings
    of the previous edition (`-threads 12`, a load check after a minute) are replaced
    by the mechanism.
- **Source:**
  - the studio's first full run, video 10 (4K HEVC 60 fps, 88 Mbit/s, 208 s),
    17.09.2026: ffmpeg on the source and whisper large-v3 recognition ran at the same time —
    both on the processor, 100% of all 24 threads of the Xeon E5-2690 v3. The GT 740
    does not decode HEVC and cannot run neural networks; by the time it was stopped ffmpeg had accumulated
    11,112 processor seconds;
  - the computer got very hot, the screen flickered. The owner stopped the montage and turned
    the PC off. The Windows log shows no video-driver resets, hardware errors
    or emergency shutdowns;
  - simultaneity was permitted by the line of the `montaj` agent "departments 4 and 5 may be
    launched in parallel" and the run brief ("in batches of 3–5"). Both removed;
  - the owner's order: "all jobs ran in a queue when montage is working, this is
    important so that this does not happen again";
  - on the evening of 17.09.2026 the owner ordered the law built into code: "make sure
    the agents in no way make mistakes about this". Verified with harmless
    commands: a process in the queue sees 12 of 24 threads and below-normal priority,
    a second job waits and gets code 75, a queue crash kills the job
    tree, the hook catches 30 of 30 bypasses and lets through 30 of 30 light
    commands.
  - **Queue measurements, second run of video 10 (17.09.2026, evening), 12 of 24
    threads.** There was no flicker and no cool-down pauses.

    | Time | Job | Min | Code | Load avg / peak | Frequency reference / min | Pauses | Turbo |
    |---|---|---|---|---|---|---|---|
    | 19:28 | whisper large-v3, whole file 208 s | 4.47 | 0 | 52.5% / 68.0% | 116.9% / 116.0% | 0 | on |
    | 19:35 | whisper on 20 phrases | 18.93 | 0 | 59.8% / 69.1% | 117.5% / 100.0% | 0 | off from ~19:40 |
    | 19:58 | text hypothesis check | 7.39 | 0 | 57.6% / 74.4% | 100.0% / 99.9% | 0 | off |
    | 20:07 | hypothesis check, second pass | 2.99 | 0 | 53.6% / 61.7% | 100.0% / 99.9% | 0 | off |
    | 20:17 | emotion map `akcenty.py`, 208 s | 1.79 | 0 | 25.8% / 59.5% | 99.9% / 99.4% | 0 | off |

    Do not use the 19:35 job to calibrate the threshold: the reference was taken with turbo, the minimum
    already without it. The jobs from 19:35 to 20:10 ran on local whisper already after the owner's
    ban (the department learned of it at 20:11) — since then the ban is held by code.
- **What would refute it:** a run through the queue again brings the machine to screen
  flicker — then half the cores is too many or the cause is in cooling, the power supply
  or the video card: the share of cores is lowered, the hardware is checked. Only the owner can cancel the queue,
  for example after a new video card and a temperature measurement under load.

### M-45 · The 40-second ceiling is a guideline, not a gate

- **Status:** law (owner's direct word 18.09.2026) · confirmations: 1 · refutations: 0
- **Rule:** the length of a video is set by the speech, not by a check threshold. `qc.py` measures
  a 15–40 s range and marks leaving it as FAIL — this is a guideline for the short
  format, not a delivery gate. **A video whose duration is the only
  failed `qc.py` item counts as a finished master and is delivered as is.**
  For the sake of timing it is forbidden to:
  - cut the speech and "pull something out of the text" (M-27 forbids this too);
  - reassemble a finished video only because of its length;
  - push the tempo to the upper edge of M-23 (1.2×) and trim the M-42 pause to fit
    into the range: both levers are legitimate by themselves, but not as a way to fit a number.

  The owner's word: "15-40 seconds is not a hard rule. If my video came out
  42 seconds or a minute — you must do it that way, don't invent and don't
  make anything up, don't cut again, don't pull something out of the text to
  bring it to 40 seconds". In the report the duration is stated as a number, not presented
  as a defect.
  **18.09.2026, as a follow-up:** the `qc.py` code is fixed too (not just the studio knew —
  now the code knows it too): the 40 s ceiling is marked `advisory` (field `совет`) —
  the check is printed and goes into the JSON, but is not counted toward FAIL and does not
  fail the return code. The 15 s minimum stayed a hard gate (it catches a real
  build breakage — a file cut down to seconds). The reason for the fix is not only
  cleanliness but factual: while the threshold was a gate, a video with a single
  failed item "duration" looked like FAIL both in the log and in the return code —
  on 17-18.09 this became one of the reasons why the studio's death at the session limit
  at this very spot went unnoticed for 10 hours (nobody could tell
  from the logs that the job was finished, not hung).
- **Source:** video 10 (R10, light-talk), 18.09.2026. Build v1 passed 8 checks
  out of 9 (1080×1920, 30 fps, −14.0 LUFS, pauses 0.0 s, no black or frozen frames,
  light background under the captions on 6% of frames), one FAIL — 42.7 s against the 15–40 range.
  The arithmetic of the gap, calculated from `edl.json`: the sum of 21 speech pieces 49.01 s,
  at tempo 1.15× — 42.62 s; the M-23 limit (1.2×) would give 40.84 s, removing the M-42
  pause (252 ms) — another 0.21 s, total 40.63 s. The video did not fit into 40 s under any
  legitimate combination: the missing 0.63 s would have had to be taken from the speech. The cost
  of the attempt — about 1.5 hours of queue (4K clean speech cut 11 min, matting 29, background
  build 53, render 10) and recalculating the timings of the spec, captions, inserts and eyes for the sake of
  a result that is a FAIL anyway. The owner dropped the question entirely.
- **What would refute it:** the owner, on a live 45–60 s video, says it drags
  and does not hold attention, or retention measurements show a failure exactly after the 40th second —
  then the range returns as a gate, and length is built into the script before
  shooting, not cut in montage.

### M-46 · The speaker window lives only over an insert

- **Status:** working · confirmations: 1 · refutations: 0
- **Rule:** a window (the author in a frame over another picture) is created **only
  when there is something to show under it** — a shot or found insert. No
  insert — no window: the author stays in full frame, and the meaning is carried by the shot-size step
  at the boundary of a thought and by layers on top of him.
  - The edit plan writes the window for a specific insert. If the inserts department returned "there is no such
    shot", the director must **remove the window**, not leave it open
    onto emptiness. An empty light slide with a little window is a presentation placeholder, not
    montage: the viewer loses the face, the anchor drifts away (M-39), the lower half of the frame
    sits empty.
  - A one-line check: every piece with a window in the spec must have a `src`.
    An `insert` layer without `src` is a red flag, not "a place for an insert".
  - Layers and lists intended to go inside the window move to the author: the space
    under the chin and below is free if the caption is off at that moment (M-15).
- **Source:** video 10, 18.09.2026. Beat 6 ("thousands of publications across dozens
  of pages") got a 0.32 window at the top edge at 20.809–23.443, but no insert was found for
  the first piece — the stocks have no same person at three
  moments of the day, and the department did not fake a match. The window stayed open
  onto an empty slide. Three sources independently named this spot the main risk
  of losing the viewer: the director from the frame sheet, `montaj-kritik-uderzhanie`
  ("the video promised a payoff, and instead it takes away the face") and `montaj-kritik-kadr`
  (the grid inside the slide rendered as an empty skeleton, saturation 22–24 out of 255).
  Measurements before and after removing the window: face anchor 3.3° → 0.3° with a tolerance of 2°; cut
  20.809 from "into the window" became an honest 0.58× step; "doesn't glue" across the whole video
  1 → 0; the qc check "background under captions is light" 6% of frames → 0% (together with the
  slide went the only section where the white caption risked disappearing).
- **What would refute it:** a video where a window over a neutral background holds attention
  better than a full frame — for example when a long breakdown of graphics runs in the window
  and the author is needed as a small commentator. Then the rule narrows to "a window without
  an insert lives no longer than 1 second".

### M-47 · The matte edge tears on the first frame after a cut

- **Status:** working · confirmations: 1 · refutations: 0
- **Rule:** matting tracks the person over time and loses its
  history at a cut: the first frame of the new piece gets a raw edge — a colored fringe along
  the hair for one frame. **After the background is built, the frames at piece boundaries
  are checked separately**, by eye on the sheet or by counting.
  - A cheap measurement: count the pixels of the fringe color (for a blue halo —
    `B − R > 70` and `B > 130`) in the central band of the frame above the graphics. On a clean
    video the median is 0, a bad frame stands out by thousands.
  - Fixed **without rebuilding**: the bad frame is replaced by its neighbor right in the finished
    master — `ffmpeg split + trim=start_frame=1 + overlay=enable='eq(n,N)'`,
    video re-encoded, audio copied. Two identical pictures of 33 ms at the start of the shot
    are not noticeable, length and loudness do not change.
  - One found frame is not enough: the finding is checked across **all** piece boundaries,
    otherwise one gets fixed and five stay in the video.
- **Source:** video 10, 18.09.2026. `montaj-kritik-kadr` found one frame
  (32.167 s) and called it "barely noticeable". A check of the whole video by numbers
  gave six frames — 330, 577, 965, 1129, 1176, 1268, and all six sit exactly
  on speech piece boundaries (6 of 20 cuts, 30%). The worst — 1129 (37.633 s)
  on the call to action "Գրի կոմենտներում": 22,570 blue pixels against a median of 0 for the video,
  that is a fringe over half the head. The patch took 1.04 minutes of queue against
  ≈1.5 hours of the honest path (matting 29 min + background build 53 + render 11 +
  a new round of critics); after it the halo count is 0 of 1279, length, frame count
  and loudness −14.0 LUFS did not change.
- **What would refute it:** a video shot as one piece with no cuts also shows
  halos in the middle of shots — then the problem is not the break in matting history,
  but the mask itself or the key parameters, and matting must be fixed, not frames.
  Or: matting with a warm-up (several frames before each cut) does not remove
  the fringe — then the cause is deeper.

### M-48 · The critic looks once — no second round

- **Status:** law (owner's direct word 18.09.2026) · confirmations: 0 · refutations: 0
- **Rule:** a video goes to the critics **once** per run. Build finished →
  all four critics at once (M-44) → if there are remarks — the department fixes once →
  delivery. A second pass of the critics after the fix is not launched: whatever stayed
  disputed after the single fix is a line to the owner in the report, not a new
  round. The last check before delivery is the director's eyes on the summary frame sheet
  and the cut sheet (the rule existed before), not a repeat call to a critic.
  - A critic who cannot check (no frame, file not ready) is not
    "accepted", but also not a reason to reopen a round: what is missing is asked
    of the department within that same single fix.
  - The rule replaces the former "ceiling — two rounds" from the text of the `montaj` agent
    (that was the agent's text, not the canon): in practice even a ceiling of two or three rounds
    stretched into a 6-7 hour conversation between the director and the critics. Video 10
    actually went through three rounds of critics (three studios, three chats), although the
    processor count for the whole video is 195 minutes (see the "time breakdown" entry of 18.09
    in `log.md`).
- **Source:** the video 10 time breakdown (18.09.2026, `Wiki/log.md`) and the owner's direct words:
  "The critic's round should go through only once... the video must be
  edited, finished and handed to the critic. The critic checks once,
  sends it for correction if there is something to correct. And the video gets corrected."
- **What would refute it:** the department's fix after a critic's remarks regularly introduces
  a new defect of the same kind the critic already checked (not a new defect from the fix
  itself — that is a separate case) — then a short repeat look
  at exactly the changed spot is needed, but not a full second round over the whole video.

---

### M-49 · Edit plan self-check verifies layers too, not only overlays

- **Status:** working · confirmations: 0 · refutations: 0
- **Rule:** `validate.py:check()` now checks every `scenes[].layers`
  on a par with `overlays` — an empty duration or one extending past the scene (the same
  logic as for overlays), and separately for `kind == "insert"`: an ERROR if there
  is no `src` or the file at `src` is not found in `public/`. Before, there was no loop over `layers`
  at all, and the M-46 bug (an author window with no insert on video 10) slipped
  past the validator and was found only by the frame critic after a full render.
- **Source:** the plan of 18.09.2026 (`Wiki/log.md`, "plan for the three open
  items"), code `pipeline/validate.py`. Verified with two synthetic
  copies of video 10's `spec.json` (an insert layer without `src`; an insert layer with `src`
  pointing to a nonexistent file) — both are caught with an ERROR giving the exact layer number.
  Along the way the real `spec.json` of video 10 revealed an overlap not noticed before:
  the FARM card (a card layer) runs to 42.95 s with the scene at 42.633 s —
  not fixed (video 10 is closed and delivered), but it confirms that the `at+dur`
  check works and finds real cases, not only invented ones.
- **What would refute it:** validate.py lets through an insert layer without `src` or
  with a nonexistent file on a new video, or falsely rejects a layer
  with a correct `src` — then check the exactness of `public/` path matching.

### M-50 · Local transcription prints uncertain words

- **Status:** working · confirmations: 0 · refutations: 0
- **Rule:** `transcribe_local()` (`pipeline/transcribe.py`) puts
  `"p"` — the word probability 0–1 from `faster-whisper` (`w.probability`) —
  into each word dictionary and immediately prints "uncertain words: N" if
  anyone has `p` below 0.5 (`P_NEUVERENNO`), exactly as the cloud
  branch already did by `logprob` (`NEUVERENNO`, M-…). The `"p"` field does not end up
  in the finished `captions.json` — `to_blocks()` still builds a block
  only from `t/s/e`, as before; it is a signal at the moment of transcription,
  not part of the captions.
- **Source:** the plan of 18.09.2026 (`Wiki/log.md`). Verified by replacing
  `model.transcribe()` with fake words of known probability — `p`
  is computed correctly, the printout triggers exactly at the threshold. Separate
  files `frazy.py`/`proverka*.py` were deemed unnecessary by the same plan —
  they were not in the repository and will not be; the text fix on video 10 was made
  by comparison with the cloud text, not by them.
- **What would refute it:** the `faster-whisper` probability regularly diverges
  from what sounds wrong by ear (many false alarms or misses) —
  then move the 0.5 threshold, rather than remove the printout itself.

### M-51 · The studio watchdog outside the chat

- **Status:** working in logic, **schedule suspended 18.09.2026 — see
  M-54** (each task run is a whole Claude session at ≈0.65 GB of memory);
  deliberately without auto-resurrection (plan, item "c")
  · confirmations: 0 · refutations: 1 (18.09.2026, false alarm — correction made, see below)
- **Rule:** `pipeline/storozh.py` scans `runs/*/*/` for folders
  with `rezhisser-hod.json` but without `doklad-studii.md` (an unclosed run), takes
  the freshest of them and by the mtime of `rezhisser-hod.json` counts the minutes
  of silence. The threshold is 20 minutes when the heavy queue is free
  (`ochered._svobodno(TYAZHELAYA)`), 45 when it is busy, 180 in any case
  regardless of the queue. It prints ALIVE / NONE / DEAD as the first word
  (ЖИВА / НЕТ / УМЕРЛА in the code). A `mcp__scheduled-tasks` task (id `montaj-storozh`, every 20 minutes,
  stored on disk, survives closing the studio chat — not `CronCreate`,
  which dies together with the chat) runs it and on DEAD sends a single
  `PushNotification`; it fixes and restarts nothing itself — only
  detection and notification, the decision to restart belongs to the owner.
- **Source:** the plan of 18.09.2026 (the owner considered this item the most valuable).
  The logic was verified on the real folder `R10-zelenyy` (closed → "NONE")
  and on synthetic copies in `runs/` (fresh → ALIVE; 200 minutes of silence →
  DEAD; the appearance of `doklad-studii.md` immediately removes the folder from view) —
  all three states and the correct return code are confirmed, the test
  folders were deleted after the check. A manual run of the task itself
  (`run_scheduled_task`) was launched but stopped at a one-time permission
  for the PowerShell tool inside the task — one click from the owner is needed
  (the "Run now" button in the "Schedule" panel or open the session and allow
  manually), after that the task runs by itself without questions.
- **What would refute it:** after the first real trigger the notification
  either does not arrive on a real studio death, or arrives falsely
  for a studio that is still alive, just slow — then recalculate the 20/45/180 thresholds
  from facts, not from the numbers inherited from the watchdogs of previous chats.
- **Refutation No. 1 (18.09.2026, correction made in `storozh.py`):** the first
  real run gave a false "DEAD: R11 silent for 27 min" with a living studio.
  The watchdog measured silence only by `rezhisser-hod.json`, and that is updated when
  a step ends; "meaning" (a department subagent is working, the director waits for it) ran
  28 minutes — run files were written until 21:13, the department's log until 21:15.
  The sign of life is now the freshest of the progress log, any file in the run folder and
  the subagent logs (`--zhivoy`; for the watchdog inside the chat — the `subagents` folder
  of its own session). Four cases were verified synthetically: death, a file deep in
  the folder, a subagent log, a closed run; on a live studio — "ALIVE". Residual
  risk: a very long train of thought by a department without a single write (a known case —
  captions, 64 thousand output tokens in a row) will still raise the alarm; the 20/45/180 thresholds
  were not changed. The studio's progress file must be updated inside a long step too —
  a line "in progress: what the department is doing" every 10 minutes is cheaper than a false alarm.

### M-52 · The person matte is computed in pieces (matte.py --workers)

- **Status:** working on a short segment, the full video was not measured ·
  confirmations: 2 · refutations: 0
- **Rule:** `matte.py` cuts the video into pieces by common frame numbering and
  computes them in processes simultaneously; by default the number of pieces is decided by the cores of the queue
  and the free memory commit (`--workers 1` — as before). Everything shared
  is decided by the parent once before distribution: framing from the edge
  scouting and the wall backing. Each piece before starting warms up what the previous
  frame remembers — the neural network, the backing and the jitter suppression — on 30 frames that are not
  written. The thread counts of the neural network, cv2 and ffmpeg in a piece are limited (otherwise the pieces
  fight for cores). The join — `concat -c copy` separately for each output; the audio
  is laid in once.
- **Source:** video 10 (1080p), 120 frames: one process 1.26 s/frame, two
  pieces 0.92 s/frame, the mask matched a single-process pass to 0.003/255
  (`Wiki/log.md`, 18.09.2026, "matte.py is cut into pieces"). A piece's memory
  is about 3.3 GB with three outputs — auto mode with little free commit
  will honestly choose one piece. **Second measurement, 18.09.2026 (twelfth chat):**
  one piece (frames 40–59) at 2, 4 and 9 threads — commit 2.09 / 2.24 / 1.75 GB
  (threads do not change memory; with two outputs ≈2.1 GB, ≈1.0 GB per megapixel),
  time per frame 1.46 / 1.22 / 1.14 s — depends weakly on threads, **pieces pay off more
  than threads**. A piece's mask equals a single-process pass at any thread count: mean
  difference 0.00001, maximum 0.00002; a control shifted by one frame gives 0.0092 —
  a one-frame shift is clearly visible to this measure. `GB_NA_MP` raised from 0.60 to 1.1
  (×1.5 with `--fg-out`), auto mode prints "memory limits the number of pieces".
- **What would refute it:** on a full video with 4 pieces the time does not drop at least
  by half versus one process (meaning the pieces fight for memory or cores —
  look at threads and `GB_NA_MP`), or a piece's mask diverges from a single-process
  pass by more than 0.1/255 at the boundary (meaning a 30-frame warm-up is not enough —
  raise `RAZGON`, do not remove the pieces).

### M-53 · A piece lands on the right frame with -ss only without frame-rate alignment

- **Status:** working · confirmations: 2 (matte.py, fon_compose.py) ·
  refutations: 0; the fix was also made in `fon_compose.py` on 18.09.2026
- **Rule:** any piece reader that lands by a fractional `-ss` (for example,
  half a frame earlier than needed so as not to lose a frame to rounding) reads with
  `reader(..., passthrough=True)` — `-fps_mode passthrough`. Otherwise ffmpeg
  by default (CFR) sees the first frame half a frame after the start, gives it out
  twice, and the whole piece shifts by a frame: a duplicate at the piece junction and the person layer
  33 ms behind the sound.
- **Source:** `reader` on video 10: `t0+(G-0.5)/FPS` gives out frames
  `[G, G, G+1...]`, while `t0+G/FPS-0.001` gives `[G, G+1, G+2...]`; the mask pieces
  diverged from a single pass only with a shift of −1, after `passthrough`
  the difference is 0.003/255. **`fon_compose.py` (readers `rf` and `ra`), verified on
  files 18.09.2026:** 1080p, 4 s of video 10, grain off, one process versus
  two pieces. Before the fix the frames of the second piece diverge from a single process by up to
  0.040 (48 of 120 frames above 0.01), best match with a +1 shift —
  the piece lagged by a frame; the number of closed holes 735,012 versus 473,295. After
  the fix (`passthrough=True` in `rf`, `-fps_mode passthrough` in the `ra` call):
  mean difference 0.00259 exactly on all 120 frames (this is codec noise), maximum
  0.00298, frames above 0.01 — zero; holes 473,292. Video 10 (the accepted master)
  was built before the fix. I looked at its 4K background at the junctions 320, 640, 960: the difference of adjacent
  frames at the junction 319→320 is 0.0041 against a median of 0.0082 (a dip — looks like a duplicate
  frame), at 639→640 and 959→960 there is no dip. The shift of the person layer against the sound in
  video 10 was not measured; the video was not redone.
- **What would refute it:** the frames of a piece with `passthrough` do not match a pass
  by a single process on another source (variable frame rate, ragged
  timestamps) — then look up the frame by timestamp, not by count.

### M-54 · A scheduled task is a live Claude session: the watchdog does not spin idle

- **Status:** working · confirmations: 1 (18.09.2026) · refutations: 0
- **Rule:** every run of a `mcp__scheduled-tasks` task is a whole Claude session:
  a live process at ≈0.65 GB of Windows memory commit, a full context (system
  prompt, memory, plugins) and, at least on the first runs, a PowerShell permission
  request. The session does not close itself — it is archived only with the owner's
  consent. Therefore the watchdog `montaj-storozh` (M-51) **is enabled only while a studio
  run is going and with a step no more often than 60 minutes**; between runs `enabled: false`.
  While the studio runs from a live chat, a watchdog inside the chat is preferable (a background
  `storozh.py` loop without its own session), not a task. The reason is serious: memory is
  the limiter of piecewise matting (M-52) and of the 4K background build (`fon_compose.py`), and
  a 20-minute watchdog idling took pieces away from them.
- **Source:** 18.09.2026, thirteenth MONTAGE chat. Free commit was 3.3 GB
  with ≥11 needed; 37 live Claude sessions held 24 GB (≈0.65 GB each), of them
  7 were watchdog runs at 14:26–16:20 UTC (≈4.5 GB, ≈2 GB per hour); the seventh
  run hung for 15 minutes on a PowerShell permission request, while `storozh.py` at that
  time answered "NONE active run". The owner allowed archiving the watchdog and
  19 finished montage chats (26 sessions): processes 37 → 17, free
  commit 3.3 → 11.7 GB.
- **What would refute it:** archiving or closing of sessions launched by a task
  happens by itself (then a 20-minute watchdog is acceptable), or a way appears
  to run the check without a full session (a Windows task with a script and
  notification) — then return the watchdog to a permanent basis.

---

### M-55 · One entry point for montage — the `montage` agent, mode by material

Introduced 09.11.2026 by the owner's decision. Montage is run by one agent `montage`
(`~/.claude/agents/монтаж.md`); the old studio with the `montaj` director, the `montage-lead`
orchestrator, the `raw-editor`/`cut-planner`/`speech-splitter`/`frame-fixer` wrappers
and the four critics are in the archive `~/.claude/agents-arhiv/montaj-2026-11-09/`.

- **Rule.** The mode is chosen by the input, not by habit: A ready clips of an AI character →
  the Vera template (≤15 min); B screen + face + lavalier → the lesson script `d01.py` (≤30 min);
  C the owner's talking head → the M-32…M-42 canon (≤2 h, `montaj-*` departments only when needed,
  no critics); D a long stream → shorts; E a broken-down film → inventory, sync, order,
  conform, assembly, a project for CapCut/Resolve; F reworking a finished video;
  G the editor's program (CapCut is installed; Premiere and Resolve are not installed; Higgsfield — only with a "yes" and a price).
- **Why.** Vera V1 by departments — 2 h 05 min without render, V3 by template — 8 min; Mara 14.10 —
  two `montaj` at once, 7 minutes without render. The process, not the model, ate the time.
- **Tools added 09.11.2026:** the plugins `ffmpeg-skill` (42 ffmpeg operations,
  ducking, multicam by loudness, loudness) and `hyperframes` (HTML → MP4, ≈450 motion-graphics
  blocks), the library `pyJianYingDraft` (CapCut drafts). Not installed:
  `ghost-editor` (Mac only), `claude-shorts`/`long-to-shorts` (WSL only) — their ideas
  went into M-27 and mode D.
- **What would refute it.** Three videos in a row in the fast mode taking longer than 15 minutes with a working
  template, or a canon video where the absence of a critic let through a defect which the owner
  would call a failure — then the critic returns for one step, not the whole studio.
- **What is not yet measured.** The acceptance test of criterion 6 from `ԲԱՑ-ԱՌԱՋԱԴՐԱՆՔ-montaj-ագենտի-ուղղում.md`
  (1 reel in ≤15 min by the new agent) has not yet been carried out.

## Bank of techniques from references

Analyzed 16.09.2026 from 12 videos sent by the owner. The files are in
`C:\Users\User\Downloads`. We take the techniques, we do not copy the picture.

### Technique T-01 · Round speaker window

`IMG_4691`. The upper two thirds — graphics and cards on a light background, at the bottom
a round window with the face, a gradient outline-indicator of duration runs around the circle.
The caption comes one or two words at a time between the graphics and the circle.
Suitable for an explainer about tools and automation.

### Technique T-02 · Glowing window and cards

`reel13`, `IMG_4137`, `4534534`. The speaker in a rounded rectangle
with a thin glowing outline at the top of the frame, below — photo cards tilted
and with a shadow, lists with thumbnails sliding in from the left. The background behind the person is replaced
with a clean gradient.

### Technique T-03 · Two-layer caption with an accent

`reel13`, `IMG_4137`, `IMG_3435`, `IMG_3516`. Two lines: the upper one white,
the lower in an accent color (orange in the references). The accent falls
on the meaningful word of the phrase, not on the last one.

### Technique T-04 · Kinetic typography

`IMG_3435`. A word repeats as an echo and recedes into depth ("choke · choke ·
choke"), the figure "×3" in a circle with arrows. Amplifies emotion without inserts.

### Technique T-05 · Lists sliding in one by one

`reel13`, `IMG_4137`. Items appear in sequence, each a plate
with a thumbnail on the left and text on the right, the active item is highlighted.
This is how enumerations are shown without losing the speaker.

### Technique T-06 · Glass and volume

`montazh-0712-3d`. Three-dimensional lettering with a metallic gradient, glass
plates, a neon grid in the background, 3D icons. It looks more expensive, but requires
assets and easily slides into a template.

### Technique T-07 · Typographic video without a face

`JpKlDZVyjS`. Cream background, large black type, yellow marker highlights,
row cards, large figures, a small monospaced running head, a progress bar
at the top. A format for news, breakdowns and lessons where the face is not needed.

### Technique T-08 · Retro poster

`IMG_3613`. Engraving-style illustrations, torn paper, plates of pure color,
lightning bolts and stars. Assembled from generated pictures and typography.

### Technique T-09 · Story morphing

`IMG_2130`. A construction site turns into a finished house in one camera move —
"was → became" transitions inside a continuous frame. This is generation, not
montage, but as a technique for showing the result of work it is stronger than any cut.

### Technique T-10 · Multi-style of one script

`IMG_3784`. The same piece shown in four visual themes at once.
Useful as a way to choose the style before the build, not after.

### Market observation

`IMG_4314`, `IMG_4137`, `IMG_3784`, `4534534` — these are ads of competitors
who sell automatic montage by an AI agent for 18 ₽ per video and collect
leads by a code word. The format "video BEFORE on the left, result on the right" is
their main selling technique.

---

## Deferred and refuted

### M-25 · Background replacement on a skin-colored wall: key at the head and room light

- **Status:** refuted 16.09.2026 · confirmations: 1 · refutations: 1
- **Why withdrawn:** on the full video v3 this recipe gave a ragged greenish contour (the hard difference key cuts the edge in steps, subtracting the wall by dividing by alpha leaves a green-blue rim) and flicker at the lower edge (hole filling by rows switched on and off on adjacent frames). Replaced by the rules M-28…M-31.
- **Rule:** if the background must be changed and the wall is close to skin in color:
  1. take the person's color from the source frame, not from the network's prediction —
     the network recolors a short dark haircut into a gray "cap";
  2. around the head (`--head` from `quality.py`) — a difference key against the known
     color of the old wall: clearly not wall — opaque, almost wall — transparent;
     do not let the key onto the torso — there it cuts holes at moving hands;
  3. slightly trim and soften the edge (`--shrink 0.1 --edge-soft 1.2`);
  4. room light: below the face the person is darker (`--relight 0.4`), otherwise a flatly
     lit figure on a dark background looks pasted in;
  5. mask dropouts on the body (`--fill-holes 0.08`): on a white T-shirt when the
     hand moves the network makes the torso semi-transparent. Below the chin everything is filled that is
     inside the figure's contour in the row or inside the "average figure" across the whole video,
     except pixels of the old wall color. Check the mask on a pure green background —
     on an office background a dropout looks like a highlight.
  Test on 1–2 seconds and the full frame, not only on a close-up of the head.
- **Source:** reel 1, 16.09.2026: six test runs of settings. The owner demanded
  background replacement despite the halo (rule M-20 was cancelled by his decision for this
  case); the halo and cap went away on the seventh test, the torso holes — after filling by the average figure (236 frames).
- **What would refute it:** the owner or viewers notice the matte on a phone screen.
