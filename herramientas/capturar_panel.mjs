// Saca las capturas de docs/img/ con el panel en marcha (python -m brazo_base.servidor) y Chrome instalado.
//   npm i puppeteer-core && node herramientas/capturar_panel.mjs docs/img http://127.0.0.1:8000/
// Mueve el simulador de verdad (lleva una caja, provoca una alarma): usalo solo con el simulador.
import puppeteer from "puppeteer-core";
const SALIDA = process.argv[2];
const espera = (ms) => new Promise((r) => setTimeout(r, ms));
const nav = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new", args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--no-sandbox"], defaultViewport: { width: 1360, height: 860, deviceScaleFactor: 1 } });
const p = await nav.newPage();
p.on("pageerror", (e) => console.log("ERROR EN LA PÁGINA:", e.message));
await p.goto(process.argv[3] || "http://127.0.0.1:8000/", { waitUntil: "networkidle2" });
await p.waitForFunction(() => window.__panel && window.__panel.robot, { timeout: 60000 });
const post = (ruta, cuerpo) => p.evaluate(async (r, c) => (await fetch(r, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(c) })).status, ruta, cuerpo);
const estado = () => p.evaluate(async () => (await fetch("/estado")).json());
const esperarTarea = async (lim = 90000) => { const t0 = Date.now(); while (Date.now() - t0 < lim) { const e = await estado(); if (e.tarea.estado !== "en_curso") return e; await espera(300); } };
const limpiar = () => p.evaluate(() => { document.getElementById("mensajes").innerHTML = ""; document.querySelector("aside").scrollTop = 0; });
const foto = (nombre) => p.screenshot({ path: `${SALIDA}/${nombre}.png` });

await p.click("#conectar"); await p.waitForFunction(() => document.getElementById("insignia").textContent.includes("habilitado"), { timeout: 30000 });
await post("/mover", { x: 0, y: -480, z: 170 }); await esperarTarea(); await espera(1500);
await limpiar(); await foto("01-panel");

// 2. llevar una caja: foto cuando la pinza ya la sostiene y la sube
await post("/llevar", { desde: "caja_roja", hasta: "bandeja" });
for (let i = 0; i < 400; i++) { const e = await estado(); if (e.sostiene && e.objetos.caja_roja[2] > 60) break; await espera(150); }
await espera(300); await foto("02-llevar-objeto");
await esperarTarea(); await espera(800);

// 3. vista desde arriba con las zonas prohibidas (el trípode)
await limpiar(); await p.click('[data-vista="arriba"]'); await espera(1500); await foto("03-vista-superior");
await p.click('[data-vista="3/4"]'); await espera(1200);

// 4. el recorrido prohibido se rechaza antes de mover
await limpiar(); await p.type("#ir-x", "-450"); await p.type("#ir-y", "-300"); await p.type("#ir-z", "50"); await p.click("#ir"); await espera(900);
await foto("04-recorrido-prohibido");

// 5. practicar un fallo
await p.evaluate(() => document.querySelectorAll("details").forEach((d) => (d.open = true)));
await p.click('[data-f="alarma"]'); await espera(900);
await foto("05-fallo-alarma");
// 6. la celda real del laboratorio (calibración del ajedrez) en el simulador
await post("/desconectar", {}); await espera(800);
await p.evaluate(() => { document.getElementById("celda").value = "celda/celda.json"; });
await p.click("#conectar"); await p.waitForFunction(() => document.getElementById("insignia").textContent.includes("habilitado"), { timeout: 30000 });
await post("/mover", { punto: "a1" }); await esperarTarea(); await espera(1500);
await p.click('[data-vista="3/4"]'); await espera(1300);
await limpiar(); await foto("06-celda-laboratorio");
await nav.close();
console.log("capturas listas");
