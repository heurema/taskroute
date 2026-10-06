import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [browser, rawPort] = process.argv.slice(2);
const port = Number(rawPort);
if (!browser || !Number.isInteger(port) || port < 1024 || port > 65535) throw new Error("Explicit browser and port required");
const server = spawn(process.execPath, ["node_modules/vite/bin/vite.js", "--configLoader", "native", "--host", "127.0.0.1", "--port", String(port), "--strictPort"], { stdio: "pipe" });
let serverLog = "";
server.stdout.on("data", (data) => { serverLog += data; });
server.stderr.on("data", (data) => { serverLog += data; });
const origin = `http://127.0.0.1:${port}`;
try {
  let ready = false;
  for (let attempt = 0; attempt < 100 && server.exitCode === null; attempt++) {
    try {
      const response = await fetch(origin, { signal: AbortSignal.timeout(100) });
      if (response.ok) { ready = true; break; }
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  if (!ready) throw new Error(`Local server unavailable: ${serverLog}`);
  const result = spawnSync(browser, [
    // The enclosing TaskRoute macOS policy supplies the check boundary.
    "--headless=new", "--no-sandbox", "--no-first-run", "--no-default-browser-check",
    "--disable-background-networking", "--disable-extensions", "--disable-sync",
    "--disable-breakpad", "--disable-crash-reporter", "--disable-gpu", "--no-proxy-server",
    `--crash-dumps-dir=${join(tmpdir(), "crashes")}`,
    `--user-data-dir=${mkdtempSync(join(tmpdir(), "browser-profile-"))}`,
    "--virtual-time-budget=3000", "--dump-dom", `${origin}/?acceptance=1`,
  ], {
    encoding: "utf8", timeout: 25000, maxBuffer: 1048576,
  });
  if (result.status !== 0 || !result.stdout.includes('data-browser-acceptance="PASS"')) {
    throw new Error(`Browser check failed: ${result.error || ""}\n${result.stderr}\n${result.stdout}`);
  }
  console.log("BROWSER_ACCEPTANCE_PASS: selection, focus and scroll preserved after refresh");
} finally {
  server.kill("SIGTERM");
  await new Promise((resolve) => { if (server.exitCode !== null) resolve(); else server.once("exit", resolve); });
}
