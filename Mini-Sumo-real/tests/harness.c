/* ==========================================================================
 *  harness.c  --  Banco de pruebas nativo (ring de sumo sin Webots)
 *
 *  Simulador cinematico 2D minimo del dohyo reglamentario. No sustituye a
 *  Webots (no hay dinamica de contacto ni friccion real), pero corre 50
 *  asaltos en milisegundos y permite medir CADA version del algoritmo al
 *  instante. Webots queda como juez final; esto es el sparring diario.
 *
 *  Compilar:  make -C tests
 *  Ejecutar:  ./tests/build/harness --rounds 50 --opponent charger \
 *                                   --out runs/v0.1.0/results.json
 * ========================================================================== */

#include "../algorithms/strategy.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* ---- geometria del dohyo mini-sumo ------------------------------------- */
#define RING_R        0.385f   /* radio del dohyo                          */
#define RING_LINE_R   0.360f   /* radio interior de la banda blanca        */
#define BODY_R        0.055f   /* radio equivalente del robot (10x10 cm)   */
#define CORNER_OFF    0.045f   /* offset de los sensores de linea          */
#define SENSOR_OFF    0.035f   /* los sensores de distancia miran desde aqui*/
#define V_MAX         1.20f    /* m/s a consigna 1.0                       */
#define DT_S          0.008f   /* 8 ms                                     */
#define MATCH_MAX_S   30.0f    /* limite de asalto en el modo banco         */
#define ARM_DELAY_S   0.20f    /* retardo de arranque del harness          */

/* ---- modo reglamento (Extras/Reglamento de MINISUMO II, p. 8-13) --------
 * Colocacion en la cruz central a 5 cm cara con cara: 1a ronda de frente,
 * 2a de lado en sentidos opuestos, 3a de espaldas. Tres rondas en tres
 * minutos: 60 s por ronda como tope. Es opcional (--reglamento) para que las
 * metricas del modo de siempre sigan siendo comparables entre versiones.   */
#define REG_MAX_S     60.0f
#define REG_CENTROS   0.150f   /* 10 cm de robot + 5 cm de separacion       */

typedef enum { COL_BANCO = 0, COL_FRENTE, COL_LADO, COL_ESPALDA } colocacion_t;
static const char *COL_NAME[] = { "banco", "frente", "lado", "espalda" };
static bool  g_reglamento = false;
static float g_max_s = MATCH_MAX_S;

typedef enum { OPP_STATIC, OPP_CHARGER, OPP_SPINNER, OPP_MIRROR } opp_kind_t;

typedef struct {
  float x, y, th;
  float cl, cr;          /* consignas aplicadas */
  sumo_strategy_t brain; /* usado por GELATINA y por OPP_MIRROR */
  int   scripted_phase;
  float scripted_t;
} bot_t;

/* ---- PRNG reproducible (xorshift32) ------------------------------------ */
static uint32_t rng_state = 1u;
static float frand(void)
{
  rng_state ^= rng_state << 13; rng_state ^= rng_state >> 17; rng_state ^= rng_state << 5;
  return (float)(rng_state & 0xFFFFFFu) / (float)0x1000000u;
}
static float frand_sym(float a) { return (frand() * 2.0f - 1.0f) * a; }


/* ==========================================================================
 *  Simulacion de sensores
 * ========================================================================== */

/* Interseccion rayo-circulo. Devuelve la distancia o -1 si no hay impacto. */
static float ray_circle(float ox, float oy, float dx, float dy,
                        float cx, float cy, float r)
{
  const float mx = ox - cx, my = oy - cy;
  const float b = mx * dx + my * dy;
  const float c = mx * mx + my * my - r * r;
  if (c > 0.0f && b > 0.0f) return -1.0f;
  const float disc = b * b - c;
  if (disc < 0.0f) return -1.0f;
  float t = -b - sqrtf(disc);
  if (t < 0.0f) t = 0.0f;
  return t;
}

static void sense(const bot_t *me, const bot_t *foe, uint32_t t_ms,
                  bool armed, sumo_sensors_t *s)
{
  memset(s, 0, sizeof(*s));
  s->t_ms  = t_ms;
  s->armed = armed;
  s->yaw_rad = me->th;

  for (int i = 0; i < SUMO_N_DIST; ++i) {
    const float a  = me->th + (float)SUMO_DIST_ANGLE_CDEG[i] / 100.0f * (float)(M_PI / 180.0);
    const float dx = cosf(a), dy = sinf(a);
    const float ox = me->x + SENSOR_OFF * dx, oy = me->y + SENSOR_OFF * dy;
    const float t  = ray_circle(ox, oy, dx, dy, foe->x, foe->y, BODY_R);
    if (t < 0.0f || t > 1.2f) {
      s->dist_mm[i] = SUMO_DIST_NONE;
    } else {
      float mm = t * 1000.0f + frand_sym(6.0f);      /* +-6 mm de ruido */
      if (mm < 0.0f) mm = 0.0f;
      s->dist_mm[i] = (uint16_t)mm;
    }
  }

  static const float cx[SUMO_N_LINE] = { +CORNER_OFF, +CORNER_OFF, -CORNER_OFF, -CORNER_OFF };
  static const float cy[SUMO_N_LINE] = { +CORNER_OFF, -CORNER_OFF, +CORNER_OFF, -CORNER_OFF };
  const float ct = cosf(me->th), st = sinf(me->th);
  for (int i = 0; i < SUMO_N_LINE; ++i) {
    const float wx = me->x + cx[i] * ct - cy[i] * st;
    const float wy = me->y + cx[i] * st + cy[i] * ct;
    s->line[i] = (sqrtf(wx * wx + wy * wy) >= RING_LINE_R);
  }
}


/* ==========================================================================
 *  Rivales de referencia
 * ========================================================================== */

static void opponent_act(bot_t *b, const sumo_sensors_t *s, opp_kind_t kind,
                         sumo_actuators_t *a)
{
  a->led = 0;
  if (!s->armed) { a->left = a->right = 0.0f; return; }

  const bool line_front = s->line[LINE_FL] || s->line[LINE_FR];
  const bool line_rear  = s->line[LINE_RL] || s->line[LINE_RR];

  switch (kind) {
  case OPP_STATIC:
    a->left = a->right = 0.0f;
    break;

  case OPP_SPINNER:
    if (line_front || line_rear) { a->left = -0.6f; a->right = -0.6f; }
    else                         { a->left = -0.5f; a->right = 0.5f; }
    break;

  case OPP_CHARGER:
  default: {
    /* retrocede si ve linea delante, si no embiste hacia el contacto mas cercano */
    if (line_front) { b->scripted_phase = 1; b->scripted_t = 0.0f; }
    if (b->scripted_phase == 1) {
      b->scripted_t += DT_S;
      a->left  = (b->scripted_t < 0.30f) ? -0.8f : -0.6f;
      a->right = (b->scripted_t < 0.30f) ? -0.8f :  0.6f;
      if (b->scripted_t > 0.70f) b->scripted_phase = 0;
      break;
    }
    if (line_rear) { a->left = 0.9f; a->right = 0.9f; break; }

    uint16_t best = SUMO_DIST_NONE; int bi = -1;
    for (int i = 0; i < SUMO_N_DIST; ++i)
      if (s->dist_mm[i] != SUMO_DIST_NONE && s->dist_mm[i] < best) { best = s->dist_mm[i]; bi = i; }

    if (bi < 0) { a->left = -0.45f; a->right = 0.45f; }          /* buscar girando */
    else {
      const float turn = (float)SUMO_DIST_ANGLE_CDEG[bi] / 6000.0f * 0.55f;
      a->left  = 0.95f - turn;
      a->right = 0.95f + turn;
    }
    break;
  }
  }
}


/* ==========================================================================
 *  Integracion del movimiento y resolucion de empuje
 * ========================================================================== */

static void integrate(bot_t *b, float cl, float cr)
{
  b->cl = cl; b->cr = cr;
  const float vl = cl * V_MAX, vr = cr * V_MAX;
  const float v  = 0.5f * (vl + vr);
  const float w  = (vr - vl) / SUMO_TRACK_M;
  b->th += w * DT_S;
  b->x  += v * cosf(b->th) * DT_S;
  b->y  += v * sinf(b->th) * DT_S;
}

/* Empuje: quien tiene mas empuje alineado con la normal de contacto gana. */
static void resolve_push(bot_t *a, bot_t *b)
{
  float dx = b->x - a->x, dy = b->y - a->y;
  float d = sqrtf(dx * dx + dy * dy);
  if (d >= 2.0f * BODY_R) return;
  if (d < 1e-5f) { dx = 1.0f; dy = 0.0f; d = 1e-5f; }
  const float nx = dx / d, ny = dy / d;
  const float pen = 2.0f * BODY_R - d;

  const float va = 0.5f * (a->cl + a->cr) * V_MAX;
  const float vb = 0.5f * (b->cl + b->cr) * V_MAX;
  float ta = va * (cosf(a->th) * nx + sinf(a->th) * ny);   /* A empuja hacia B */
  float tb = vb * (cosf(b->th) * -nx + sinf(b->th) * -ny); /* B empuja hacia A */
  if (ta < 0.0f) ta = 0.0f;
  if (tb < 0.0f) tb = 0.0f;

  const float tot = ta + tb + 0.02f;
  const float share_b = ta / tot;   /* fraccion de penetracion que absorbe B */
  const float share_a = tb / tot;
  const float rest = 1.0f - share_a - share_b;

  b->x += nx * pen * (share_b + rest * 0.5f);
  b->y += ny * pen * (share_b + rest * 0.5f);
  a->x -= nx * pen * (share_a + rest * 0.5f);
  a->y -= ny * pen * (share_a + rest * 0.5f);
}

static bool out_of_ring(const bot_t *b)
{
  return sqrtf(b->x * b->x + b->y * b->y) > (RING_R + BODY_R * 0.35f);
}


/* ==========================================================================
 *  Un asalto
 * ========================================================================== */

typedef struct { int result; float t_s; const char *reason; colocacion_t col; } round_res_t;
/* result: +1 gana Gelatina, -1 pierde, 0 empate */

static round_res_t play_round(opp_kind_t kind, const sumo_params_t *params, int idx)
{
  bot_t me = (bot_t){0}, foe = (bot_t){0};
  strategy_init(&me.brain, params);
  if (kind == OPP_MIRROR) {
    sumo_params_t mp = sumo_params_default();
    strategy_init(&foe.brain, &mp);
  }

  const colocacion_t col = g_reglamento ? (colocacion_t)(1 + idx % 3) : COL_BANCO;
  if (col == COL_BANCO) {
    /* Modo banco: en diagonal a 36 cm, mirandose, con jitter por asalto */
    const float base = (idx % 2 == 0) ? 0.0f : (float)(M_PI / 2.0);
    const float r0 = 0.18f + frand_sym(0.02f);
    me.x  =  r0 * cosf(base);              me.y  =  r0 * sinf(base);
    foe.x = -r0 * cosf(base);              foe.y = -r0 * sinf(base);
    me.th  = base + (float)M_PI + frand_sym(0.25f);
    foe.th = base + frand_sym(0.25f);
  } else {
    /* Reglamento: centros a 15 cm sobre un eje de la cruz. La orientacion
     * global es libre (el dohyo es simetrico) y la mano que coloca tiene
     * +-3 mm y +-3 grados de error. */
    const float phi = frand() * 2.0f * (float)M_PI;
    const float h = 0.5f * REG_CENTROS;
    float ax = cosf(phi), ay = sinf(phi);
    if (col == COL_LADO) { const float t = ax; ax = -ay; ay = t; }
    me.x  =  h * ax + frand_sym(0.003f);   me.y  =  h * ay + frand_sym(0.003f);
    foe.x = -h * ax + frand_sym(0.003f);   foe.y = -h * ay + frand_sym(0.003f);
    if (col == COL_FRENTE) { me.th = phi + (float)M_PI; foe.th = phi; }   /* se miran        */
    else                   { me.th = phi; foe.th = phi + (float)M_PI; }   /* lado y espaldas */
    me.th  += frand_sym(0.05f);
    foe.th += frand_sym(0.05f);
  }

  const int steps = (int)(g_max_s / DT_S);
  const int arm_step = (int)(ARM_DELAY_S / DT_S);
  float last_contact_s = -99.0f;   /* para separar expulsion de auto-salida */

  for (int k = 0; k < steps; ++k) {
    const uint32_t t_ms = (uint32_t)(k * 8);
    const bool armed = (k >= arm_step);

    sumo_sensors_t s_me, s_foe;
    sumo_actuators_t a_me = {0}, a_foe = {0};

    sense(&me,  &foe, t_ms, armed, &s_me);
    sense(&foe, &me,  t_ms, armed, &s_foe);

    strategy_step(&me.brain, &s_me, &a_me);
    if (kind == OPP_MIRROR) strategy_step(&foe.brain, &s_foe, &a_foe);
    else                    opponent_act(&foe, &s_foe, kind, &a_foe);

    integrate(&me,  a_me.left,  a_me.right);
    integrate(&foe, a_foe.left, a_foe.right);
    resolve_push(&me, &foe);

    const float t_s = (float)(k - arm_step) * DT_S;
    {
      const float sx = foe.x - me.x, sy = foe.y - me.y;
      if (sqrtf(sx * sx + sy * sy) < 2.0f * BODY_R + 0.012f) last_contact_s = t_s;
    }

    const bool me_out = out_of_ring(&me), foe_out = out_of_ring(&foe);
    if (me_out && foe_out) return (round_res_t){ 0, t_s, "doble salida", col };
    if (foe_out)           return (round_res_t){ +1, t_s, "rival fuera", col };
    if (me_out) {
      /* Perder empujado es una derrota tactica; perder solo es un fallo del
       * escape de borde. Distinguirlo es lo que hace util la metrica. */
      const bool empujado = (t_s - last_contact_s) < 0.40f;
      return (round_res_t){ -1, t_s, empujado ? "expulsado" : "auto-salida", col };
    }
  }
  return (round_res_t){ 0, g_max_s, "tiempo agotado", col };
}


/* Probabilidad de ganar el combate a 3 rondas (reglamento p. 8 y 13) a partir
 * de las probabilidades por ronda de cada colocacion (frente, lado, espalda).
 * Gana quien llega a dos Yuko; al acabar las tres, quien tenga mas; con
 * igualdad, ronda extra de frente y, si tambien es empate, deciden los jueces. */
static void match_prob(const double pw[3], const double pd[3], const double pl[3],
                       double *win, double *judges, double *loss)
{
  double P[3][3] = {{0.0}};
  double W = 0.0, L = 0.0, D = 0.0;
  P[0][0] = 1.0;
  for (int r = 0; r < 3; ++r) {
    double Q[3][3] = {{0.0}};
    for (int i = 0; i < 2; ++i)
      for (int j = 0; j < 2; ++j) {
        const double p = P[i][j];
        Q[i + 1][j] += p * pw[r];
        Q[i][j]     += p * pd[r];
        Q[i][j + 1] += p * pl[r];
      }
    for (int j = 0; j < 2; ++j) { W += Q[2][j]; Q[2][j] = 0.0; }
    for (int i = 0; i < 2; ++i) { L += Q[i][2]; Q[i][2] = 0.0; }
    memcpy(P, Q, sizeof P);
  }
  for (int i = 0; i < 2; ++i)
    for (int j = 0; j < 2; ++j) {
      const double p = P[i][j];
      if (i > j)      W += p;
      else if (j > i) L += p;
      else { W += p * pw[0]; L += p * pl[0]; D += p * pd[0]; }
    }
  *win = W; *judges = D; *loss = L;
}


/* ========================================================================== */

static const char *KIND_NAME[] = { "static", "charger", "spinner", "mirror" };

int main(int argc, char **argv)
{
  int rounds = 50;
  opp_kind_t kind = OPP_CHARGER;
  const char *out = NULL;
  const char *ver = "WORK";
  bool all = false;
  float max_s = -1.0f;
  rng_state = 12345u;

  for (int i = 1; i < argc; ++i) {
    if (!strcmp(argv[i], "--rounds")   && i + 1 < argc) rounds = atoi(argv[++i]);
    else if (!strcmp(argv[i], "--seed") && i + 1 < argc) rng_state = (uint32_t)atoi(argv[++i]) | 1u;
    else if (!strcmp(argv[i], "--out")  && i + 1 < argc) out = argv[++i];
    else if (!strcmp(argv[i], "--version") && i + 1 < argc) ver = argv[++i];
    else if (!strcmp(argv[i], "--all")) all = true;
    else if (!strcmp(argv[i], "--reglamento")) { g_reglamento = true; g_max_s = REG_MAX_S; }
    else if (!strcmp(argv[i], "--max-s") && i + 1 < argc) max_s = (float)atof(argv[++i]);
    else if (!strcmp(argv[i], "--opponent") && i + 1 < argc) {
      const char *k = argv[++i];
      for (int j = 0; j < 4; ++j) if (!strcmp(k, KIND_NAME[j])) kind = (opp_kind_t)j;
    }
  }

  if (max_s > 0.0f) g_max_s = max_s;

  const sumo_params_t params = sumo_params_default();
  const int k0 = all ? 0 : (int)kind;
  const int k1 = all ? 3 : (int)kind;

  int tw = 0, tl = 0, td = 0, tself = 0, tr = 0;
  float twin_t = 0.0f;
  char per_opp[8192]; size_t po = 0;
  per_opp[0] = '\0';
  double match_sum = 0.0; int n_match = 0;

  printf("\n  Gelatina Nuclear -- banco nativo   estrategia %s   modo %s (%.0f s)\n",
         strategy_version(), g_reglamento ? "reglamento" : "banco", (double)g_max_s);
  printf("  %-9s %6s %6s %6s %8s %10s\n", "RIVAL", "W", "L", "D", "win%", "t_med(s)");
  printf("  ------------------------------------------------------------\n");

  for (int kk = k0; kk <= k1; ++kk) {
    int w = 0, l = 0, d = 0, so = 0; float wt = 0.0f;
    int cw[4] = {0}, cl[4] = {0}, cd[4] = {0};   /* por colocacion */
    for (int i = 0; i < rounds; ++i) {
      const round_res_t r = play_round((opp_kind_t)kk, &params, i);
      if (r.result > 0)      { w++; wt += r.t_s; cw[r.col]++; }
      else if (r.result < 0) { l++; cl[r.col]++; if (!strcmp(r.reason, "auto-salida")) so++; }
      else                   { d++; cd[r.col]++; }
    }
    const float wr = (float)w / (float)rounds;
    printf("  %-9s %6d %6d %6d %7.1f%% %10.2f\n", KIND_NAME[kk], w, l, d,
           wr * 100.0f, w ? wt / (float)w : 0.0f);
    po += (size_t)snprintf(per_opp + po, sizeof(per_opp) - po,
                           "%s{\"name\":\"%s\",\"rounds\":%d,\"wins\":%d,\"losses\":%d,"
                           "\"draws\":%d,\"win_rate\":%.3f",
                           po ? "," : "", KIND_NAME[kk], rounds, w, l, d, (double)wr);
    if (g_reglamento) {
      double pw[3], pd[3], pl[3], mw, mj, ml;
      po += (size_t)snprintf(per_opp + po, sizeof(per_opp) - po, ",\"placements\":[");
      for (int c = COL_FRENTE; c <= COL_ESPALDA; ++c) {
        const int n = cw[c] + cl[c] + cd[c];
        pw[c - 1] = n ? (double)cw[c] / n : 0.0;
        pd[c - 1] = n ? (double)cd[c] / n : 1.0;
        pl[c - 1] = n ? (double)cl[c] / n : 0.0;
        printf("    %-8s %6d %6d %6d %7.1f%%\n", COL_NAME[c], cw[c], cl[c], cd[c], 100.0 * pw[c - 1]);
        po += (size_t)snprintf(per_opp + po, sizeof(per_opp) - po,
                               "%s{\"name\":\"%s\",\"rounds\":%d,\"wins\":%d,\"losses\":%d,\"draws\":%d}",
                               c > COL_FRENTE ? "," : "", COL_NAME[c], n, cw[c], cl[c], cd[c]);
      }
      match_prob(pw, pd, pl, &mw, &mj, &ml);
      printf("    %-8s gana %5.1f%%  jueces %5.1f%%  pierde %5.1f%%\n", "combate",
             100.0 * mw, 100.0 * mj, 100.0 * ml);
      po += (size_t)snprintf(per_opp + po, sizeof(per_opp) - po,
                             "],\"match\":{\"win\":%.3f,\"judges\":%.3f,\"loss\":%.3f}", mw, mj, ml);
      match_sum += mw; n_match++;
    }
    po += (size_t)snprintf(per_opp + po, sizeof(per_opp) - po, "}");
    tw += w; tl += l; td += d; tself += so; tr += rounds; twin_t += wt;
  }

  const float total_wr = tr ? (float)tw / (float)tr : 0.0f;
  printf("  ------------------------------------------------------------\n");
  printf("  %-9s %6d %6d %6d %7.1f%% %10.2f\n\n", "TOTAL", tw, tl, td,
         total_wr * 100.0f, tw ? twin_t / (float)tw : 0.0f);

  if (out) {
    FILE *f = fopen(out, "w");
    if (!f) { fprintf(stderr, "no puedo escribir %s\n", out); return 1; }
    char extra[96] = "";
    if (n_match)
      snprintf(extra, sizeof extra, "    \"match_win_rate\": %.3f,\n", match_sum / n_match);
    fprintf(f,
      "{\n  \"version\": \"%s\",\n  \"engine\": \"harness-nativo\",\n"
      "  \"mode\": \"%s\",\n  \"round_max_s\": %.0f,\n"
      "  \"strategy_build\": \"%s\",\n  \"metrics\": {\n"
      "    \"rounds\": %d,\n    \"wins\": %d,\n    \"losses\": %d,\n    \"draws\": %d,\n"
      "    \"win_rate\": %.3f,\n    \"avg_win_time_s\": %.2f,\n    \"self_outs\": %d,\n%s"
      "    \"opponents\": [%s]\n  }\n}\n",
      ver, g_reglamento ? "reglamento" : "banco", (double)g_max_s,
      strategy_version(), tr, tw, tl, td, (double)total_wr,
      tw ? (double)(twin_t / (float)tw) : 0.0, tself, extra, per_opp);
    fclose(f);
    printf("  resultados -> %s\n\n", out);
  }
  return 0;
}
