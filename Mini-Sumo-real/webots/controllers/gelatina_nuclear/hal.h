/* ==========================================================================
 *  hal.h  --  Capa de abstraccion de plataforma
 *
 *  El algoritmo (algorithms/) no sabe si corre en Webots, en un banco de
 *  pruebas o en un microcontrolador. Solo existe este contrato de seis
 *  funciones. Portar Gelatina Nuclear al robot real consiste EXCLUSIVAMENTE
 *  en escribir un hal_<plataforma>.c nuevo: ni una linea de strategy.c cambia.
 *
 *  Backends existentes:
 *      hal_webots.c   -> simulacion              (este directorio)
 *      tests/harness.c -> banco nativo, integrado (no usa hal.h)
 *      hal_<mcu>.c    -> pendiente, robot real
 * ========================================================================== */
#ifndef SUMO_HAL_H
#define SUMO_HAL_H

#include "sumo_types.h"

/* Inicializa la plataforma. Devuelve false si algo imprescindible falta. */
bool hal_init(int argc, char **argv);

/* Periodo real del lazo de control en ms (lo impone la plataforma). */
uint16_t hal_period_ms(void);

/* Avanza un paso y rellena los sensores. false = la plataforma pide parar. */
bool hal_poll(sumo_sensors_t *s);

/* Aplica las consignas normalizadas a los motores. */
void hal_apply(const sumo_actuators_t *a);

/* Traza de depuracion (printf en simulacion, UART en el robot real). */
void hal_log(const char *fmt, ...);

/* Libera la plataforma. */
void hal_shutdown(void);

#endif /* SUMO_HAL_H */
