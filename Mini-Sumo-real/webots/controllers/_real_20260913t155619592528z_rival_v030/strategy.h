/* ==========================================================================
 *  strategy.h  --  API publica del cerebro de Gelatina Nuclear
 *
 *  Toda la inteligencia del robot vive detras de dos funciones. El backend
 *  (Webots, firmware o banco de pruebas) solo rellena sensores, llama a
 *  strategy_step() y aplica los actuadores. Nada mas.
 * ========================================================================== */
#ifndef SUMO_STRATEGY_H
#define SUMO_STRATEGY_H

#include "sumo_types.h"
#include "params.h"

/* Estados de la maquina de combate. El orden importa: se publica como
 * indice en actuators.led para poder depurar desde fuera. */
typedef enum {
  ST_WAIT = 0,      /* inmovil, esperando la senal de arranque       */
  ST_OPENING,       /* jugada de apertura, los primeros ~400 ms      */
  ST_SEARCH,        /* barrido buscando al rival                     */
  ST_TRACK,         /* rival localizado lejos, aproximacion          */
  ST_ATTACK,        /* rival enganchado, empuje maximo               */
  ST_EDGE_ESCAPE,   /* borde detectado, salvar el combate            */
  ST_COUNT
} sumo_state_t;

/* Percepcion derivada, expuesta para telemetria y depuracion. */
typedef struct {
  bool     target_seen;        /* hay rival creible ahora mismo      */
  uint16_t target_dist_mm;     /* distancia al mas cercano           */
  int16_t  target_bearing_cdeg;/* rumbo estimado en centigrados, + = babor */
  uint8_t  line_mask;          /* bits segun enum sumo_line_idx      */
  uint32_t last_seen_ms;       /* instante del ultimo contacto       */
  bool     contact_front;      /* rival pegado y de frente, visto EN ESTE ciclo */
} sumo_percept_t;

typedef struct {
  sumo_params_t  p;
  sumo_state_t   state;
  sumo_percept_t per;

  uint32_t t_ms;             /* reloj recibido en el ultimo paso      */
  uint32_t t_state_ms;       /* instante de entrada al estado actual  */
  uint32_t t_edge_clear_ms;  /* fin de la ventana ciega tras un borde */

  /* sub-fase del escape de borde */
  uint8_t  esc_phase;        /* 0 = retroceder/avanzar, 1 = reencuadrar */
  float    esc_turn;         /* signo y fuerza del giro de escape       */
  float    esc_drive;        /* +1 avanzar, -1 retroceder               */

  /* sub-fase de la busqueda */
  bool     search_probing;

  /* salida anterior, para el limitador de pendiente */
  float    prev_left;
  float    prev_right;

  uint32_t edge_events;      /* contador de bordes vistos, telemetria */

  /* empuje comprometido: borde a la vista con el rival pegado de frente */
  bool     commit_active;    /* ventana abierta                          */
  uint32_t t_commit_ms;      /* instante en que se abrio                 */
  uint32_t push_commits;     /* ventanas abiertas, telemetria            */
} sumo_strategy_t;

void        strategy_init(sumo_strategy_t *st, const sumo_params_t *p);
void        strategy_step(sumo_strategy_t *st, const sumo_sensors_t *s, sumo_actuators_t *a);
const char *strategy_state_name(sumo_state_t s);
const char *strategy_version(void);

#endif /* SUMO_STRATEGY_H */
