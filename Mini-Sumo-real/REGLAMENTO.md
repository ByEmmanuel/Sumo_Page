# El reglamento y Gelatina Nuclear

Fuente: `../Extras/Reglamento de MINISUMO II .pdf` (24 páginas), leído entero
el 13-09-2026. Aquí va cada regla que afecta al robot o a la simulación, con
su estado en el proyecto:

- **cumple**: el proyecto ya lo respetaba;
- **ajustado**: se cambió el proyecto para cumplirlo;
- **pendiente**: depende del robot real o de la organización.

## El robot

| Regla (página) | Estado | En el proyecto |
|---|---|---|
| Cabe en 10 × 10 cm, alto libre (p. 3) | cumple | Huella de 10 × 10 cm en `hardware/modelo_robot.py` y en el PROTO. |
| Peso **por debajo** de 500 g (p. 3) | ajustado | El modelo cerraba 500 g justos, que no es "por debajo". Pasa a **495 g**: deja 5 g de margen para la báscula del evento. El lastre de tungsteno absorbe la diferencia (`MASA_TOTAL`); el PROTO y el BOM se regeneran con `python3 hardware/genera_proto.py`. |
| Puede expandirse tras el inicio sin separarse; perder menos de 5 g no descalifica (p. 4) | cumple | No hay piezas desplegables. |
| Autónomo, con todo el control a bordo (p. 4) | cumple | STM32F411 a bordo; la estrategia no depende de nada externo. |
| Número de registro visible (p. 4) | pendiente | Lo asigna la organización. Hay que rotularlo en la carcasa. |
| Arranque con pulsador o interruptor, y apagado al terminar (p. 4) | ajustado | El BOM llevaba un receptor IR de módulo de arranque. Pasa a **pulsador de arranque**; el interruptor de encendido ya estaba en la PCB. En la simulación, la señal `ARM` del árbitro hace de pulsación. |
| Sin interferencias IR, sin dañar el dohyo, sin líquidos, fuego ni proyectiles (p. 5-6) | cumple | Los VL53L0X emiten pulsos IR para medir distancia, no para saturar al rival. |
| Los neumáticos no levantan un A4 más de 2 s (p. 6) | cumple, a vigilar | Silicona sin aditivos. En Webots, el coeficiente rueda-dohyo es 1,6: alto, pero sin adhesión. El simulador de GPU aleatoriza el agarre ±15 % para que la estrategia no dependa de ese número. |
| Sin imanes ni vacío (p. 6) | cumple | El lastre es de tungsteno. |

## El dohyo y el combate

| Regla (página) | Estado | En el proyecto |
|---|---|---|
| Dohyo circular de 77 cm, línea de 2,5 cm, madera (p. 7) | cumple | `dohyo.wbt`, el banco nativo y el simulador de GPU usan 385 mm de radio y banda blanca desde 360 mm. |
| Fuera = cualquier parte toca el suelo más allá del borde exterior de la línea; la línea es área de combate (p. 9) | aproximado | El árbitro de Webots da por fuera al robot con el centro 3 cm más allá del borde o hundido 12 mm; el banco nativo, con el centro a 1,9 cm. Con el dohyo elevado 25 mm, eso equivale a tocar el suelo. La pala volada sin tocar (caso 3) sigue dentro, porque el centro no ha pasado. |
| Tres rondas en tres minutos; gana quien suma dos Yuko; si se acaba el tiempo, gana quien tenga un Yuko; con cero, ronda extra (p. 8 y 12) | ajustado | **Modo reglamento** en `tests/harness.c` (`--reglamento`), en el simulador de GPU y en el árbitro (`--colocacion reglamento`): 60 s por ronda y probabilidad de ganar el combate a partir de cada colocación. El modo de siempre no cambia: da exactamente las mismas cifras que antes (135/38/67 para v0.3.0), así que las métricas anteriores siguen siendo comparables. |
| **Colocación: 1.ª ronda frente a frente a 5 cm; 2.ª de lado, en sentidos opuestos, a 5 cm; 3.ª de espaldas a 5 cm** (p. 10-11) | ajustado | Es el cambio más grande. Antes los robots salían en diagonal a 36 cm, mirándose. Ahora salen en la cruz central, con 15 cm entre centros. |
| Yuko también si el rival sale solo (p. 13) | cumple | El banco distingue "expulsado" de "auto-salida"; las dos puntúan para el rival. |
| Doble eliminación (p. 19-22) | orienta el objetivo | Perder un combate no elimina, perder dos sí. El entrenamiento optimiza la probabilidad de ganar el combate contra una liga variada de rivales, no un asalto suelto. |

## Lo que el reglamento no dice (y el proyecto supone)

- **No fija un retardo de 5 s tras el arranque.** `hal_webots.c` arma al robot
  a los 5 s si no hay árbitro, como en las reglas internacionales habituales.
  Con arranque por pulsador hace falta algún retardo para retirar la mano.
  Hay que confirmarlo con la organización.
- **No da un límite por ronda.** Se usan 60 s: tres minutos entre tres rondas.

## Qué destapó el modo reglamento

Con las colocaciones del reglamento, v0.3.0 tenía puntos ciegos que la
diagonal escondía. Banco nativo en C, tabla oficial (60 asaltos por rival):

| Rival | Frente | Lado | Espaldas | Gana el combate |
|---|---|---|---|---|
| static | 100 % | 100 % | **0 %** | 100 % |
| charger | 35 % | **10 %** | 100 % | 47,8 % |
| spinner | **5 %** | 100 % | 100 % | 100 % |

De espaldas contra un rival inmóvil perdía los 20 asaltos; de frente contra
el spinner, 19 de 20. Es lo primero que ataca el entrenamiento en GPU
(`ml/`).
