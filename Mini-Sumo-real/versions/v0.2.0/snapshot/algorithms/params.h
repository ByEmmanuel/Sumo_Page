/* ==========================================================================
 *  params.h  --  Todos los numeros sintonizables del robot, en un solo sitio
 *
 *  Por que un fichero aparte: en la bitacora de versiones, una iteracion de
 *  tipo "tuning" debe producir un diff de tres lineas legible de un vistazo.
 *  Si los numeros magicos viven dentro de strategy.c, el diff se vuelve ruido
 *  y se pierde el objetivo del proyecto: entender QUE toco la IA y POR QUE.
 *
 *  Regla de la bitacora: cambiar un numero de aqui = version "tuning" (patch).
 *  Anadir un campo nuevo = version "new-behavior" (minor).
 * ========================================================================== */
#ifndef SUMO_PARAMS_H
#define SUMO_PARAMS_H

#include <stdint.h>
#include "sumo_types.h"

/* Aperturas de partida. El primer segundo decide muchos combates. */
typedef enum {
  OPENING_CHARGE = 0,   /* embestida recta inmediata                        */
  OPENING_ARC_L  = 1,   /* arco a babor buscando el flanco del rival        */
  OPENING_ARC_R  = 2,   /* arco a estribor                                  */
  OPENING_SCAN   = 3    /* giro en el sitio hasta enganchar y luego atacar   */
} sumo_opening_t;

typedef struct {
  /* ---- periodo de control ------------------------------------------- */
  uint16_t dt_ms;                 /* periodo del lazo, ms                  */

  /* ---- percepcion ---------------------------------------------------- */
  uint16_t dist_valid_max_mm;     /* por encima, se ignora la lectura      */
  uint16_t dist_attack_mm;        /* rival "enganchado": empuje a fondo    */
  uint16_t dist_track_mm;         /* rival a la vista: persecucion         */
  uint16_t target_hold_ms;        /* histeresis: sigo creyendo que esta ahi*/

  /* ---- velocidades normalizadas [0..1] ------------------------------- */
  float v_attack;
  float v_track;
  float v_search;
  float v_escape;
  float v_opening;

  /* ---- seguimiento --------------------------------------------------- */
  float track_kp;                 /* rad^-1, error de rumbo -> diferencial */
  float track_max_diff;           /* tope del termino diferencial          */

  /* ---- escape de borde (maxima prioridad) ----------------------------- */
  uint16_t escape_back_ms;        /* retroceso tras ver linea frontal      */
  uint16_t escape_turn_ms;        /* giro de reencuadre                    */
  uint16_t escape_lockout_ms;     /* ventana ciega para no reentrar al borde*/

  /* ---- empuje comprometido -------------------------------------------- */
  uint16_t dist_contact_mm;       /* rival a esta distancia o menos: pegado */
  uint16_t contact_cone_cdeg;     /* ... y dentro de este cono frontal (+-) */
  uint16_t push_commit_ms;        /* max. empujando con el borde a la vista */

  /* ---- busqueda ------------------------------------------------------- */
  uint16_t search_spin_ms;        /* giro en el sitio                      */
  uint16_t search_probe_ms;       /* avance corto entre giros              */
  float    search_turn_ratio;     /* -1 = sobre si mismo, 0 = recto        */

  /* ---- apertura -------------------------------------------------------- */
  sumo_opening_t opening;
  uint16_t       opening_ms;      /* duracion de la apertura               */

  /* ---- proteccion del tren motriz -------------------------------------- */
  float slew_per_s;               /* cambio maximo de consigna por segundo */
  float deadband;                 /* consignas por debajo -> 0             */
} sumo_params_t;


static inline sumo_params_t sumo_params_default(void)
{
  sumo_params_t p;

  p.dt_ms               = 8;

  p.dist_valid_max_mm   = 800;
  p.dist_attack_mm      = 260;
  p.dist_track_mm       = 700;
  p.target_hold_ms      = 260;

  p.v_attack            = 1.00f;
  p.v_track             = 0.72f;
  p.v_search            = 0.55f;
  p.v_escape            = 0.85f;
  p.v_opening           = 0.80f;

  p.track_kp            = 1.10f;
  p.track_max_diff      = 0.85f;

  p.escape_back_ms      = 300;
  p.escape_turn_ms      = 360;
  p.escape_lockout_ms   = 140;

  p.dist_contact_mm     = 60;
  p.contact_cone_cdeg   = 2500;
  p.push_commit_ms      = 600;

  p.search_spin_ms      = 520;
  p.search_probe_ms     = 300;
  p.search_turn_ratio   = -0.85f;

  p.opening             = OPENING_CHARGE;
  p.opening_ms          = 420;

  p.slew_per_s          = 25.0f;
  p.deadband            = 0.04f;

  return p;
}

#endif /* SUMO_PARAMS_H */
