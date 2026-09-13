# Avance para revisar · 13 de septiembre de 2026

**22 revisiones registradas: 3 previas y 19 del trabajo actual. No se prevén más cambios de física mientras se completa la evaluación de v0022.** Las revisiones conservan los cambios y errores; `--revision 22` selecciona un modelo concreto, no pide hacer 22 pruebas.

- Historial y archivos: https://byemmanuel.github.io/Sumo_Page//#versions
- Webots está abierto en pausa, puerto 1340: física v0022, algoritmo histórico v0.1.0. Pulsa ▶ para observarlo. Esta sesión visual tiene resultados separados.
- [Datos de calibración](calibracion_webots.json) y [protocolo de medidas](PROTOCOLO_MEDIDAS_REALES.md).

## Qué se está modelando

El diseño copiado mantiene 495 g, ruedas de 42 mm, Pololu #3063, LiPo 2S, cinco VL53L0X y cuatro QTR. **El robot aún no existe: estos valores son nominales.** La lógica de `strategy.c` y los valores de `params.h` de todas las versiones permanecen intactos.

| Cambio | Cómo revisarlo |
|---|---|
| Motor eléctrico | El par disminuye con la velocidad; incluye batería, resistencia del motor y caída del puente. PWM cero supone freno eléctrico. |
| Superficie | Fricción nominal 1.1, intervalo exploratorio 0.6–1.6; sin adhesión. No está medida sobre tu dohyo. |
| Borde | Dohyo con colisión poligonal de 96 lados; ruedas cilíndricas. Se descartó una malla de ruedas porque desestabilizaba la marcha. |
| ToF | Abanico horizontal de 25°, lecturas cada 33 ms, rango y ruido variables. La máscara vertical ideal sigue siendo una aproximación importante. |
| QTR | Señal analógica, ADC de 12 bits y retardo; la pala clara puede activar línea. La curva necesita medidas físicas. |
| Tiempos | Ciclo 8 ms, retardo de actuación 8 ms, inicio tras 5 s. |

## Algo concreto que ya puedes juzgar

Medidas de **simulación nominal v0022**, no medidas físicas:

| Ensayo | Resultado |
|---|---|
| Aceleración con PWM=1 | 1.83 m/s al segundo |
| Frenada aplicando PWM=−1 | 25.4 cm y 256 ms hasta invertir la velocidad longitudinal |
| Frenada aplicando PWM=0 | 26.9 cm y 400 ms hasta velocidad horizontal menor de 0.01 m/s |
| Aproximación al borde con PWM=0.3 | Se detiene; recorre 3.15 cm desde la detección |
| Aproximación al borde con PWM=0.6 y 1.0 | **Cae del dohyo**, aun ordenando freno al detectar blanco |

En estos ensayos la orden viene de un diagnóstico, no de la estrategia. El caso de borde muestra por qué no basta con que el robot “vea blanco”: importa la distancia disponible para frenar. No se ha alterado la física para evitar esa caída.

![Curvas de aceleración y frenada](artifacts/calibracion-v0022.png)

Las curvas grises son tres realizaciones aleatorias; algunas se desvían y salen de la pista de calibración. No todas proporcionan una frenada válida. El JSON conserva las caídas y los valores no observados; esas curvas no son límites garantizados del robot.

## Qué falta y qué no está demostrado

La matriz final mide las cinco máquinas de estados y la red neuronal contra cinco rivales, con dos colocaciones y física nominal/aleatoria: **120 tandas de 30 asaltos, 3600 en total**. Son las combinaciones pedidas por el prompt; no son nuevas revisiones.

La línea base se reprodujo exactamente: v0.3.1 obtuvo 114 victorias de 120. Al introducir física, sensores y tiempos, la etapa v0015 obtuvo 84 victorias, 31 derrotas y 5 empates en los mismos cuatro rivales. La evaluación final aún estaba ejecutándose al crear esta vista; no confundir estas cifras intermedias con el resultado final.

Hubo repeticiones evitables: una derivada inicial incorrecta del encoder, la malla de ruedas descartada y una escritura de inercia que Webots rechazaba. Están conservadas y señaladas. La v0022 comprueba que la inercia solicitada se aplica y el ejecutor rechaza tandas con errores de Webots.

La red coincide con Python con el mismo historial registrado (error máximo menor de 4e−7), pero falla la equivalencia de trayectorias largas con realimentación independiente. Es una limitación abierta, no una validación completa de transferencia.

**Lo que más condiciona el diseño:** el modo real de frenado del TB6612, la fricción de las ruedas, la posición/lectura de los QTR y el montaje óptico de los ToF. No hay medidas tuyas para decidir sus valores con precisión. Se pueden revisar estas decisiones de diseño ahora; no hay motivos para afinar la estrategia a partir de un porcentaje aislado de victorias.


## Actualización: evaluación terminada

La física sigue en **v0022**. Terminaron los3600 asaltos. Consulta el [informe completo](INFORME_WEBOTS_REAL.md) y [Simulación](https://byemmanuel.github.io/Sumo_Page//#simulation).

| Algoritmo, reglamento | Nominal: V / D / E | Aleatorio: V / D / E |
|---|---|---|
| v0.3.1 |108 /32 /10|110 /36 /4|
| Red neuronal |70 /43 /37|80 /43 /27|

150 asaltos por celda, cinco rivales. Estos recuentos no prueban rendimiento en hardware. Las comprobaciones de software pasan; siguen pendientes las medidas físicas y la equivalencia neuronal con realimentación prolongada.
