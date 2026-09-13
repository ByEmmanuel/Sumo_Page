"""
ppo.py -- politica neuronal para Gelatina Nuclear, entrenada con PPO en la GPU.

La maquina de estados son 24 numeros sobre una estructura escrita a mano.
Aqui el algoritmo de movimiento es una red: de los sensores a las dos ruedas,
sin estados. Aprende por refuerzo (PPO, Schulman et al. 2017) jugando miles
de asaltos a la vez en el mismo simulador validado contra el banco en C.

Recompensa de un paso:
    - al acabar el asalto: +1 si gana, -1 si pierde (-1,25 si se sale solo),
      -0,2 si se agota el tiempo (sin progreso deciden los jueces);
    - forma: +2 por metro que el rival se aleja del centro mientras hay
      contacto, -2 por metro que Gelatina se acerca al borde pasado r = 0,30;
    - recompensa humana: al acabar, lambda * r(rasgos del asalto), el mismo
      modelo que guia a la estrategia evolutiva.

El actor (21 -> 64 -> 64 -> 2) cabe de sobra en el STM32F411: ~5.600 pesos y
unas 5.500 multiplicaciones por ciclo de 8 ms. `exporta_c` lo escribe como
C99 puro y comprueba que el C da lo mismo que PyTorch.

La salida pasa por la misma rampa (25/s) y zona muerta que drive(): la red
no puede pedir al puente en H nada que la maquina de estados no pida.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import subprocess
import time

import torch
import torch.nn as nn

from . import config
from .banco import COLOCACIONES_REG, combate, rivales_estandar
from .config import ARM_STEP, DATA, DT_MS, DT_S, NONE, pasos
from .sim import FSM, RASGOS, estado_inicial, fisica, mueve_rival, observa, params_tensor, rasgos

OBS = 21
ANG = torch.tensor([60.0, 30.0, 0.0, -30.0, -60.0]) * math.pi / 180.0
CARPETA = DATA / "politicas"
SLEW = 25.0 * DT_S
DEADBAND = 0.04


class Politica(nn.Module):
    def __init__(self, h_pi: int = 64, h_v: int = 128):
        super().__init__()
        self.pi = nn.Sequential(nn.Linear(OBS, h_pi), nn.Tanh(), nn.Linear(h_pi, h_pi), nn.Tanh(),
                                nn.Linear(h_pi, 2), nn.Tanh())
        self.v = nn.Sequential(nn.Linear(OBS, h_v), nn.Tanh(), nn.Linear(h_v, h_v), nn.Tanh(), nn.Linear(h_v, 1))
        self.log_std = nn.Parameter(torch.full((2,), -0.7))

    def forward(self, obs):
        return self.pi(obs), self.v(obs).squeeze(-1)


# ---------------------------------------------------------------------------
#  observacion: sensores de este ciclo + una memoria minima
# ---------------------------------------------------------------------------

def memoria_inicial(n, dev):
    z = torch.zeros(n, device=dev)
    return {"bearing": z.clone(), "t_visto": torch.full((n,), -10_000, dtype=torch.long, device=dev),
            "t_linea": torch.full((n,), -10_000, dtype=torch.long, device=dev),
            "linea": torch.zeros(n, 4, device=dev), "l": z.clone(), "r": z.clone()}


def observacion(E, M, d, line):
    """Lo mismo que calculara nn_observa() en C: ver exporta_c."""
    t = E["k"] * DT_MS
    valid = (d != NONE) & (d <= 1190)
    dn = torch.where(valid, d.float() / 1200.0, 1.0)
    w = torch.where(valid, 1200.0 - d.float(), 0.0)
    ws = w.sum(1)
    visto = ws > 0
    brg = (w * ANG.to(d.device)).sum(1) / ws.clamp(min=1e-6)
    M = dict(M)
    M["bearing"] = torch.where(visto, brg, M["bearing"])
    M["t_visto"] = torch.where(visto, t, M["t_visto"])
    lf = line.float()
    hay_linea = line.any(1)
    M["t_linea"] = torch.where(hay_linea, t, M["t_linea"])
    M["linea"] = torch.where(hay_linea[:, None], lf, M["linea"])
    armado_ms = torch.clamp((E["k"] - ARM_STEP) * DT_MS, min=0)
    obs = torch.cat([
        dn, lf, M["l"][:, None], M["r"][:, None], visto.float()[:, None],
        (M["bearing"] / (math.pi / 3))[:, None], dn.min(1).values[:, None],
        (torch.clamp(t - M["t_visto"], 0, 1000).float() / 1000.0)[:, None],
        (torch.clamp(t - M["t_linea"], 0, 1000).float() / 1000.0)[:, None],
        M["linea"], (torch.clamp(armado_ms, max=3000).float() / 3000.0)[:, None],
    ], dim=1)
    return obs, M


def aplica(E, M, accion):
    """Rampa y zona muerta de drive(); sin permiso de arranque, quieto."""
    armed = E["k"] >= ARM_STEP
    obj = accion.clamp(-1.0, 1.0)
    l = M["l"] + (obj[:, 0] - M["l"]).clamp(-SLEW, SLEW)
    r = M["r"] + (obj[:, 1] - M["r"]).clamp(-SLEW, SLEW)
    l = torch.where(armed, l, 0.0)
    r = torch.where(armed, r, 0.0)
    M = dict(M, l=l, r=r)
    return M, torch.where(l.abs() < DEADBAND, 0.0, l), torch.where(r.abs() < DEADBAND, 0.0, r)


# ---------------------------------------------------------------------------
#  entorno con reinicio automatico
# ---------------------------------------------------------------------------

class Entorno:
    def __init__(self, n: int, rivales, modo: str = "robusto", max_s: float = 30.0, device="cuda"):
        self.n, self.modo, self.dev = n, modo, torch.device(device)
        self.total = pasos(max_s)
        self.max_s = max_s
        R = len(rivales)
        idx = torch.arange(n) % R                      # cada entorno tiene su rival fijo
        self.rival = torch.tensor([r.tipo for r in rivales])[idx].to(self.dev)
        relleno = config.params_version(config.versiones_registradas()[-1])
        self.Pf = params_tensor([(rivales[i].params or relleno) for i in idx.tolist()], 1, self.dev)
        self.nombres = [r.nombre for r in rivales]
        self.idx_rival = idx.to(self.dev)
        self.E = self._nuevo(torch.ones(n, dtype=torch.bool, device=self.dev), None)
        self.M = memoria_inicial(n, self.dev)

    def _colocaciones(self, n):
        return torch.randint(1, 4, (n,), device=self.dev)       # frente, lado, espaldas

    def _nuevo(self, mask, E):
        nuevo = estado_inicial(self.rival, self._colocaciones(self.n), self.modo)
        nuevo["k"] = torch.zeros(self.n, dtype=torch.long, device=self.dev)
        if E is None:
            return nuevo
        return _mezcla(E, nuevo, mask)

    def reinicia(self, mask):
        self.E = self._nuevo(mask, self.E)
        ini = memoria_inicial(self.n, self.dev)
        self.M = {k: torch.where(mask.view(-1, *([1] * (v.dim() - 1))), ini[k], v) for k, v in self.M.items()}

    def paso(self, accion, rm=None, lam_h=0.0):
        E = self.E
        d_me, l_me, d_fo, l_fo = self._sensores
        self.M, lm, rm_ = aplica(E, self.M, accion)
        r_me0 = torch.sqrt(E["me_x"] ** 2 + E["me_y"] ** 2)
        r_fo0 = torch.sqrt(E["fo_x"] ** 2 + E["fo_y"] ** 2)
        hecho0 = E["done"]
        line_now = l_me.any(1)
        E = dict(E)
        E["f_bordes"] = E["f_bordes"] + ((E["k"] >= ARM_STEP) & ~hecho0 & line_now & ~E["f_linea"]).float()
        E["f_linea"] = line_now
        E, lf, rf = mueve_rival(E, self.Pf, d_fo, l_fo)
        E = fisica(E, lm, rm_, lf, rf)
        r_me = torch.sqrt(E["me_x"] ** 2 + E["me_y"] ** 2)
        r_fo = torch.sqrt(E["fo_x"] ** 2 + E["fo_y"] ** 2)
        contacto = torch.sqrt((E["fo_x"] - E["me_x"]) ** 2 + (E["fo_y"] - E["me_y"]) ** 2) < config.CONTACT_D
        rec = 2.0 * torch.where(contacto, (r_fo - r_fo0).clamp(min=0.0), 0.0)
        rec -= 2.0 * torch.where(r_me > 0.30, (r_me - r_me0).clamp(min=0.0), 0.0)
        acaba = E["done"] & ~hecho0
        tiempo = ~E["done"] & (E["k"] >= self.total)
        fin = acaba | tiempo
        rec += torch.where(acaba, E["res"].float() - 0.25 * (E["razon"] == 3).float(), 0.0)
        rec += torch.where(tiempo, -0.2, 0.0)
        info = None
        if bool(fin.any()):
            E2 = dict(E, done=E["done"] | tiempo)
            ras = rasgos(E2, self.max_s, torch.sqrt(E["me_x"] ** 2 + E["me_y"] ** 2),
                         torch.sqrt(E["fo_x"] ** 2 + E["fo_y"] ** 2))
            if rm is not None and lam_h > 0:
                rec += torch.where(fin, lam_h * rm.puntua(ras), 0.0)
            info = {"fin": fin, "res": torch.where(tiempo, 0, E["res"]), "razon": torch.where(tiempo, 5, E["razon"]),
                    "rival": self.idx_rival}
        self.E = E
        if info is not None:
            self.reinicia(fin)
        return rec, fin, info

    def observa(self):
        self._sensores = observa(self.E)
        obs, self.M = observacion(self.E, self.M, self._sensores[0], self._sensores[1])
        return obs


def _mezcla(a, b, mask):
    if isinstance(a, dict):
        return {k: _mezcla(a[k], b[k], mask) for k in a}
    if a.dim() == 0:
        return a
    return torch.where(mask.view(-1, *([1] * (a.dim() - 1))), b, a)


# ---------------------------------------------------------------------------
#  entrenamiento
# ---------------------------------------------------------------------------

def entrenar(iteraciones: int = 400, entornos: int = 4096, horizonte: int = 128, lr: float = 3e-4,
             gamma: float = 0.998, lam: float = 0.95, lambda_humano: float | None = None,
             semilla: int = 0, nombre: str = "", log=print) -> dict:
    from .recompensa import ModeloRecompensa
    torch.manual_seed(semilla)
    dev = torch.device("cuda")
    rivales = rivales_estandar()
    env = Entorno(entornos, rivales)
    pol = Politica().to(dev)
    opt = torch.optim.Adam(pol.parameters(), lr=lr, eps=1e-5)
    rm = ModeloRecompensa.carga()
    lam_h = lambda_humano if lambda_humano is not None else (rm.lambda_sugerida() if rm else 0.0)
    pid = _dt.datetime.now().strftime("p-%Y%m%d-%H%M%S") + (f"-{nombre}" if nombre else "")
    carpeta = CARPETA / pid
    carpeta.mkdir(parents=True, exist_ok=True)
    cfg = dict(iteraciones=iteraciones, entornos=entornos, horizonte=horizonte, lr=lr, gamma=gamma, lam=lam,
               lambda_humano=lam_h, rivales=[r.nombre for r in rivales], obs=OBS, semilla=semilla)
    (carpeta / "config.json").write_text(json.dumps(cfg, indent=2))
    log(f"[ppo] {pid}: {iteraciones} iteraciones x {entornos} entornos x {horizonte} pasos; lambda_humano={lam_h:.2f}")

    T, N = horizonte, entornos
    B_obs = torch.zeros(T, N, OBS, device=dev)
    B_act = torch.zeros(T, N, 2, device=dev)
    B_logp = torch.zeros(T, N, device=dev)
    B_val = torch.zeros(T, N, device=dev)
    B_rec = torch.zeros(T, N, device=dev)
    B_fin = torch.zeros(T, N, device=dev)
    R = len(rivales)
    t0 = time.time()
    obs = env.observa()
    flog = open(carpeta / "log.jsonl", "w")
    mejor = -1e9
    for it in range(iteraciones):
        cuenta = torch.zeros(R, 3, device=dev)            # gana, empata, pierde por rival
        with torch.no_grad():
            for t in range(T):
                mu, v = pol(obs)
                std = pol.log_std.exp()
                a = mu + std * torch.randn_like(mu)
                logp = (-((a - mu) ** 2) / (2 * std ** 2) - pol.log_std - 0.5 * math.log(2 * math.pi)).sum(1)
                rec, fin, info = env.paso(a, rm, lam_h)
                B_obs[t], B_act[t], B_logp[t], B_val[t], B_rec[t], B_fin[t] = obs, a, logp, v, rec, fin.float()
                if info is not None:
                    f = info["fin"]
                    res = info["res"][f]
                    rv = info["rival"][f]
                    for k, val in enumerate((1, 0, -1)):
                        cuenta[:, k] += torch.bincount(rv[res == val], minlength=R).float()
                obs = env.observa()
            _, v_fin = pol(obs)
            ventaja = torch.zeros(T, N, device=dev)
            ultimo = torch.zeros(N, device=dev)
            for t in reversed(range(T)):
                v_sig = v_fin if t == T - 1 else B_val[t + 1]
                no_fin = 1.0 - B_fin[t]
                delta = B_rec[t] + gamma * v_sig * no_fin - B_val[t]
                ultimo = delta + gamma * lam * no_fin * ultimo
                ventaja[t] = ultimo
            retorno = ventaja + B_val

        o, a_, lp, adv, ret = (B_obs.reshape(-1, OBS), B_act.reshape(-1, 2), B_logp.reshape(-1),
                               ventaja.reshape(-1), retorno.reshape(-1))
        adv = (adv - adv.mean()) / (adv.std() + 1e-8)
        n_tot = o.shape[0]
        for _ in range(4):
            perm = torch.randperm(n_tot, device=dev)
            for mb in perm.split(n_tot // 8):
                mu, v = pol(o[mb])
                std = pol.log_std.exp()
                logp = (-((a_[mb] - mu) ** 2) / (2 * std ** 2) - pol.log_std - 0.5 * math.log(2 * math.pi)).sum(1)
                ratio = (logp - lp[mb]).exp()
                l_pi = -torch.min(ratio * adv[mb], ratio.clamp(0.8, 1.2) * adv[mb]).mean()
                l_v = 0.5 * ((v - ret[mb]) ** 2).mean()
                ent = (pol.log_std + 0.5 * math.log(2 * math.pi * math.e)).sum()
                perdida = l_pi + 0.5 * l_v - 0.001 * ent
                opt.zero_grad()
                perdida.backward()
                nn.utils.clip_grad_norm_(pol.parameters(), 0.5)
                opt.step()

        tot = cuenta.sum(1).clamp(min=1)
        gana = (cuenta[:, 0] / tot).tolist()
        pierde = (cuenta[:, 2] / tot).tolist()
        fila = {"it": it, "t": round(time.time() - t0, 1), "pasos": (it + 1) * T * N,
                "recompensa_media": float(B_rec.sum(0).mean()), "asaltos": int(cuenta.sum()),
                "gana": dict(zip(env.nombres, gana)), "pierde": dict(zip(env.nombres, pierde)),
                "std": pol.log_std.exp().tolist()}
        flog.write(json.dumps(fila) + "\n")
        flog.flush()
        media_g = sum(gana) / R - sum(pierde) / R
        if media_g > mejor and it > iteraciones // 4:
            mejor = media_g
            torch.save(pol.state_dict(), carpeta / "politica.pt")
        if it % 20 == 0 or it == iteraciones - 1:
            log(f"[ppo] it {it:4d}  {fila['pasos'] / 1e6:6.1f} M pasos  gana {sum(gana) / R:.3f}  "
                f"pierde {sum(pierde) / R:.3f}  std {fila['std'][0]:.2f}  {time.time() - t0:5.0f}s")
    flog.close()
    if not (carpeta / "politica.pt").exists():
        torch.save(pol.state_dict(), carpeta / "politica.pt")
    log(f"[ppo] fin en {time.time() - t0:.0f}s ({iteraciones * T * N / 1e6:.0f} M pasos). Politica en {carpeta.relative_to(DATA.parent)}")
    return {"id": pid, "carpeta": str(carpeta)}


# ---------------------------------------------------------------------------
#  evaluacion: mismas reglas que banco.evaluar, politica determinista
# ---------------------------------------------------------------------------

@torch.no_grad()
def evaluar(pid: str, rondas: int = 32, modo: str = "robusto", log=print) -> dict:
    dev = torch.device("cuda")
    pol = Politica().to(dev)
    pol.load_state_dict(torch.load(CARPETA / pid / "politica.pt", map_location=dev))
    rivales = rivales_estandar()
    R, C = len(rivales), 3
    n = R * C * rondas
    tipo = torch.tensor([r.tipo for r in rivales]).repeat_interleave(C * rondas).to(dev)
    col = torch.tensor(COLOCACIONES_REG).repeat_interleave(rondas).repeat(R).to(dev)
    relleno = config.params_version(config.versiones_registradas()[-1])
    Pf = params_tensor([r.params or relleno for r in rivales], C * rondas, dev)
    E = estado_inicial(tipo, col, modo)
    E["k"] = torch.zeros(n, dtype=torch.long, device=dev)
    M = memoria_inicial(n, dev)
    for _ in range(pasos(30.0)):
        sens = observa(E)
        o, M = observacion(E, M, sens[0], sens[1])
        mu, _ = pol(o)
        M, lm, rm_ = aplica(E, M, mu)
        E, lf, rf = mueve_rival(E, Pf, sens[2], sens[3])
        E = fisica(E, lm, rm_, lf, rf)
        if bool(E["done"].all()):
            break
    res = torch.where(E["done"], E["res"], 0).view(R, C, rondas)
    pw, pd, pl = ((res == 1).float().mean(-1), (res == 0).float().mean(-1), (res == -1).float().mean(-1))
    W, D, L = combate(pw, pd, pl)
    out = {"id": pid, "modo": modo, "rondas": rondas, "rivales": []}
    for i, r in enumerate(rivales):
        out["rivales"].append({"nombre": r.nombre, "combate": {"gana": float(W[i]), "jueces": float(D[i]), "pierde": float(L[i])},
                               "colocaciones": {config.COLOCACIONES[c]: {"gana": float(pw[i, j]), "pierde": float(pl[i, j])}
                                                for j, c in enumerate(COLOCACIONES_REG)}})
    out["combate_gana"] = float(W.mean())
    out["combate_pierde"] = float(L.mean())
    (CARPETA / pid / f"evaluacion_{modo}.json").write_text(json.dumps(out, indent=2))
    log(f"[ppo] {pid} ({modo}): combate ganado {out['combate_gana']:.3f}, perdido {out['combate_pierde']:.3f}")
    for f in out["rivales"]:
        log(f"      {f['nombre']:8s} gana {f['combate']['gana']:.3f}  pierde {f['combate']['pierde']:.3f}")
    return out


# ---------------------------------------------------------------------------
#  exportacion a C99
# ---------------------------------------------------------------------------

def _matriz(nombre, t):
    filas = ",\n  ".join("{" + ", ".join(f"{v:.8e}f" for v in fila) + "}" for fila in t.tolist())
    return f"static const float {nombre}[{t.shape[0]}][{t.shape[1]}] = {{\n  {filas}\n}};\n"


def _vector(nombre, t):
    return f"static const float {nombre}[{t.shape[0]}] = {{ " + ", ".join(f"{v:.8e}f" for v in t.tolist()) + " };\n"


def exporta_c(pid: str, log=print) -> dict:
    """Escribe el actor como C99 puro (nn_politica.h) y comprueba contra PyTorch."""
    pol = Politica()
    pol.load_state_dict(torch.load(CARPETA / pid / "politica.pt", map_location="cpu"))
    capas = [m for m in pol.pi if isinstance(m, nn.Linear)]
    h = capas[0].out_features
    txt = [f"/* nn_politica.h -- actor de la politica {pid}, generado por ml/ppo.py. No editar.\n"
           f" * Entrada: {OBS} rasgos (ver ml/ppo.py: observacion). Salida: consignas izquierda y derecha\n"
           f" * en [-1, 1], antes de la rampa y la zona muerta de drive(). */\n",
           "#ifndef NN_POLITICA_H\n#define NN_POLITICA_H\n#include <math.h>\n",
           f"#define NN_OBS {OBS}\n#define NN_H {h}\n"]
    for k, capa in enumerate(capas, start=1):
        txt.append(_matriz(f"NN_W{k}", capa.weight.detach()))
        txt.append(_vector(f"NN_B{k}", capa.bias.detach()))
    txt.append("""
static void nn_capa(const float *x, int n_in, const float *w, const float *b, int n_out, float *y)
{
  for (int i = 0; i < n_out; ++i) {
    float s = b[i];
    for (int j = 0; j < n_in; ++j) s += w[i * n_in + j] * x[j];
    y[i] = tanhf(s);
  }
}

static void nn_politica(const float obs[NN_OBS], float out[2])
{
  float h1[NN_H], h2[NN_H];
  nn_capa(obs, NN_OBS, &NN_W1[0][0], NN_B1, NN_H, h1);
  nn_capa(h1, NN_H, &NN_W2[0][0], NN_B2, NN_H, h2);
  nn_capa(h2, NN_H, &NN_W3[0][0], NN_B3, 2, out);
}
#endif
""")
    destino = CARPETA / pid / "nn_politica.h"
    destino.write_text("".join(txt))

    # prueba: el C y PyTorch dan lo mismo con 256 observaciones al azar
    g = torch.Generator().manual_seed(1)
    X = torch.rand(256, OBS, generator=g) * 2 - 1
    with torch.no_grad():
        Y = pol.pi(X)
    prueba = CARPETA / pid / "prueba_nn.c"
    prueba.write_text('#include <stdio.h>\n#include "nn_politica.h"\n' + _matriz("X", X) +
                      "int main(void){ float o[2]; for (int i = 0; i < 256; ++i) { nn_politica(X[i], o); "
                      'printf("%.7f %.7f\\n", o[0], o[1]); } return 0; }\n')
    binario = CARPETA / pid / "prueba_nn"
    subprocess.run(["gcc", "-std=c99", "-O2", "-Wall", "-o", str(binario), str(prueba), "-lm"], check=True)
    salida = subprocess.run([str(binario)], capture_output=True, text=True, check=True).stdout.split()
    Yc = torch.tensor([float(v) for v in salida]).view(256, 2)
    err = float((Yc - Y).abs().max())
    n_pesos = sum(c.weight.numel() + c.bias.numel() for c in capas)
    log(f"[ppo] {destino.relative_to(DATA.parent)}: {n_pesos} pesos ({n_pesos * 4 / 1024:.1f} KB); "
        f"error maximo C frente a PyTorch {err:.2e}")
    return {"fichero": str(destino), "pesos": n_pesos, "error_max": err}
