# ml/ — aprendizaje por refuerzo con retroalimentación humana en GPU

El algoritmo de movimiento de Gelatina Nuclear se entrena en la RTX 5070 y
mejora con tus votos. Hay dos familias de algoritmo:

- **La máquina de estados** de `algorithms/strategy.c`, con sus 24 números de
  `params.h`. La optimiza una estrategia evolutiva (CMA-ES). Es lo que va al
  robot: un candidato ganador se exporta a `params.h` y se registra en la
  bitácora como una versión más.
- **Una política neuronal** (21 entradas → 64 → 64 → 2 ruedas), entrenada con
  PPO. Es un experimento: se exporta a C99 y cabe en el STM32F411, pero todavía
  no ha pasado por Webots.

Las dos comparten el simulador, el banco de rivales y el modelo de recompensa.

## El ciclo

```
   simular en GPU ──► candidatos ──► comparaciones A/B ──► tus votos
         ▲                                                    │
         └──── aptitud = simulada + λ · recompensa humana ◄───┘
                               (modelo de recompensa)
```

1. **Entrenar.** CMA-ES juega cada generación entera (cientos de candidatos
   × decenas de asaltos) en una sola pasada de la GPU, contra static,
   charger, spinner, las versiones de la bitácora y los campeones de la liga,
   en las tres colocaciones del reglamento.
2. **Votar.** Para el campeón y la versión de la que partió se graba el
   **mismo** asalto (mismo rival, misma colocación, mismo sorteo). Tú ves las
   dos repeticiones a la vez, sin saber cuál es cuál, y eliges.
3. **Recompensa.** Cinco redes aprenden de tus votos qué rasgos de un asalto
   prefieres (empuje, riesgo de borde, brusquedad, agresividad…). Bradley-Terry
   para los pares; un umbral aprendido para "los dos mal".
4. **Liga y dirección.** Todos contra todos da un Elo. Una red sustituta,
   entrenada con todas las variantes probadas, dice hacia qué parámetros se
   inclinan las mejores versiones: su gradiente en el campeón.

El peso de tu opinión (λ) empieza en 0 y crece con el número de votos y con
lo bien que el modelo predice los que no vio: sin votos no hay recompensa
humana, y con 60 votos bien predichos pesa del todo (λ = 0,5).

## Uso

Desde `Mini-Sumo/`. Vale cualquier `python`: `python -m ml` se relanza solo
con `ml/.venv`, que es donde están PyTorch y numpy.

```bash
ml/.venv/bin/python -m ml servidor          # interfaz de votos: http://localhost:8765
ml/.venv/bin/python -m ml ciclo             # recompensa -> entrenar -> pares -> liga
```

Por piezas:

```bash
ml/.venv/bin/python -m ml validar           # simulador de GPU contra tests/harness.c
ml/.venv/bin/python -m ml entrenar          # CMA-ES (60 gen x 384 candidatos por defecto)
ml/.venv/bin/python -m ml evaluar c-002     # un algoritmo contra el banco, por colocación
ml/.venv/bin/python -m ml pares c-002 v0.3.1
ml/.venv/bin/python -m ml votar p-0001 a --etiqueta "empuja bien"
ml/.venv/bin/python -m ml recompensa        # reentrena el modelo con los votos
ml/.venv/bin/python -m ml liga              # Elo y dirección de mejora
ml/.venv/bin/python -m ml banco-c c-002     # el candidato en el banco nativo en C
ml/.venv/bin/python -m ml exportar c-002    # a algorithms/params.h + versions/_draft.json
ml/.venv/bin/python -m ml ppo               # política neuronal
ml/.venv/bin/python -m ml ppo-evaluar p-...
ml/.venv/bin/python -m ml ppo-exportar p-...
```

## De candidato a versión

Un candidato es una propuesta. Para entrar en la bitácora:

1. `ml exportar c-XXX` reescribe solo los números de `params.h` y deja un
   borrador en `versions/_draft.json`.
2. `ml banco-c c-XXX` y `python3 tools/webots_reglamento.py --version c-XXX`
   lo miden en el banco en C y en Webots, en los dos modos. **Webots es el
   juez**: el simulador de GPU es cinemático y no tiene inercia.
3. Se completa el porqué del borrador (title, summary, rationale, hypothesis,
   risks) y se registra con `python3 tools/gnver.py new`.

## El simulador

`sim.py` y `fsm.py` son `tests/harness.c` y `strategy.c` vectorizados en
PyTorch: la misma cinemática, los mismos sensores y la misma máquina de
estados, con miles de asaltos a la vez. `validar` compara sus estadísticas con
las del C. La última validación dio 96 de 96 comparaciones dentro del error de
muestreo (|z| ≤ 2,1).

Modo **banco**: idéntico a `harness.c`. Modo **robusto**: aleatoriza lo que
Webots demostró que el banco fija (velocidad máxima de 1,05 a 1,65 m/s, agarre
±15 %, ruido y pérdidas del ToF, retardo de motor hasta 40 ms, pala del rival
leída como borde). Se entrena en modo robusto.

Rendimiento en la RTX 5070: unos 90.000 asaltos por segundo con 262.144
entornos; una corrida de 100 generaciones × 512 candidatos (7,4 M de asaltos)
tarda 3 minutos. PPO: unos 640.000 pasos de 8 ms por segundo.

Si `strategy.c` cambia de estructura (una versión `new-behavior`), hay que
portar el cambio a `fsm.py` y volver a ejecutar `ml validar`.

## Datos (`ml/data/`)

| Ruta | Qué es |
|---|---|
| `corridas/<id>/` | configuración, curva por generación, muestras y resumen de cada entrenamiento |
| `candidatos.json` | los campeones, con su origen y su evaluación |
| `clips/`, `pares.json` | las repeticiones grabadas y las comparaciones pendientes o votadas |
| `preferencias.jsonl` | tus votos, uno por línea; nunca se reescriben |
| `recompensa.pt`, `recompensa.json` | el modelo de recompensa y lo que ha aprendido de ti |
| `liga.json` | Elo, matriz de combates y dirección de mejora |
| `politicas/<id>/` | políticas PPO, su evaluación y su exportación a C |
| `validacion.json` | la última comparación contra el banco en C |

`GN_ML_DATA=/otra/carpeta` desvía todo esto: sirve para probar sin mezclar
datos de prueba con tus votos.

## Instalación

El entorno ya está en `ml/.venv` (Python 3.13, PyTorch 2.14 con CUDA 13).
Para rehacerlo:

```bash
uv venv ml/.venv --python 3.13
VIRTUAL_ENV=ml/.venv uv pip install torch numpy --index-url https://download.pytorch.org/whl/cu130 --extra-index-url https://pypi.org/simple
```

La interfaz de votos usa el diseño de la web de `codex/`: `web/codex.css` es
una copia exacta de `codex/web/style.css`. No se modificó nada en `codex/`.
