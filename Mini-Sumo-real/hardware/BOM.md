# Gelatina Nuclear: hardware

> Generado por `hardware/genera_proto.py` desde `hardware/modelo_robot.py`.
> Cambia las piezas allí y regenera: el PROTO de Webots sale de los mismos datos.

Configuración típica de competición de mini-sumo, elegida para que coincida
con lo que el proyecto ya asumía: motor N20 con reductora, puente en H,
ruedas de 42 mm, 5 sensores de distancia al frente, 4 de línea en las
esquinas, IMU y pulsador de arranque. **Si tus piezas reales son otras,
cámbialas en `modelo_robot.py` y regenera.**

## Lista de materiales

| Cant. | Componente | Referencia | Masa total (g) | Notas |
|---|---|---|---|---|
| 2 | Motorreductor | Pololu #3063: 50:1 Micro Metal Gearmotor HPCB 6V (51,45:1) | 19.0 | 650 rpm y 0,74 kg·cm a 6 V; a 7,4 V, 802 rpm (84 rad/s) y 0,090 N·m |
| 2 | Soporte de motor | Soporte para micro metal gearmotor (Pololu) | 2.0 |  |
| 2 | Rueda | Llanta de PLA impresa + neumático de silicona colada, Ø42 × 15 mm | 28.0 | Ø y ancho del modelo desde v0.1.0; 4 g de llanta + 10 g de neumático |
| 5 | Sensor de distancia ToF | Pololu #2490: VL53L0X, placa de 13 × 18 mm | 2.5 | hasta 2 m con FoV de 25°; en la simulación, 1 rayo hasta 1,2 m |
| 4 | Sensor de línea + soporte | Pololu #958: QTR-1A (QRE1113), 7,6 × 12,7 mm | 2.9 | a ~6 mm del suelo; los delanteros van tras la pala |
| 1 | PCB principal | FR4 de 1,6 mm, 78 × 68 mm | 15.7 | cara superior del robot |
| 1 | Componentes de la PCB | STM32F411CEU6, MPU-6050, TB6612FNG, AMS1117-3.3, cristal, XT30, JST-SH, interruptor | 5.0 | el MPU-6050 aporta los dispositivos imu y giro |
| 1 | Pulsador de arranque | Pulsador táctil de 6 × 6 mm con capuchón y cableado | 1.0 | reglamento p. 4: arranque con pulsador o interruptor; en Webots, la señal ARM del árbitro |
| 1 | Batería | LiPo 2S 7,4 V 300 mAh 45C con XT30 (46 × 16 × 14 mm) | 20.0 | p. ej. TATTU 300 mAh 2S |
| 1 | Placa base | Aluminio 6061, 80 × 68 × 2 mm | 29.4 |  |
| 1 | Carcasa | PLA impreso: paredes y barra de sensores | 19.6 | color del robot |
| 1 | Pala | Acero inoxidable de 1,5 mm, 98 × 30 mm a 34° | 34.8 | arista a 0,8 mm del suelo |
| 1 | Patín trasero | PTFE Ø8 mm | 1.5 |  |
| 1 | Cableado | Silicona 26-28 AWG | 4.0 |  |
| 1 | Tornillería | M2 inox | 3.0 |  |
| 1 | Lastre | Aleación de tungsteno W-Ni-Fe (18 g/cm³) | 306.6 | dimensionado para cerrar 500 g con el CdM 4 mm tras el eje |
| | **Total** | | **495.0** | reglamento: ≤ 500 g |

## Propiedades físicas (las que usa Webots)

- Centro de masas del robot completo: x = -14.0 mm, y = +0.0 mm,
  z = 13.4 mm. Queda 4.0 mm por detrás del eje de las ruedas.
- Cuerpo sin ruedas: 467.0 g; inercia respecto a su CdM (kg·m²):
  Ixx = 1.997e-04, Iyy = 2.425e-04, Izz = 3.807e-04.
- Rueda: 14 g; inercia respecto al eje 2.21e-05 kg·m², transversal 2.32e-06 kg·m².
- Lastre: 306.6 g de tungsteno, placa de 35.5 × 60 × 8 mm en el suelo del chasis.
- Motor #3063: referencia de fabricante650rpm,0.74kg·cm,1.5A a6V.
  El HAL calcula el par electrico, las perdidas y la tension; ver `real/parameters.json`.
  Los limites Webots 150.0rad/s y 0.2500N·m son techos numericos, no prestaciones del motor.

## Limitaciones conocidas del modelo

- El motor usa control por par electrico en el HAL. No se modelan temperatura ni inductancia.
- La inercia del rotor reflejada se estima geometricamente y se aleatoriza; falta medirla.
- A menos de ~2 cm del canto del dohyo, el contacto cilindro-cilindro de ODE
  empuja la rueda hacia fuera (verificado con una prueba A/B).

## Fuentes

- Motor: https://www.pololu.com/product/3063/specs
- VL53L0X: https://www.pololu.com/product/2490/specs
- QTR-1A: https://www.pololu.com/product/958
- LiPo 2S 300 mAh: TATTU 45C XT30, 46 × 16 × 14 mm y 20 g según el fabricante.
