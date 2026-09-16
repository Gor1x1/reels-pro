/**
 * Снимки кадров из Remotion Studio через системный Chrome — без рендера.
 *
 * Зачем. Рендер Remotion запускает свой компоновщик remotion.exe. На машине
 * с включённым Smart App Control Windows его блокирует как неподписанный,
 * и ни ролик, ни даже один кадр не собираются. Системный Chrome подписан
 * Google и не блокируется, а предпросмотр студии компоновщик не использует.
 * Скрипт открывает студию в Chrome, ставит нужный кадр и снимает холст —
 * этого хватает для проверки раскладки глазами и для картинок стилей.
 *
 *   node pipeline/snap.mjs shots.json
 *
 * shots.json: {"studio": "http://localhost:3210",
 *              "shots": [{"comp": "Reel", "frame": 250, "out": "runs/x/f250.png"}],
 *              "pages": [{"url": "file:///C:/.../page.html", "selector": ".ph", "index": 0,
 *                         "width": 1080, "out": "runs/x/mock.png"}]}
 *
 * Студию нужно запустить заранее: npx remotion studio src/index.ts --port 3210 --no-open
 */
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync, readFileSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { tmpdir } from "node:os";

const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9333;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const cfg = JSON.parse(readFileSync(process.argv[2], "utf-8"));
const profile = resolve(tmpdir(), `snap-chrome-${Date.now()}`);

const chrome = spawn(
  CHROME,
  [
    "--headless=new",
    `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${profile}`,
    "--window-size=1200,2000",
    "--autoplay-policy=no-user-gesture-required",
    "--hide-scrollbars",
    "about:blank",
  ],
  { stdio: "ignore" },
);

let ws;
let nextId = 1;
const pending = new Map();

const send = (method, params = {}) =>
  new Promise((res, rej) => {
    const id = nextId++;
    pending.set(id, { res, rej });
    ws.send(JSON.stringify({ id, method, params }));
  });

const evaluate = async (expression) => {
  const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.text);
  return r.result.value;
};

const shoot = async (clip, out) => {
  const shot = await send("Page.captureScreenshot", { format: "png", clip: { ...clip, scale: 1 } });
  mkdirSync(dirname(resolve(out)), { recursive: true });
  writeFileSync(out, Buffer.from(shot.data, "base64"));
};

async function connect() {
  for (let i = 0; i < 40; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = list.find((t) => t.type === "page");
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(250);
  }
  throw new Error("Chrome не поднял порт отладки");
}

async function main() {
  ws = new WebSocket(await connect());
  await new Promise((r) => ws.addEventListener("open", r, { once: true }));
  ws.addEventListener("message", (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { res, rej } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? rej(new Error(msg.error.message)) : res(msg.result);
    }
  });
  await send("Page.enable");
  await send("Runtime.enable");

  let done = 0;
  // кадры из студии: крупный масштаб экрана, чтобы холст снимался близко к 1080×1920
  if (cfg.shots?.length) {
    await send("Emulation.setDeviceMetricsOverride", { width: 900, height: 1500, deviceScaleFactor: 3, mobile: false });
    let current = "";
    for (const s of cfg.shots) {
      if (s.comp !== current) {
        await send("Page.navigate", { url: `${cfg.studio}/${s.comp}` });
        await sleep(9000);
        current = s.comp;
      }
      await evaluate(`window.remotion_setFrame(${s.frame}, ${JSON.stringify(s.comp)}); true`);
      await sleep(s.wait ?? 3500);
      const rect = await evaluate(
        `(() => { const r = document.querySelector('.remotion-studio-composition-container').getBoundingClientRect();
                  return {x: r.x, y: r.y, width: r.width, height: r.height}; })()`,
      );
      await shoot(rect, s.out);
      done++;
      console.log(`кадр ${s.comp} #${s.frame} -> ${s.out}`);
    }
  }

  // HTML-макеты: элемент страницы снимается в заданной ширине
  for (const p of cfg.pages ?? []) {
    await send("Emulation.setDeviceMetricsOverride", { width: 1100, height: 1400, deviceScaleFactor: 1, mobile: false });
    await send("Page.navigate", { url: p.url });
    await sleep(p.wait ?? 2500);
    const rect = await evaluate(
      `(() => { const r = document.querySelectorAll(${JSON.stringify(p.selector)})[${p.index ?? 0}].getBoundingClientRect();
                return {x: r.x, y: r.y, width: r.width, height: r.height}; })()`,
    );
    const dsf = (p.width ?? 1080) / rect.width;
    await send("Emulation.setDeviceMetricsOverride", { width: 1100, height: 1400, deviceScaleFactor: dsf, mobile: false });
    await sleep(800);
    await shoot(rect, p.out);
    done++;
    console.log(`макет ${p.selector}[${p.index ?? 0}] -> ${p.out}`);
  }

  console.log(`готово: ${done}`);
}

main()
  .catch((e) => {
    console.error("ошибка:", e.message);
    process.exitCode = 1;
  })
  .finally(async () => {
    try { ws?.close(); } catch {}
    chrome.kill();
    await sleep(500);
    try { rmSync(profile, { recursive: true, force: true }); } catch {}
  });
