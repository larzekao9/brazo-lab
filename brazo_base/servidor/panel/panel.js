import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const $ = (id) => document.getElementById(id);
let estado = { conectado: false };
let celda = null;
const vis = {};  // posiciones que se dibujan: p{i}x/y/z (brazo), tx/ty/tz (punta), o:{nombre}x/y/z (objetos)
const reducido = matchMedia("(prefers-reduced-motion: reduce)");
let brazoMallas = null;

// ---------- API ----------
async function api(ruta, cuerpo, metodo) {
  const r = await fetch(ruta, { method: metodo || (cuerpo === undefined ? "GET" : "POST"), headers: { "Content-Type": "application/json" }, body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo) });
  const datos = await r.json().catch(() => ({}));
  if (!r.ok) {
    const detalle = datos.problemas ? "\n- " + datos.problemas.join("\n- ") : "";
    throw new Error((datos.error || (Array.isArray(datos.detail) ? "Dato inválido: " + datos.detail.map((d) => d.loc.join(".") + " " + d.msg).join("; ") : datos.detail) || r.statusText) + detalle);
  }
  return datos;
}
function mensaje(texto, tipo = "error") {
  const p = document.createElement("p");
  p.className = tipo; p.textContent = texto;
  $("mensajes").prepend(p);
  while ($("mensajes").children.length > 6) $("mensajes").lastChild.remove();
  if (!reducido.matches) gsap.from(p, { y: -10, autoAlpha: 0, duration: 0.3, ease: "power2.out", clearProps: "transform,visibility" });
  if (tipo !== "error") setTimeout(() => (reducido.matches ? p.remove() : gsap.to(p, { autoAlpha: 0, height: 0, margin: 0, padding: 0, duration: 0.3, onComplete: () => p.remove() })), 6000);
}
async function accion(ruta, cuerpo, ok, metodo) {
  try { const r = await api(ruta, cuerpo, metodo); if (ok) mensaje(ok, "ok"); return r; } catch (e) { mensaje(e.message); }
}

// ---------- escena 3D (z hacia arriba, milímetros) ----------
const cont = $("lienzo");
const renderer = new THREE.WebGLRenderer({ antialias: true });
cont.appendChild(renderer.domElement);
const escena = new THREE.Scene();
const fondo = () => (escena.background = new THREE.Color(getComputedStyle(document.documentElement).getPropertyValue("--vista").trim() || "#eef1f5"));
fondo(); matchMedia("(prefers-color-scheme: dark)").addEventListener("change", fondo);
const camara = new THREE.PerspectiveCamera(45, 1, 10, 20000);
camara.up.set(0, 0, 1); camara.position.set(900, 400, 800);
const orbita = new OrbitControls(camara, renderer.domElement);
orbita.target.set(0, -400, 100);
escena.add(new THREE.HemisphereLight(0xffffff, 0x445566, 1.4));
const luz = new THREE.DirectionalLight(0xffffff, 1.2); luz.position.set(400, 300, 900); escena.add(luz);
const rejilla = new THREE.GridHelper(2000, 20, 0x8899aa, 0xb0b8c4); rejilla.rotation.x = Math.PI / 2; escena.add(rejilla);
escena.add(new THREE.AxesHelper(150));
const grupoCelda = new THREE.Group(), grupoBrazo = new THREE.Group(); escena.add(grupoCelda, grupoBrazo);
const objetosMalla = {};

function ajustar() { const { clientWidth: w, clientHeight: h } = cont; renderer.setSize(w, h); camara.aspect = w / Math.max(h, 1); camara.updateProjectionMatrix(); }
new ResizeObserver(ajustar).observe(cont); ajustar();
(function animar() { requestAnimationFrame(animar); pintar(); orbita.update(); renderer.render(escena, camara); })();

function vaciar(g) { while (g.children.length) { const c = g.children.pop(); c.geometry?.dispose(); c.material?.dispose?.(); } }

function dibujarCelda() {
  vaciar(grupoCelda); for (const k in objetosMalla) delete objetosMalla[k]; for (const k of Object.keys(vis)) if (k.startsWith("o:")) delete vis[k];
  if (!celda) return;
  const mat = (c) => new THREE.MeshStandardMaterial({ color: c });
  for (const o of celda.objetos) {
    let malla;
    if (o.forma === "caja") malla = new THREE.Mesh(new THREE.BoxGeometry(...o.tamano_mm), mat(o.agarrable ? 0xd9534f : 0x777777));
    else { malla = new THREE.Mesh(new THREE.CylinderGeometry(o.radio_mm, o.radio_mm, o.alto_mm, 24), mat(o.agarrable ? 0x3b82f6 : 0x777777)); malla.rotation.x = Math.PI / 2; }
    malla.userData.alto = o.forma === "caja" ? o.tamano_mm[2] : o.alto_mm;
    objetosMalla[o.nombre] = malla; grupoCelda.add(malla);
  }
  for (const z of celda.zonas_prohibidas || []) if (z.forma === "circulo") zona(z.x, z.y, z.radio);
  for (const o of celda.objetos) if (!o.agarrable) zona(o.posicion[0], o.posicion[1], (o.forma === "caja" ? Math.hypot(o.tamano_mm[0], o.tamano_mm[1]) / 2 : o.radio_mm) + 30);
  const lim = celda.seguridad?.limites_mesa;
  if (lim) { const [x1, y1, x2, y2] = lim; const g = new THREE.BufferGeometry().setFromPoints([[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]].map(([x, y]) => new THREE.Vector3(x, y, 1))); grupoCelda.add(new THREE.Line(g, new THREE.LineBasicMaterial({ color: 0x16a34a }))); }
  for (const s of Object.values(celda.superficies || {})) {
    const e = s.esquinas, pts = [e.a1, e.h1, e.h8, e.a8, e.a1].map(([x, y]) => new THREE.Vector3(x, y, s.z_mm + 1));
    grupoCelda.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0xa16207 })));
  }
}
function zona(x, y, r) {
  const m = new THREE.Mesh(new THREE.CircleGeometry(r, 40), new THREE.MeshBasicMaterial({ color: 0xff0000, transparent: true, opacity: 0.18, side: THREE.DoubleSide }));
  m.position.set(x, y, 1); grupoCelda.add(m);
}
// Movimiento suave: la telemetría llega a 10 Hz y GSAP interpola entre muestras (con prefers-reduced-motion se salta directo).
function suavizar(objetivo) {
  const nuevo = Object.keys(objetivo).some((k) => !(k in vis));
  if (nuevo || reducido.matches) { Object.assign(vis, objetivo); return; }
  gsap.to(vis, { ...objetivo, duration: 0.13, ease: "none", overwrite: "auto" });
}
function dibujarBrazo(puntos, tcp) {
  if (!puntos?.length) return;
  const objetivo = { tx: tcp[0], ty: tcp[1], tz: tcp[2] };
  puntos.forEach((p, i) => { objetivo[`p${i}x`] = p[0]; objetivo[`p${i}y`] = p[1]; objetivo[`p${i}z`] = p[2]; });
  if (!brazoMallas || brazoMallas.n !== puntos.length) {
    vaciar(grupoBrazo);
    const linea = new THREE.Line(new THREE.BufferGeometry().setFromPoints(puntos.map(() => new THREE.Vector3())), new THREE.LineBasicMaterial({ color: 0xf59e0b }));
    const esferas = puntos.map(() => { const m = new THREE.Mesh(new THREE.SphereGeometry(14), new THREE.MeshStandardMaterial({ color: 0x334155 })); grupoBrazo.add(m); return m; });
    const punta = new THREE.Mesh(new THREE.SphereGeometry(10), new THREE.MeshBasicMaterial({ color: 0xff2d55 }));
    linea.frustumCulled = false;
    grupoBrazo.add(linea, punta);
    brazoMallas = { n: puntos.length, linea, esferas, punta };
  }
  suavizar(objetivo);
}
function moverObjetos(posiciones) {
  const objetivo = {};
  for (const [n, p] of Object.entries(posiciones || {})) { const m = objetosMalla[n]; if (m) { objetivo[`o:${n}x`] = p[0]; objetivo[`o:${n}y`] = p[1]; objetivo[`o:${n}z`] = p[2] + m.userData.alto / 2; } }
  suavizar(objetivo);
}
function pintar() {
  if (brazoMallas) {
    const { n, linea, esferas, punta } = brazoMallas, pos = linea.geometry.attributes.position;
    for (let i = 0; i < n; i++) { const x = vis[`p${i}x`], y = vis[`p${i}y`], z = vis[`p${i}z`]; esferas[i].position.set(x, y, z); pos.setXYZ(i, x, y, z); }
    pos.needsUpdate = true; punta.position.set(vis.tx, vis.ty, vis.tz);
  }
  for (const [n, m] of Object.entries(objetosMalla)) if (`o:${n}x` in vis) m.position.set(vis[`o:${n}x`], vis[`o:${n}y`], vis[`o:${n}z`]);
}

// Vistas de cámara con transición
const VISTAS = { "3/4": [900, 400, 800], arriba: [0, -400, 1500], lateral: [1300, -400, 250], frente: [0, 700, 350] };
function irAVista(nombre) {
  const [x, y, z] = VISTAS[nombre];
  if (reducido.matches) { camara.position.set(x, y, z); return; }
  gsap.to(camara.position, { x, y, z, duration: 0.8, ease: "power2.inOut", overwrite: true });
}
document.querySelectorAll("[data-vista]").forEach((b) => (b.onclick = () => irAVista(b.dataset.vista)));

// ---------- telemetría ----------
function conectarWS() {
  const ws = new WebSocket(`ws://${location.host}/telemetria`);
  ws.onmessage = (e) => recibir(JSON.parse(e.data));
  ws.onclose = () => setTimeout(conectarWS, 1000);
}
let teniaConexion = false, ultimoError = 0;
async function recibir(e) {
  estado = e;
  if (e.conectado && !teniaConexion) { celda = await api("/celda").catch(() => null); dibujarCelda(); llenarListas(); }
  if (!e.conectado && teniaConexion) { celda = null; dibujarCelda(); }
  teniaConexion = e.conectado;
  const ins = $("insignia");
  ins.className = "insignia " + (e.conectado && e.habilitado ? "ok" : "");
  const antes = ins.textContent;
  ins.textContent = !e.conectado ? "sin conexión" : `${e.destino} · ${e.habilitado ? "habilitado" : "sin habilitar"} · modo ${e.modo}`;
  if ([9, 11].includes(e.modo)) ins.className = "insignia mal";
  if (ins.textContent !== antes && !reducido.matches) gsap.fromTo(ins, { scale: 1.12 }, { scale: 1, duration: 0.35, ease: "back.out(3)" });
  if (e.conectado && e.pose) {
    dibujarBrazo(e.brazo_puntos, e.pose);
    moverObjetos(e.objetos);
    const [x, y, z] = e.pose;
    $("estado").textContent = `TCP  x ${x.toFixed(1)}  y ${y.toFixed(1)}  z ${z.toFixed(1)}\nÁngulos ${e.angulos.map((a) => a.toFixed(1)).join("  ")}\nTarea: ${e.tarea.nombre ?? "-"} (${e.tarea.estado})${e.tarea.error ? "\n" + e.tarea.error : ""}${e.sostiene ? "\nSostiene: " + e.sostiene : ""}`;
    $("herr-estado").textContent = JSON.stringify(e.herramienta);
  } else $("estado").textContent = e.conectado ? (e.error_lectura || "") : "";
  if (e.tarea?.estado === "error" && e.tarea.id !== ultimoError) { ultimoError = e.tarea.id; mensaje(e.tarea.error); }
  const ocupado = e.tarea?.estado === "en_curso";
  document.querySelectorAll("[data-d],[data-h],#ir,#ir-punto,#llevar").forEach((b) => (b.disabled = !e.habilitado || ocupado));
}

function llenarListas() {
  if (!celda) return;
  $("puntos").innerHTML = Object.keys(celda.puntos).map((n) => `<option>${n}</option>`).join("");
  $("objeto").innerHTML = celda.objetos.filter((o) => o.agarrable).map((o) => `<option>${o.nombre}</option>`).join("");
  const lugares = [...Object.keys(celda.lugares)];
  for (const [n, s] of Object.entries(celda.superficies)) for (let c = 0; c < s.columnas; c++) for (let f = 1; f <= s.filas; f++) lugares.push(`${n}:${String.fromCharCode(97 + c)}${f}`);
  $("lugares").innerHTML = lugares.map((l) => `<option value="${l}">`).join("");
}

// ---------- controles ----------
const num = (id) => ($(id).value === "" ? null : Number($(id).value));
$("destino").onchange = () => ($("fila-real").hidden = $("destino").value !== "real");
$("conectar").onclick = async () => {
  const real = $("destino").value === "real";
  if (real && !$("confirma-real").checked) return mensaje("Marcá la casilla de confirmación para conectar con el brazo real.");
  const r = await accion("/conectar", { destino: $("destino").value, celda: $("celda").value || null, velocidad_simulacion: 1, confirmar_real: real });
  if (r && !real) await accion("/habilitar", {}, "Simulador listo");
};
$("habilitar").onclick = () => accion("/habilitar", {});
$("desconectar").onclick = () => accion("/desconectar", {});
$("parar").onclick = () => accion("/parar", {}, "Parado");
$("limpiar").onclick = () => accion("/limpiar-error", {}, "Error limpiado");
document.querySelectorAll("[data-d]").forEach((b) => (b.onclick = () => {
  const [eje, signo] = b.dataset.d.split(","), paso = Number($("paso").value) * Number(signo), [x, y, z] = estado.pose;
  accion("/mover", { x: x + (eje === "x" ? paso : 0), y: y + (eje === "y" ? paso : 0), z: z + (eje === "z" ? paso : 0) });
}));
$("ir").onclick = () => accion("/mover", { x: num("ir-x"), y: num("ir-y"), z: num("ir-z") });
document.querySelectorAll("[data-h]").forEach((b) => (b.onclick = () => accion("/herramienta", { accion: b.dataset.h, valor: Number($("apertura").value) })));
$("ir-punto").onclick = () => accion("/mover", { punto: $("puntos").value });
$("guardar-punto").onclick = async () => {
  const n = $("nuevo-punto").value.trim();
  if (n && await accion(`/puntos/${n}`, { guardar: false }, `Punto «${n}» guardado en memoria`, "PUT")) { celda = await api("/celda"); llenarListas(); }
};
$("ensayo").onclick = async () => {
  const r = await accion("/ensayo", { tipo: "llevar", desde: $("objeto").value, hasta: $("lugar").value });
  if (r) mensaje(r.ok ? "El recorrido es válido" : "Recorrido prohibido:\n- " + r.problemas.join("\n- "), r.ok ? "ok" : "error");
};
$("llevar").onclick = () => accion("/llevar", { desde: $("objeto").value, hasta: $("lugar").value });
document.querySelectorAll("[data-f]").forEach((b) => (b.onclick = () => accion("/simulador/fallo", { fallo: b.dataset.f, activo: true }, "Fallo provocado: " + b.dataset.f)));
conectarWS();
