# Gelatina Nuclear — reglas del proyecto

Robot mini-sumo (10 × 10 cm, 500 g) simulado en Webots, destinado a
construirse en la vida real. El proyecto avanza por iteraciones: se propone un
cambio de algoritmo, se mide en el ring, y se registra en la bitácora.

## Regla innegociable: nada sin versionar

Cualquier cambio, por pequeño que sea, en `algorithms/` o en
`webots/controllers/gelatina_nuclear/` debe quedar registrado en la bitácora
**antes de dar el trabajo por terminado**.

```bash
python3 tools/gnver.py check      # sale con código 2 si hay código sin versionar
```

La bitácora no es un registro de commits: es la explicación del razonamiento.
Cada entrada obliga a redactar `summary` (qué cambió), `rationale` (por qué) e
`hypothesis` (qué se espera que mejore). Una entrada sin el porqué no sirve
para nada, que es justamente el propósito del proyecto.

## Ciclo de una iteración

```bash
# 1. tocar el algoritmo
$EDITOR algorithms/strategy.c        # o params.h para un simple ajuste

# 2. medir en el banco nativo (segundos, no necesita Webots)
make medir

# 3. registrar la versión con su razonamiento
$EDITOR versions/_draft.json         # ver versions/v0.1.0/meta.json de modelo
python3 tools/gnver.py new --from-json versions/_draft.json --bump patch

# 4. cargar los resultados en la versión recién creada
python3 tools/gnver.py metrics vX.Y.Z --from runs/vX.Y.Z.json --verdict mejora

# 5. republicar la página (mismo enlace)
#    Artifact con url=https://claude.ai/code/artifact/2fe653b8-287f-46ce-abb4-0ef248b5941d
```

El torneo usa las colocaciones del reglamento (`REGLAMENTO.md`): mide también
con `./tests/build/harness --all --rounds 60 --reglamento` y en Webots con
`python3 tools/webots_reglamento.py --version vX.Y.Z`, y carga esas medidas
aparte con `gnver metrics vX.Y.Z --from ... --campo metrics_reglamento` (o
`metrics_webots`). `metrics` sigue siendo la tabla oficial de siempre.

Un ajuste de números también puede salir de la GPU (`ml/README.md`):
`python -m ml exportar c-XXX` escribe `params.h` y el borrador, pero el porqué
lo redacta quien registra la versión y Webots decide si es mejora.

`gnver new` y `gnver metrics` regeneran `site/index.html` solos. La página
publicada vive en el artifact de arriba: **republicar siempre sobre esa URL**,
nunca crear una nueva, o el usuario pierde el enlace que ya tiene.

## Invariantes de arquitectura

Romper cualquiera de estas exige, como mínimo, una versión `minor` y explicarlo
en la entrada:

1. **`algorithms/strategy.c` jamás incluye cabeceras de plataforma.** Ni
   Webots, ni HAL, ni un SDK de microcontrolador. Solo `strategy.h`. Es lo que
   permite que el mismo fichero compile en la simulación, en el banco nativo y
   en el robot real.
2. **Todo número sintonizable vive en `params.h`.** Un ajuste debe producir un
   diff de tres líneas legible de un vistazo en la bitácora. Un número mágico
   enterrado en `strategy.c` convierte el diff en ruido.
3. **`sumo_types.h` es el contrato y casi no cambia.** Tocarlo rompe todos los
   backends a la vez.
4. **Portar al robot real = escribir un `hal_<plataforma>.c` nuevo.** Nada más.

## Tipos de versión

`baseline`, `tuning` (solo números), `new-behavior` (estado o capacidad nueva),
`refactor` (misma conducta), `bugfix`, `experiment`, `revert`.
Convención: `tuning` y `bugfix` suben `patch`; `new-behavior` sube `minor`;
un cambio del contrato sube `major`.

## El banco de rivales no se toca a la ligera

`tests/harness.c` y `webots/controllers/oponente/` son el examen, no el alumno,
y por eso no se versionan. Pero si se modifican, las métricas de las versiones
anteriores dejan de ser comparables: hay que anotarlo a mano en la entrada
afectada y, si el cambio es grande, volver a medir las versiones previas.

## Idioma

El código, los comentarios y la bitácora van en español. Los identificadores C
sin acentos, por compatibilidad con toolchains de microcontrolador.
