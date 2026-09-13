/* ==========================================================================
 *  main.c  --  Controlador de Webots para Gelatina Nuclear
 *
 *  Lazo de control puro. Toda la inteligencia esta en algorithms/strategy.c
 *  y todo lo especifico de Webots en hal_webots.c. Este fichero es el mismo
 *  que correra en el robot real cambiando unicamente el backend del HAL.
 * ========================================================================== */

#include "hal.h"
#include "strategy.h"

#include <stdio.h>

int main(int argc, char **argv)
{
  if (!hal_init(argc, argv)) return 1;

  sumo_params_t p = sumo_params_default();
  p.dt_ms = hal_period_ms();          /* el periodo lo impone la plataforma */

  sumo_strategy_t brain;
  strategy_init(&brain, &p);
  hal_log("estrategia %s en linea", strategy_version());

  sumo_sensors_t   s;
  sumo_actuators_t a = { 0.0f, 0.0f, 0 };
  sumo_state_t     last = ST_COUNT;

  while (hal_poll(&s)) {
    strategy_step(&brain, &s, &a);
    hal_apply(&a);

    /* Telemetria minima: solo al cambiar de estado, para no inundar la
     * consola de Webots. Es la traza que se pega en la bitacora cuando una
     * version se comporta de forma inesperada. */
    if (brain.state != last) {
      last = brain.state;
      hal_log("t=%5u ms  %-11s  rival=%s d=%4u mm rumbo=%+5d cdeg  linea=0x%X",
              s.t_ms, strategy_state_name(brain.state),
              brain.per.target_seen ? "si" : "no",
              brain.per.target_dist_mm == SUMO_DIST_NONE ? 9999u : brain.per.target_dist_mm,
              brain.per.target_bearing_cdeg, brain.per.line_mask);
    }
  }

  hal_shutdown();
  return 0;
}
