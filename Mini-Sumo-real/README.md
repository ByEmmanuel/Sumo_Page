# Gelatina Nuclear

Robot **mini-sumo** de competición: 10 × 10 cm, 500 g máximo, objetivo tirar al
rival fuera del dohyo. Se diseña y se mide en **Webots**, y está escrito para
acabar corriendo en el robot físico sin reescribir el algoritmo.

El proyecto avanza por iteraciones sucesivas, y **cada cambio en el sistema de
control queda registrado en una bitácora navegable**:

📊 **[Bitácora de algoritmos](https://claude.ai/code/artifact/2fe653b8-287f-46ce-abb4-0ef248b5941d)** — qué cambió, por qué, y qué resultado dio en el ring.

---

## La idea en una frase

El algoritmo no sabe dónde corre. `algorithms/strategy.c` consume un
`sumo_sensors_t` y produce un `sumo_actuators_t`; nada más. La plataforma entra
por detrás, a través de `hal.h`:

```
                    ┌──────────────────────────┐
                    │  algorithms/strategy.c   │   <- lo que versiona la bitácora
                    │  (C99 puro, sin deps)    │
                    └────────────┬─────────────┘
                                 │  sumo_types.h
              ┌──────────────────┼──────────────────┐
              │                  │                  │
       hal_webots.c        tests/harness.c     hal_<mcu>.c
       (simulación)        (banco nativo)      (robot real, pendiente)
```

Portar Gelatina Nuclear al hardware real consiste en escribir un backend nuevo.
Ni una línea de la estrategia cambia.

## Estructura

| Ruta | Qué es |
|---|---|
| `algorithms/` | **El cerebro.** Lógica pura versionada: contrato, parámetros y máquina de estados. |
| `hardware/` | **El robot real.** `BOM.md` con los componentes, `modelo_robot.py` (de las piezas salen la masa, el centro de masas y la inercia) y renders en `render/`. |
| `webots/protos/` | PROTO del robot, **generado** con `python3 hardware/genera_proto.py`: no se edita a mano. |
| `webots/worlds/dohyo.wbt` | Dohyo reglamentario de 770 mm con banda blanca de 25 mm. |
| `webots/controllers/gelatina_nuclear/` | Lazo de control y backend de Webots. |
| `webots/controllers/oponente/` | Rivales de referencia. Es el examen, no el alumno. |
| `webots/controllers/arbitro/` | Supervisor: coloca, arbitra, cuenta y exporta métricas. |
| `tests/harness.c` | Ring simulado sin Webots. 240 asaltos en milisegundos. Con `--reglamento`, las colocaciones y el combate a 3 rondas del torneo. |
| `ml/` | **Aprendizaje en GPU.** El mismo ring vectorizado en PyTorch, estrategia evolutiva, política neuronal (PPO), modelo de recompensa entrenado con tus votos e interfaz de votos. Ver `ml/README.md`. |
| `REGLAMENTO.md` | Cada regla del torneo y su estado en el proyecto. |
| `tools/gnver.py` | La bitácora de algoritmos. |
| `tools/build_site.py` | Genera la página de la bitácora. |
| `tools/webots_reglamento.py` | Tanda de Webots sin ventana contra los cuatro rivales, en paralelo. |
| `versions/` | Una carpeta por versión: metadatos, instantánea del código y diff. |

## Uso

```bash
make medir     # compila el algoritmo y lo mide contra los 4 rivales
make check     # falla si hay código de control sin versionar
make sitio     # regenera site/index.html
```

`make medir` no necesita Webots y tarda menos de un segundo. Es el sparring
diario; Webots es el juez final.

```bash
./tests/build/harness --all --rounds 60 --reglamento      # colocaciones del torneo
python3 tools/webots_reglamento.py --version v0.3.1        # Webots, cuatro rivales
ml/.venv/bin/python -m ml servidor                         # votar: http://localhost:8765
```

## Ejecutar en Webots

Probado con Webots R2025a (en Arch: `yay -S webots-bin`, o desde
https://cyberbotics.com/).

```bash
export WEBOTS_HOME=/usr/local/webots
make links                 # rehace los enlaces del controlador
webots webots/worlds/dohyo.wbt
```

El mundo y el PROTO siguen la convención de ejes de R2022a en adelante (ENU,
`Cylinder` sobre z). Un mundo escrito con la convención antigua pone el dohyo
de canto y los robots salen despedidos nada más arrancar.

Webots compila los controladores solo al abrir el mundo. Para una tanda de
combates automatizada, el árbitro ya está en el mundo: escribe
`runs/webots_ultimo.json`, que se carga en la bitácora con
`python3 tools/gnver.py metrics vX.Y.Z --from runs/webots_ultimo.json`.

Si abres el mundo sin árbitro, los robots se arman solos a los 5 s. Es el
retardo habitual en las reglas internacionales; el reglamento del torneo no lo
fija (ver `REGLAMENTO.md`).

### Calibrar los sensores de línea

El umbral de línea (`LINE_TH_DEFAULT = 400` en `hal_webots.c`) es un valor de
partida. Para verificar las lecturas reales, arranca el controlador con
`controllerArgs [ "--calib" ]` y observa la consola: sobre negro debería leer
cerca de 20 y sobre la banda blanca cerca de 900.

## Estado actual

**v0.3.1**: la máquina de estados de v0.3.0 con sus parámetros afinados en la
GPU para las colocaciones del reglamento (frente, lado y espaldas a 5 cm). En
Webots con el reglamento gana el combate a los cuatro rivales del banco
(114V 6D, ninguna auto-salida), frente al 26 % de v0.3.0, que se salía sola en
63 de 120 asaltos.

Punto débil conocido: en la diagonal antigua a 36 cm, v0.3.0 le gana 26 de 30
asaltos, porque su apertura lenta deja que un rival rápido le embista desde
lejos. El reglamento no usa esa colocación.

Siguiente paso: tus votos en la interfaz de `ml/` y una segunda vuelta de
entrenamiento con v0.3.1 en la liga.
