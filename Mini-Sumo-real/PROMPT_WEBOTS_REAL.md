Eres un agente de ingeniería en el proyecto de mini-sumo Gelatina Nuclear. Tu trabajo: ejecutar en Webots R2025a los algoritmos de control que ya existen y hacer que la simulación se parezca lo más posible al robot físico, midiendo cada paso. No vas a mejorar los algoritmos: vas a mejorar el mundo en el que se miden, para que lo que gane en Webots gane también en el dohyo real.

## 1. Dónde está todo (léelo entero antes de tocar nada)

Raíz: /home/byemmanuel/Desktop/Workspace/IA/Gelatina_Nuclear/

- `COORDINACION_LLM.md`: reglas entre agentes y hallazgos ya verificados. Léelo y rellena tu sección.
- `claude/Mini-Sumo/`: el proyecto. Es de otro agente y para ti es SOLO LECTURA.
  - `algorithms/strategy.c`, `strategy.h`, `params.h`, `sumo_types.h`: el algoritmo, una máquina de estados en C99 sin cabeceras de plataforma.
  - `versions/`: la bitácora. Cada versión tiene su instantánea en `versions/vX.Y.Z/snapshot/`. Las que importan: v0.3.0 y v0.3.1 (v0.3.1 lleva los parámetros afinados en GPU para el reglamento).
  - `webots/worlds/dohyo.wbt` y `webots/protos/GelatinaNuclear.proto`. El PROTO se GENERA desde `hardware/modelo_robot.py` con `python3 hardware/genera_proto.py`; nunca se edita a mano.
  - `webots/controllers/`: `gelatina_nuclear` (lazo de control y `hal_webots.c`), `oponente` (static | charger | spinner) y `arbitro` (supervisor: `--rounds`, `--rival`, `--colocacion reglamento|banco`, `--out`, `--version`).
  - `tools/webots_reglamento.py`: tanda sin ventana, un Webots por rival en paralelo. Si la versión es de la bitácora, compila Gelatina desde su instantánea.
  - `hardware/BOM.md`: componentes reales. Motor Pololu 50:1 Micro Metal HPCB 6 V a 7,4 V; 5 × VL53L0X; 4 × QTR-1A; STM32F411; TB6612FNG; LiPo 2S de 300 mAh; 495 g.
  - `REGLAMENTO.md`: reglas del torneo. Dohyo de 77 cm con línea de 2,5 cm; colocación a 5 cm de frente, de lado y de espaldas; tres rondas en tres minutos.
  - `ml/data/politicas/p-20260913-084929-reglamento-1/nn_politica.h`: una política neuronal (actor) en C99. Su entrada está definida en `ml/ppo.py`, en las funciones `observacion()` y `aplica()`; está resumida en la sección 6.
  - `CLAUDE.md`, `README.md` y `ml/README.md`: reglas y uso.

## 2. Reglas de convivencia (obligatorias)

1. No modifiques, compiles, borres ni hagas git dentro de `claude/`. Copia el proyecto a tu carpeta y trabaja sobre la copia:
   `rsync -a --exclude ml/.venv --exclude ml/data/cache claude/Mini-Sumo/ codex/Mini-Sumo-real/`
   Si no eres Codex, usa una carpeta propia hermana de `claude/` y dilo en `COORDINACION_LLM.md`.
2. Webots: usa los puertos 1300 o superiores. Cambia `PUERTOS` en tu copia de `tools/webots_reglamento.py`. No abras el `dohyo.wbt` de `claude/`, porque Webots escribe ficheros junto al mundo.
3. El otro agente puede estar usando la GPU. Pregunta en `COORDINACION_LLM.md` antes de lanzar trabajos largos en ella.
4. No cambies la lógica de `strategy.c` ni los números de `params.h`: son el objeto que se mide. Lo que cambias es la planta (física, sensores, actuadores y tiempos) y el HAL de Webots, que es la parte de la plataforma.

## 3. Qué significa "lo más real posible"

- Todo parámetro físico lleva su fuente. Vale una hoja de datos (cita el documento y la cifra), una medida del robot real (quién y cuándo) o un supuesto con su rango. Ningún número sin fuente.
- Lo que no se sabe con precisión se aleatoriza dentro de su rango, y el resultado se da como rango, no como un solo número.
- Un cambio de física cada vez, con la misma tanda antes y después.
- No ajustes la física para que gane una versión. Si un cambio realista hace perder a v0.3.1, se informa tal cual.
- Anota la versión de Webots, el paso (8 ms), las semillas y el sha256 del mundo, del PROTO y de los controladores de cada tanda.

## 4. Paso 0: reproducir la línea base

Con la copia sin cambios, reproduce estas cifras: Webots R2025a, robot de 495 g, 30 asaltos por rival (static, charger, spinner y v0.3.0 congelada).

| Versión | Reglamento V·D·E | Auto-salidas | Combate ganado de media | Diagonal V·D·E |
|---|---|---|---|---|
| v0.3.0 | 49 · 68 · 3 | 63 | 25,9 % | 99 · 20 · 1 |
| v0.3.1 | 114 · 6 · 0 | 0 | 100 % | 89 · 31 · 0 |

Órdenes: `python3 tools/webots_reglamento.py --version v0.3.0` y la misma con `--colocacion banco`; después, igual con `--version v0.3.1`. Si no coinciden, para y explica la causa antes de seguir.

## 5. Pasos de realismo

En este orden, y cada uno con medida antes y después.

A. **Motor y alimentación.** Webots aplica el par máximo constante hasta la velocidad máxima; un motor de continua real pierde par con la velocidad. Modela en el HAL de tu copia (`hal_webots.c`) un motor de continua: par = k·i, con i = (u·V_bat − k·ω) / R, donde u es la consigna PWM. Aplícalo con control por par (`wb_motor_set_torque`) o limitando par y velocidad en cada paso.
- Datos: 650 rpm y 0,74 kg·cm a 6 V, escalados a 7,4 V como en `hardware/modelo_robot.py`; saca R y k de la hoja del motor.
- Comprueba con la hoja del TB6612FNG si su corriente continua y de pico por canal limita el par de bloqueo a 7,4 V.
- Tensión de la LiPo 2S: de 8,4 V llena a unos 7,0 V bajo carga; aleatorízala por asalto.
- Verifica la curva de aceleración desde parado, la velocidad final y la distancia de frenada desde velocidad máxima.

B. **Contacto rueda-dohyo.** Silicona sobre madera. Fija `coulombFriction` y el deslizamiento (`forceDependentSlip`) con fuente o con rango, sin adherencia: el reglamento prohíbe neumáticos que levanten un A4. Prueba el empuje frontal contra un robot igual frenado: ¿patina o empuja? Revisa también el problema ya conocido: con la rueda a menos de 2 cm del canto, el contacto cilindro-cilindro de ODE empuja al robot fuera. Documenta si sigue y cómo lo mitigas.

C. **Sensores de distancia VL53L0X.** Hoy son un rayo hasta 1,2 m con ruido fijo. El sensor real tiene:
- un cono de 25°;
- alcance hasta unos 2 m, según la superficie;
- una medida cada unos 33 ms en el modo por defecto, así que con un lazo de 8 ms el valor se repite entre lecturas;
- una distancia mínima fiable;
- ruido que crece con la distancia, según la hoja de datos.

Implementa el cono sin que vea el suelo: con tres rayos ya veía el dohyo a 0,5 m (ver `COORDINACION_LLM.md`). La frecuencia de medida va en el HAL.

D. **Sensores de línea QTR-1A.** Lectura analógica que depende de la altura (unos 6 mm), contraste negro/blanco, ruido del ADC y latencia. Mantén el efecto real de que la pala metálica del rival se lee como blanco.

E. **Tiempos del microcontrolador.** Lazo de 8 ms, lectura I2C secuencial de los cinco ToF y un ciclo de retardo entre sensor y actuador. Modélalo en el HAL.

F. **Arranque y colocación.** Pulsador más 5 s (`AUTO_ARM_MS` en el HAL), error de colocación a mano de ±3 mm y ±3° (el árbitro ya lo aplica con `--colocacion reglamento`) y ronda máxima de 60 s.

G. **Rivales.** Además de static, charger y spinner, añade al menos un rival realista con la misma física: por ejemplo, arranque rápido de flanco o pala más baja. Los rivales no se versionan: si los cambias, dilo en el informe.

## 6. Ejecutar los algoritmos

- **Máquinas de estados:** todas las versiones de `versions/`, compiladas desde su instantánea (como hace `tools/webots_reglamento.py`).
- **Política neuronal:** crea en tu copia un controlador `gelatina_nn` que use `nn_politica.h`. La entrada debe ser exactamente la de `ml/ppo.py`: 21 valores en este orden, con t en ms.
  - 1 a 5: d/1200 si la lectura es válida (hay objetivo y d ≤ 1190 mm); si no, 1,0. Orden de sensores: L60, L30, C, R30, R60.
  - 6 a 9: línea FL, FR, RL, RR (0 o 1).
  - 10 y 11: consignas izquierda y derecha del ciclo anterior, después de la rampa y antes de la zona muerta.
  - 12: 1 si algún sensor de distancia es válido en este ciclo.
  - 13: rumbo / (π/3). El rumbo es Σ wᵢ·aᵢ / Σ wᵢ, con wᵢ = 1200 − dᵢ sobre los sensores válidos y a = +60°, +30°, 0°, −30°, −60° en radianes. Sin sensores válidos, se mantiene el último.
  - 14: el mínimo de los valores 1 a 5.
  - 15: min(t − t_visto, 1000) / 1000, donde t_visto es el último ciclo con algún sensor válido (vale −10 000 al empezar).
  - 16: min(t − t_línea, 1000) / 1000, donde t_línea es el último ciclo con alguna línea (vale −10 000 al empezar).
  - 17 a 20: la última máscara de línea no vacía; se mantiene hasta que aparece otra.
  - 21: min(ms desde el arranque, 3000) / 3000.

  Salida: `nn_politica(obs, out)` devuelve dos valores en [−1, 1]. Se recortan, pasan por la rampa de 0,2 por ciclo de 8 ms respecto al valor aplicado anterior y por la zona muerta de 0,04. Sin arranque, las consignas son 0 y la memoria sigue actualizándose.

  Antes de medir, comprueba con 20 secuencias de sensores grabadas que tu C da la misma observación y la misma salida que Python (error menor que 1e-5). Esta política se entrenó solo en un simulador cinemático: se espera que empeore en Webots, y hay que medir cuánto.
- **Para cada algoritmo:** tanda de reglamento y tanda de diagonal, con al menos 30 asaltos por rival, con y sin la aleatorización de la sección 5. Informa los resultados por colocación.

## 7. Datos para calibrar el simulador de GPU

Con el mundo final, graba en Webots estos ensayos y guárdalos en `calibracion_webots.json`, con series cada 8 ms, un resumen y las condiciones de cada ensayo (tensión, fricción, semilla):

1. Consigna de 0 a 1 desde parado: velocidad y posición durante 1 s.
2. Frenada desde velocidad máxima, con consigna −1 y con consigna 0: distancia y tiempo hasta parar.
3. Giro en el sitio a ±1: velocidad angular.
4. Empuje frontal contra un rival frenado y contra un rival que empuja igual: quién avanza y a qué velocidad.
5. Aproximación al borde con consigna 0,3, 0,6 y 1,0: distancia recorrida desde que el IR ve la línea hasta parar.

## 8. Lo que solo puede medir el usuario

Escribe un protocolo corto (qué medir, con qué instrumento y cómo anotarlo) para:
- rpm con carga y corriente de bloqueo;
- diámetro real de la rueda;
- masa y centro de masas;
- fricción sobre el dohyo, con un plano inclinado;
- frenada desde velocidad máxima;
- lecturas del VL53L0X frente a la carcasa del rival entre 5 y 100 cm;
- lecturas del QTR sobre negro, blanco y la pala;
- duración real del lazo en el STM32.

## 9. Entregables

- `INFORME_WEBOTS_REAL.md` en tu carpeta. Debe incluir cada cambio con su fuente y su antes y después, la tabla final por algoritmo, colocación y rival, y la lista de lo que sigue siendo un supuesto.
- Tu copia del proyecto con los cambios.
- `calibracion_webots.json` (sección 7).
- El protocolo de medidas (sección 8).
- Tu sección de `COORDINACION_LLM.md` actualizada.

## 10. Criterio de hecho

- La línea base está reproducida, o la discrepancia está explicada.
- Los pasos A a F están implementados, cada uno con su fuente y su medida antes y después.
- Todas las versiones y la política neuronal están medidas en el mundo final.
- El JSON de calibración y el protocolo están entregados.
- No se ha modificado nada en `claude/`.
