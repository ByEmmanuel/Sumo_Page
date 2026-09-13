/* ==========================================================================
 *  strategy.c  --  Cerebro de Gelatina Nuclear
 *  ------------------------------------------------------------------------
 *  Maquina de estados reactiva sobre la linea base v0.1.0, con dos ideas:
 *    - v0.2.0 EMPUJE COMPROMETIDO: si el rival esta pegado de frente, el
 *      borde que ven los sensores de linea es suyo, no nuestro, y se sigue
 *      empujando en vez de huir.
 *    - v0.3.0 EMPUJE ALINEADO: en ATTACK se corrige el rumbo con firmeza
 *      para que el rival no se escurra del centro de la pala.
 *  Sin modelo del ring, sin aprendizaje.
 *
 *  Prioridades, de mayor a menor:
 *     1. No caerse del ring      -> ST_EDGE_ESCAPE
 *        ...salvo rival pegado de frente: empuje comprometido -> ST_ATTACK
 *     2. Empujar si lo tengo     -> ST_ATTACK
 *     3. Acercarme si lo veo     -> ST_TRACK
 *     4. Encontrarlo             -> ST_SEARCH / ST_OPENING
 *
 *  Este fichero NO incluye cabeceras de Webots ni de ningun microcontrolador.
 * ========================================================================== */

#include "strategy.h"

#include <math.h>
#include <string.h>

#define STRATEGY_VERSION_STR "v0.3.0"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* Angulo de montaje real de los cinco sensores frontales. */
const int16_t SUMO_DIST_ANGLE_CDEG[SUMO_N_DIST] = {
  6000, 3000, 0, -3000, -6000
};

static const char *const STATE_NAMES[ST_COUNT] = {
  "WAIT", "OPENING", "SEARCH", "TRACK", "ATTACK", "EDGE_ESCAPE"
};


/* ==========================================================================
 *  Utilidades numericas
 * ========================================================================== */

static float clampf(float v, float lo, float hi)
{
  return v < lo ? lo : (v > hi ? hi : v);
}

static float slew(float prev, float target, float max_step)
{
  const float d = target - prev;
  if (d >  max_step) return prev + max_step;
  if (d < -max_step) return prev - max_step;
  return target;
}

static uint32_t in_state_ms(const sumo_strategy_t *st)
{
  return st->t_ms - st->t_state_ms;
}

static void enter(sumo_strategy_t *st, sumo_state_t s)
{
  if (st->state == s) return;
  st->state = s;
  st->t_state_ms = st->t_ms;
}


/* ==========================================================================
 *  Percepcion: de lecturas crudas a "donde esta el rival"
 * ==========================================================================
 *  El rumbo se estima como centroide ponderado de los sensores que ven algo:
 *  cuanto mas cerca esta una lectura, mas pesa su angulo de montaje. Con cinco
 *  sensores esto da una resolucion angular muy superior a "cual se dispara",
 *  y sale gratis en computo (cinco multiplicaciones).
 * ========================================================================== */

static void perceive(sumo_strategy_t *st, const sumo_sensors_t *s)
{
  const sumo_params_t *p = &st->p;
  sumo_percept_t *per = &st->per;

  uint32_t w_sum = 0;
  int32_t  w_ang = 0;
  uint16_t nearest = SUMO_DIST_NONE;

  for (int i = 0; i < SUMO_N_DIST; ++i) {
    const uint16_t d = s->dist_mm[i];
    if (d == SUMO_DIST_NONE || d > p->dist_valid_max_mm) continue;

    /* peso lineal inverso: 1 en la cara del robot, 0 al limite util */
    const uint32_t w = (uint32_t)(p->dist_valid_max_mm - d) + 1u;
    w_sum += w;
    w_ang += (int32_t)w * (int32_t)SUMO_DIST_ANGLE_CDEG[i];
    if (d < nearest) nearest = d;
  }

  if (w_sum > 0u) {
    per->target_seen         = true;
    per->target_dist_mm      = nearest;
    per->target_bearing_cdeg = (int16_t)(w_ang / (int32_t)w_sum);
    per->last_seen_ms        = s->t_ms;
  } else if (per->last_seen_ms != 0u &&
             (s->t_ms - per->last_seen_ms) < p->target_hold_ms) {
    /* histeresis: el rival no desaparece porque un sensor parpadee un ciclo */
    per->target_seen = true;
  } else {
    per->target_seen    = false;
    per->target_dist_mm = SUMO_DIST_NONE;
  }

  /* Contacto frontal: solo con la lectura de ESTE ciclo, nunca con la memoria
   * de histeresis. Creer que el rival sigue delante cuando ya se ha escurrido
   * a un lado es justo lo que tiraria al robot fuera empujando al vacio. */
  const int b = per->target_bearing_cdeg;
  per->contact_front = (w_sum > 0u) && nearest <= p->dist_contact_mm &&
                       (b < 0 ? -b : b) <= (int)p->contact_cone_cdeg;

  per->line_mask = 0u;
  for (int i = 0; i < SUMO_N_LINE; ++i)
    if (s->line[i]) per->line_mask |= (uint8_t)(1u << i);
}


/* ==========================================================================
 *  Escape de borde
 * ==========================================================================
 *  La regla mas cara de romper del sumo: el que toca el blanco primero pierde.
 *  Por eso este bloque interrumpe cualquier otro estado, incluso un empuje
 *  ganador. La direccion de huida se deduce de QUE esquinas vieron blanco.
 * ========================================================================== */

static void plan_escape(sumo_strategy_t *st)
{
  const uint8_t m = st->per.line_mask;
  const bool front = (m & SUMO_LINE_FRONT_MASK) != 0u;
  const bool rear  = (m & SUMO_LINE_REAR_MASK)  != 0u;
  const bool left  = (m & SUMO_LINE_LEFT_MASK)  != 0u;
  const bool right = (m & SUMO_LINE_RIGHT_MASK) != 0u;

  if (rear && !front)      st->esc_drive = +1.0f;  /* borde detras: tirar hacia delante */
  else                     st->esc_drive = -1.0f;  /* borde delante o rodeado: atras    */

  if (left && !right)      st->esc_turn = -1.0f;   /* blanco a babor  -> huir a estribor */
  else if (right && !left) st->esc_turn = +1.0f;   /* blanco a estribor -> huir a babor  */
  else                     st->esc_turn = (st->edge_events & 1u) ? +1.0f : -1.0f;

  st->esc_phase = 0u;
  st->edge_events++;
  enter(st, ST_EDGE_ESCAPE);
  st->t_state_ms = st->t_ms;   /* reinicia el cronometro aunque ya estuviera aqui */
}


/* ==========================================================================
 *  Mezclador: (avance, giro) -> consignas de rueda, con rampa y zona muerta
 * ========================================================================== */

static void drive(sumo_strategy_t *st, float fwd, float turn, sumo_actuators_t *a)
{
  const float max_step = st->p.slew_per_s * ((float)st->p.dt_ms / 1000.0f);

  float l = clampf(fwd - turn, -1.0f, 1.0f);
  float r = clampf(fwd + turn, -1.0f, 1.0f);

  l = slew(st->prev_left,  l, max_step);
  r = slew(st->prev_right, r, max_step);

  st->prev_left  = l;
  st->prev_right = r;

  if (fabsf(l) < st->p.deadband) l = 0.0f;
  if (fabsf(r) < st->p.deadband) r = 0.0f;

  a->left  = l;
  a->right = r;
  a->led   = (uint8_t)st->state;
}


/* ==========================================================================
 *  API publica
 * ========================================================================== */

void strategy_init(sumo_strategy_t *st, const sumo_params_t *p)
{
  memset(st, 0, sizeof(*st));
  st->p = p ? *p : sumo_params_default();
  st->state = ST_WAIT;
  st->per.target_dist_mm = SUMO_DIST_NONE;
}


void strategy_step(sumo_strategy_t *st, const sumo_sensors_t *s, sumo_actuators_t *a)
{
  st->t_ms = s->t_ms;
  perceive(st, s);

  /* --- 0. Sin permiso de arranque: quieto y con el lazo reiniciado ------- */
  if (!s->armed) {
    enter(st, ST_WAIT);
    st->prev_left = st->prev_right = 0.0f;
    a->left = a->right = 0.0f;
    a->led  = (uint8_t)ST_WAIT;
    return;
  }
  if (st->state == ST_WAIT) {
    enter(st, ST_OPENING);
    st->t_state_ms = st->t_ms;
  }

  const sumo_params_t *p = &st->p;

  /* --- 1. Prioridad absoluta: el borde... salvo empuje comprometido ----- *
   * Con el rival pegado de frente, la linea bajo los sensores frontales es  *
   * la pala del rival metida debajo o el borde hacia el que lo empujamos:   *
   * en ambos casos huir es regalarle el asalto. Si es la linea trasera, nos *
   * esta empujando, y el escape (avanzar a v_escape y girar en el sitio)    *
   * solo empuja menos. La ventana dura push_commit_ms desde que aparece la  *
   * linea y se cierra al perder el contacto: sin rival delante, el borde    *
   * vuelve a mandar en el mismo ciclo.                                      */
  const bool lockout = (st->t_ms < st->t_edge_clear_ms);
  const bool linea   = (st->per.line_mask != 0u);
  if (!linea) st->commit_active = false;

  bool comprometido = false;
  if (linea && st->per.contact_front) {
    if (!st->commit_active) {
      st->commit_active = true;
      st->t_commit_ms = st->t_ms;
      st->push_commits++;
    }
    comprometido = (st->t_ms - st->t_commit_ms) < p->push_commit_ms;
  }

  if (comprometido)
    enter(st, ST_ATTACK);
  else if (linea && !lockout && st->state != ST_EDGE_ESCAPE)
    plan_escape(st);
  const float bearing_rad =
      (float)st->per.target_bearing_cdeg / 100.0f * (float)(M_PI / 180.0);

  switch (st->state) {

  /* ---------------------------------------------------------------- */
  case ST_EDGE_ESCAPE: {
    if (st->esc_phase == 0u) {
      /* fase 1: despegarse del borde en linea casi recta */
      drive(st, st->esc_drive * p->v_escape, st->esc_turn * 0.15f, a);
      if (in_state_ms(st) >= p->escape_back_ms) {
        st->esc_phase = 1u;
        st->t_state_ms = st->t_ms;
      }
    } else {
      /* fase 2: reencuadrar hacia el centro del ring */
      drive(st, 0.0f, st->esc_turn * p->v_escape, a);
      if (in_state_ms(st) >= p->escape_turn_ms) {
        st->t_edge_clear_ms = st->t_ms + p->escape_lockout_ms;
        enter(st, ST_SEARCH);
        st->search_probing = false;
      }
    }
    break;
  }

  /* ---------------------------------------------------------------- */
  case ST_OPENING: {
    float fwd = p->v_opening, turn = 0.0f;
    switch (p->opening) {
      case OPENING_CHARGE: turn = 0.0f;  break;
      case OPENING_ARC_L:  turn = 0.45f; break;
      case OPENING_ARC_R:  turn = -0.45f; break;
      case OPENING_SCAN:   fwd = 0.10f; turn = 0.70f; break;
    }
    drive(st, fwd, turn, a);

    /* si aparece el rival, la apertura se abandona al instante */
    if (st->per.target_seen && st->per.target_dist_mm <= p->dist_track_mm)
      enter(st, ST_TRACK);
    else if (in_state_ms(st) >= p->opening_ms)
      enter(st, ST_SEARCH);
    break;
  }

  /* ---------------------------------------------------------------- */
  case ST_SEARCH: {
    if (st->per.target_seen) { enter(st, ST_TRACK); break; }

    /* gira hacia el lado donde se vio al rival por ultima vez */
    const float dir = (st->per.target_bearing_cdeg >= 0) ? 1.0f : -1.0f;

    if (st->search_probing) {
      drive(st, p->v_search, 0.0f, a);
      if (in_state_ms(st) >= p->search_probe_ms) {
        st->search_probing = false;
        st->t_state_ms = st->t_ms;
      }
    } else {
      const float fwd = p->v_search * (1.0f + p->search_turn_ratio);
      drive(st, fwd, dir * p->v_search, a);
      if (in_state_ms(st) >= p->search_spin_ms) {
        st->search_probing = true;
        st->t_state_ms = st->t_ms;
      }
    }
    break;
  }

  /* ---------------------------------------------------------------- */
  case ST_TRACK: {
    if (!st->per.target_seen) {
      enter(st, ST_SEARCH);
      st->search_probing = false;
      break;
    }
    if (st->per.target_dist_mm <= p->dist_attack_mm) { enter(st, ST_ATTACK); break; }

    const float turn = clampf(p->track_kp * bearing_rad,
                              -p->track_max_diff, p->track_max_diff);
    drive(st, p->v_track, turn, a);
    break;
  }

  /* ---------------------------------------------------------------- */
  case ST_ATTACK: {
    if (!st->per.target_seen) {
      enter(st, ST_SEARCH);
      st->search_probing = false;
      break;
    }
    if (st->per.target_dist_mm > p->dist_track_mm) { enter(st, ST_TRACK); break; }

    /* En contacto hay que corregir con firmeza: si el rival se escurre del
     * centro de la pala, la linea de empuje se tuerce y gana el que esta
     * mejor alineado. Hasta v0.2.0 (0.35 y +-0.30, numeros magicos aqui) el
     * charger, que gira hasta +-0.55, nos ganaba la alineacion. */
    const float turn = clampf(p->track_kp * bearing_rad * p->attack_kp_scale,
                              -p->attack_max_diff, p->attack_max_diff);
    drive(st, p->v_attack, turn, a);
    break;
  }

  /* ---------------------------------------------------------------- */
  case ST_WAIT:
  default:
    drive(st, 0.0f, 0.0f, a);
    break;
  }
}


const char *strategy_state_name(sumo_state_t s)
{
  return (s >= 0 && s < ST_COUNT) ? STATE_NAMES[s] : "?";
}

const char *strategy_version(void)
{
  return STRATEGY_VERSION_STR;
}
