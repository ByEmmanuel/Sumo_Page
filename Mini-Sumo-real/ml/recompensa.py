"""
recompensa.py -- modelo de recompensa aprendido de las preferencias del usuario.

Entrada: los rasgos de un asalto (sim.RASGOS: resultado, empuje, riesgo de
borde, brusquedad, agresividad...). Salida: un numero, la recompensa humana,
mayor cuanto mas se parece el asalto a lo que el usuario prefiere.

Se entrena con el modelo de Bradley-Terry sobre las comparaciones A/B

    P(A mejor que B) = sigmoide(r(A) - r(B))

y, para las valoraciones sueltas (bueno / malo), contra un umbral aprendido

    P(A bueno) = sigmoide(r(A) - c).

Es un conjunto de cinco redes pequenas, cada una entrenada con un remuestreo
(bootstrap) de los votos. La media es la recompensa; la dispersion entre las
redes mide lo que el modelo no sabe. Esa dispersion decide que comparaciones
se preguntan despues (las de maxima discrepancia) y cuanto pesa la
recompensa humana en el entrenamiento (lambda_sugerida).

Una cabeza lineal, entrenada igual, es la parte legible: sus pesos dicen que
rasgos premia el usuario.
"""

from __future__ import annotations

import datetime as _dt
import json

import torch
import torch.nn as nn
import torch.nn.functional as Fn

from .config import DATA
from .sim import RASGOS

F = len(RASGOS)
FICHERO = DATA / "recompensa.pt"
INFORME = DATA / "recompensa.json"


class Red(nn.Module):
    def __init__(self, h: int = 32):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(F, h), nn.SiLU(), nn.Linear(h, h), nn.SiLU(), nn.Linear(h, 1))

    def forward(self, x):
        return self.net(x).squeeze(-1)


class ModeloRecompensa:
    def __init__(self, media, desv, redes, lineal, centro, escala, n_datos, precision, device="cuda"):
        self.media, self.desv = media.to(device), desv.to(device)
        self.redes = [r.to(device).eval() for r in redes]
        self.lineal = lineal.to(device).eval()
        self.centro, self.escala = float(centro), float(escala)
        self.n_datos, self.precision = n_datos, precision

    @classmethod
    def carga(cls, device: str = "cuda") -> "ModeloRecompensa | None":
        if not FICHERO.exists():
            return None
        d = torch.load(FICHERO, map_location=device)
        redes = []
        for sd in d["redes"]:
            r = Red()
            r.load_state_dict(sd)
            redes.append(r)
        lineal = nn.Linear(F, 1)
        lineal.load_state_dict(d["lineal"])
        return cls(d["media"], d["desv"], redes, lineal, d["centro"], d["escala"],
                   d["n_datos"], d["precision"], device)

    def _x(self, rasgos: torch.Tensor) -> torch.Tensor:
        return (rasgos.reshape(-1, F).to(self.media.device).float() - self.media) / self.desv

    @torch.no_grad()
    def puntua(self, rasgos: torch.Tensor) -> torch.Tensor:
        forma = rasgos.shape[:-1]
        x = self._x(rasgos)
        r = torch.stack([red(x) for red in self.redes]).mean(0)
        return ((r - self.centro) / self.escala).reshape(forma)

    @torch.no_grad()
    def incertidumbre(self, rasgos: torch.Tensor) -> torch.Tensor:
        forma = rasgos.shape[:-1]
        x = self._x(rasgos)
        return (torch.stack([red(x) for red in self.redes]).std(0) / self.escala).reshape(forma)

    def lambda_sugerida(self) -> float:
        """Peso de la recompensa humana: nulo con menos de 6 votos, crece con el
        numero de votos y con lo bien que el modelo predice los que no vio."""
        if self.n_datos < 6:
            return 0.0
        acierto = self.precision if self.precision is not None else 0.6
        return round(0.5 * min(1.0, self.n_datos / 60.0) * max(0.0, (acierto - 0.5) / 0.5), 3)


def _ajusta(red, XA, XB, YP, XS, YS, ref, pasos, l2):
    umbral = nn.Parameter(torch.zeros((), device=ref.device))
    opt = torch.optim.Adam(list(red.parameters()) + [umbral], lr=3e-3, weight_decay=l2)
    for _ in range(pasos):
        perdida = 1e-3 * (red(ref) ** 2).mean()          # mantiene la salida acotada
        if len(YP):
            perdida = perdida + Fn.binary_cross_entropy_with_logits(red(XA) - red(XB), YP)
        if len(YS):
            perdida = perdida + Fn.binary_cross_entropy_with_logits(red(XS) - umbral, YS)
        opt.zero_grad()
        perdida.backward()
        opt.step()
    return red


def entrena(log=print, device: str = "cuda", n_redes: int = 5, pasos: int = 400,
            semilla: int = 0) -> ModeloRecompensa | None:
    from .feedback import datos_entrenamiento, rasgos_referencia

    pares, sueltos = datos_entrenamiento()
    if len(pares) + len(sueltos) < 3:
        log(f"[recompensa] solo {len(pares) + len(sueltos)} votos: hacen falta 3 para empezar.")
        return None
    torch.manual_seed(semilla)
    ref = rasgos_referencia().to(device)
    media, desv = ref.mean(0), ref.std(0).clamp(min=1e-3)
    nz = lambda x: (x.to(device) - media) / desv
    ref_n = nz(ref)

    def tensores(ip, is_):
        XA = nz(torch.stack([pares[i][0] for i in ip])) if ip else torch.zeros(0, F, device=device)
        XB = nz(torch.stack([pares[i][1] for i in ip])) if ip else torch.zeros(0, F, device=device)
        YP = torch.tensor([pares[i][2] for i in ip], device=device, dtype=torch.float32)
        XS = nz(torch.stack([sueltos[i][0] for i in is_])) if is_ else torch.zeros(0, F, device=device)
        YS = torch.tensor([sueltos[i][1] for i in is_], device=device, dtype=torch.float32)
        return XA, XB, YP, XS, YS

    # --- acierto fuera de muestra: validacion cruzada en 5 bloques ------------
    g = torch.Generator().manual_seed(semilla)
    decisivos = [i for i, p in enumerate(pares) if p[2] != 0.5]
    precision = None
    if len(decisivos) >= 8:
        orden = torch.randperm(len(pares), generator=g).tolist()
        aciertos = total = 0
        for k in range(5):
            prueba = set(orden[k::5])
            tr_p = [i for i in range(len(pares)) if i not in prueba]
            red = _ajusta(Red().to(device), *tensores(tr_p, list(range(len(sueltos)))), ref_n, pasos, 1e-3)
            with torch.no_grad():
                for i in prueba:
                    if pares[i][2] == 0.5:
                        continue
                    d = red(nz(pares[i][0])[None]) - red(nz(pares[i][1])[None])
                    aciertos += int((d.item() > 0) == (pares[i][2] > 0.5))
                    total += 1
        precision = aciertos / max(total, 1)

    # --- conjunto con remuestreo ------------------------------------------------
    redes = []
    for k in range(n_redes):
        ip = torch.randint(len(pares), (len(pares),), generator=g).tolist() if pares else []
        is_ = torch.randint(len(sueltos), (len(sueltos),), generator=g).tolist() if sueltos else []
        redes.append(_ajusta(Red().to(device), *tensores(ip, is_), ref_n, pasos, 1e-3))
    lineal = nn.Linear(F, 1).to(device)
    lin = lambda x: lineal(x).squeeze(-1)

    class _L(nn.Module):
        def __init__(self):
            super().__init__()
            self.l = lineal

        def forward(self, x):
            return lin(x)

    _ajusta(_L(), *tensores(list(range(len(pares))), list(range(len(sueltos)))), ref_n, pasos, 1e-2)

    with torch.no_grad():
        r_ref = torch.stack([red(ref_n) for red in redes]).mean(0)
    centro, escala = float(r_ref.mean()), float(r_ref.std().clamp(min=1e-3))
    n_datos = len(pares) + len(sueltos)
    modelo = ModeloRecompensa(media, desv, redes, lineal, centro, escala, n_datos, precision, device)

    # pendiente media de la recompensa respecto a cada rasgo (en desviaciones tipicas)
    x = ref_n.clone().requires_grad_(True)
    torch.stack([red(x) for red in redes]).mean(0).sum().backward()
    pendiente = (x.grad.mean(0) / escala).tolist()

    DATA.mkdir(parents=True, exist_ok=True)
    torch.save({"redes": [r.state_dict() for r in redes], "lineal": lineal.state_dict(),
                "media": media.cpu(), "desv": desv.cpu(), "centro": centro, "escala": escala,
                "n_datos": n_datos, "precision": precision}, FICHERO)
    informe = {
        "fecha": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "pares": len(pares), "valoraciones": len(sueltos), "n_datos": n_datos,
        "precision_validacion_cruzada": precision,
        "lambda_sugerida": modelo.lambda_sugerida(),
        "rasgos": [{"nombre": n, "peso_lineal": float(w), "pendiente": float(s)}
                   for n, w, s in zip(RASGOS, lineal.weight[0].tolist(), pendiente)],
    }
    INFORME.write_text(json.dumps(informe, indent=2, ensure_ascii=False))
    prec = "sin validar (pocos votos decisivos)" if precision is None else f"{precision:.0%}"
    log(f"[recompensa] {n_datos} votos ({len(pares)} pares, {len(sueltos)} valoraciones); "
        f"acierto fuera de muestra {prec}; lambda sugerida {modelo.lambda_sugerida():.2f}")
    top = sorted(informe["rasgos"], key=lambda r: -abs(r["pendiente"]))[:5]
    for r in top:
        log(f"      {'+' if r['pendiente'] > 0 else '-'} {r['nombre']:20s} pendiente {r['pendiente']:+.3f}")
    return modelo
