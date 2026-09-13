# Protocolo de medidas del prototipo

Estado: el usuario confirmó el 13-09-2026 que todavía es un diseño. Ninguno de
los valores del BOM se considera una medida del robot. Anotar cada ensayo con
fecha, operador, instrumento y resolución, montaje, tensión en bornes, temperatura,
superficie y cinco repeticiones. Conservar las muestras originales y los fallos.

| Magnitud | Instrumento y procedimiento | Registro |
|---|---|---|
| RPM con carga | Tacómetro óptico o encoder y rodillo de carga. Medir ambos motores a las tensiones reales de alimentación, anotando fuerza tangencial en la rueda y corriente; incluir vacío y varios puntos de carga. | Tiempo, V, A, rpm, fuerza N, motor L/R. |
| Corriente de bloqueo | Preferir identificar la resistencia con una fuente de laboratorio limitada en corriente y tensión baja, rotor inmovilizado en un soporte, en varias posiciones; descontar cables y puente y extrapolar I=V/R. No bloquear el motor directamente con la LiPo. Una medida de bloqueo a tensión nominal requiere instrumentación y un procedimiento térmico específico: Pololu advierte que puede dañar motor y reductora. | V en motor, I, duración del pulso, resistencia de cables, posición del rotor, temperatura; distinguir extrapolado de medido. |
| Diámetro de rueda | Calibre en varios ángulos, sin aplastar la silicona; medir ambas ruedas. Con el robot cargado, marcar una vuelta sobre el dohyo y medir el avance para obtener el radio efectivo. | Diámetros mm, anchura mm, circunferencia bajo carga mm, masa sobre cada rueda. |
| Masa y centro de masas | Báscula con resolución adecuada; pesar el robot completo, batería y cableado incluidos. Apoyar en dos líneas de soporte de separación conocida y medir las reacciones: x=L·F2/(F1+F2). Repetir en el otro eje. Para altura, repetir con inclinación conocida y aplicar equilibrio de momentos con la geometría anotada. | Masa g, posiciones de soportes mm, reacciones g/N, ángulo y cálculo del centro de masas; no inferir altura de una sola pesada plana. |
| Fricción | Muestra del mismo dohyo, plano inclinable e inclinómetro. Bloquear las ruedas y elevar lentamente hasta deslizamiento: μ estática≈tan(ángulo). Evitar vuelco con un montaje de ensayo que conserve carga y material. Para fricción dinámica, medir fuerza de arrastre a velocidad constante con dinamómetro. | Ángulo de inicio, fuerza, carga normal, humedad, limpieza, lote de silicona; ensayo A4 por separado. |
| Frenada | Cámara de alta velocidad con escala y marcas de posición, sobre pista del mismo material. Alcanzar velocidad estable y registrar la orden y la detención para PWM=0 y PWM=−1; identificar si 0 significa cortocircuito o rueda libre. | V bajo carga, velocidad inicial m/s, instante de orden, curva x(t), distancia y tiempo de parada. |
| VL53L0X | Blanco formado por la carcasa y pala previstas del rival; regla o carril, luz registrada. Medir a 5, 10, 20, 30, 50, 70 y 100 cm, centrado y en distintos ángulos; repetir sin blanco y sobre dohyo vacío. Capturar al menos 100 lecturas por condición, incluyendo códigos de validez y timestamps. | Distancia real y leída mm, estado, intervalo real ms, material, tamaño aparente, ángulo, iluminación y perfil/timing budget. |
| QTR-1A | Registrar ADC crudo sobre negro, banda blanca y pala, a alturas de 3, 4, 5 y 6 mm, en reposo y cruzando la frontera. Medir también la alimentación y la polaridad analógica. | Altura mm, ADC, V, material, luz, timestamp y distribución; calibrar el umbral después de medir, mediante una versión nueva. |
| Lazo STM32 | Conmutar un GPIO al entrar/salir del ciclo y otro alrededor de las cinco lecturas I2C y de la actualización PWM. Usar analizador lógico/osciloscopio durante búsqueda, contacto y lecturas inválidas. | Periodo, duración, percentiles, máximo, jitter, duración de cada lectura, orden I2C y latencia sensor→PWM. |

CSV común sugerido:
`ensayo,repeticion,operador,fecha,instrumento,t_ms,tension_v,canal,valor,unidad,condicion`.
Adjuntar fotos del montaje y configuración del firmware, con versión y hash.
No corregir los datos para acercarlos al simulador: las discrepancias sirven para
ajustar la planta en una revisión posterior.

Fuentes: [motor Pololu #3063](https://www.pololu.com/product/3063/specs),
[QTR-1A](https://www.pololu.com/product/958),
[VL53L0X, tablas de prestaciones y condiciones](https://www.st.com/resource/en/datasheet/vl53l0x.pdf).
