/* ==========================================================================
 *  arbitro.c  --  Supervisor de combate (juez y estadistico)
 *
 *  Cierra el bucle de aprendizaje: coloca a los robots, da la senal de
 *  arranque, detecta la expulsion, repite N asaltos y escribe un JSON con el
 *  MISMO esquema que el banco nativo. Ese JSON entra en la bitacora con:
 *
 *      python3 tools/gnver.py metrics vX.Y.Z --from runs/webots_vX.Y.Z.json
 *
 *  Sin esto no hay metricas, y sin metricas una iteracion es una opinion.
 * ========================================================================== */

#include <webots/robot.h>
#include <webots/supervisor.h>
#include <webots/emitter.h>

#include <math.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "contact_real.h"

/* M_PI no lo garantiza C99 estricto; glibc lo oculta bajo -std=c99. */
#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define RING_R       0.385
#define OUT_MARGIN   0.030   /* centro del robot mas alla de esto = fuera   */
#define FALL_Z      -0.012   /* o directamente se ha caido del dohyo        */
#define CONTACT_D    0.125   /* centros a menos de esto = estan en contacto  */
#define SETTLE_MS      300.0
#define DEFAULT_TIMEOUT 60.0

/* Colocacion del reglamento (Extras/Reglamento de MINISUMO II, p. 10-11):
 * centros a 15 cm (10 cm de robot + 5 cm de separacion) sobre un eje de la
 * cruz central; ronda 1 de frente, 2 de lado en sentidos opuestos, 3 de
 * espaldas. Tres rondas en tres minutos: 60 s por ronda como tope.
 * Con --colocacion banco (por defecto) se usa la diagonal a 36 cm de siempre,
 * para que las metricas anteriores sigan siendo comparables. */
#define REG_CENTROS  0.150
#define REG_TIMEOUT  60.0
static const char *COL_NAME[] = { "banco", "frente", "lado", "espalda" };

typedef struct { WbNodeRef node; WbFieldRef tr, rot; } fighter_t;

static void place(const fighter_t *f, double x, double y, double yaw)
{
  const double t[3] = { x, y, 0.001 };
  const double r[4] = { 0.0, 0.0, 1.0, yaw };
  wb_supervisor_field_set_sf_vec3f(f->tr, t);
  wb_supervisor_field_set_sf_rotation(f->rot, r);
  wb_supervisor_node_reset_physics(f->node);
}

static bool is_out(const fighter_t *f)
{
  const double *p = wb_supervisor_node_get_position(f->node);
  const double rad = sqrt(p[0] * p[0] + p[1] * p[1]);
  return (rad > RING_R + OUT_MARGIN) || (p[2] < FALL_Z);
}

static void broadcast(WbDeviceTag tx, const char *msg)
{
  wb_emitter_send(tx, msg, (int)strlen(msg) + 1);
}

/* Probabilidad de ganar el combate a 3 rondas a partir de la de cada ronda
 * por colocacion. Misma cuenta que tests/harness.c y ml/sim.py. */
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
        Q[i + 1][j] += P[i][j] * pw[r];
        Q[i][j]     += P[i][j] * pd[r];
        Q[i][j + 1] += P[i][j] * pl[r];
      }
    for (int j = 0; j < 2; ++j) { W += Q[2][j]; Q[2][j] = 0.0; }
    for (int i = 0; i < 2; ++i) { L += Q[i][2]; Q[i][2] = 0.0; }
    memcpy(P, Q, sizeof P);
  }
  for (int i = 0; i < 2; ++i)
    for (int j = 0; j < 2; ++j) {
      if (i > j)      W += P[i][j];
      else if (j > i) L += P[i][j];
      else { W += P[i][j] * pw[0]; L += P[i][j] * pl[0]; D += P[i][j] * pd[0]; }
    }
  *win = W; *judges = D; *loss = L;
}

int main(int argc, char **argv)
{
  wb_robot_init();
  contact_init();
  const int step = (int)wb_robot_get_basic_time_step();

  int rounds = 20;
  double timeout = -1.0;
  bool reg = false;
  const char *out_path = "../../../runs/webots_ultimo.json";
  const char *version  = "WORK";
  const char *rival    = "charger";

  for (int i = 1; i < argc; ++i) {
    if      (!strcmp(argv[i], "--rounds")  && i + 1 < argc) rounds   = atoi(argv[++i]);
    else if (!strcmp(argv[i], "--timeout") && i + 1 < argc) timeout  = atof(argv[++i]);
    else if (!strcmp(argv[i], "--out")     && i + 1 < argc) out_path = argv[++i];
    else if (!strcmp(argv[i], "--version") && i + 1 < argc) version  = argv[++i];
    else if (!strcmp(argv[i], "--rival")   && i + 1 < argc) rival    = argv[++i];
    else if (!strcmp(argv[i], "--colocacion") && i + 1 < argc) reg = !strcmp(argv[++i], "reglamento");
  }
  if (timeout <= 0.0) timeout = reg ? REG_TIMEOUT : DEFAULT_TIMEOUT;

  fighter_t me = {0}, foe = {0};
  me.node  = wb_supervisor_node_get_from_def("GELATINA");
  foe.node = wb_supervisor_node_get_from_def("RIVAL");
  if (!me.node || !foe.node) {
    fprintf(stderr, "[arbitro] faltan los DEF GELATINA / RIVAL en el mundo\n");
    wb_robot_cleanup();
    return 1;
  }
  me.tr   = wb_supervisor_node_get_field(me.node,  "translation");
  me.rot  = wb_supervisor_node_get_field(me.node,  "rotation");
  foe.tr  = wb_supervisor_node_get_field(foe.node, "translation");
  foe.rot = wb_supervisor_node_get_field(foe.node, "rotation");

  WbDeviceTag tx = wb_robot_get_device("emisor");

  int wins = 0, losses = 0, draws = 0, self_outs = 0;
  int cw[4] = {0}, cl[4] = {0}, cd[4] = {0};   /* por colocacion */
  double win_time_sum = 0.0;

  printf("\n[arbitro] %d asaltos contra '%s', colocacion %s, limite %.0f s por asalto\n",
         rounds, rival, reg ? "reglamento" : "banco", timeout);
  fflush(stdout);

  for (int k = 0; k < rounds && wb_robot_step(step) != -1; ++k) {

    contact_round(k);
    /* --- puesta en escena ------------------------------------------------ */
    broadcast(tx, "STOP");
    const int col = reg ? 1 + k % 3 : 0;
    if (col == 0) {
      const double base = (k % 2 == 0) ? 0.0 : M_PI / 2.0;
      const double jit  = ((k * 37) % 17 - 8) * 0.004;   /* +-32 mm determinista */
      const double r0   = 0.18;
      place(&me,   r0 * cos(base) + jit,  r0 * sin(base),        base + M_PI);
      place(&foe, -r0 * cos(base),       -r0 * sin(base) + jit,  base);
    } else {
      /* eje de la cruz con orientacion global variada y +-3 mm de mano */
      const double phi = ((k / 3) * 53 % 360) * M_PI / 180.0;
      const double h   = 0.5 * REG_CENTROS;
      const double jit = ((k * 37) % 7 - 3) * 0.001;
      double ax = cos(phi), ay = sin(phi);
      if (col == 2) { const double t = ax; ax = -ay; ay = t; }
      const double yaw_me  = (col == 1) ? phi + M_PI : phi;   /* de frente se miran */
      const double yaw_foe = (col == 1) ? phi : phi + M_PI;   /* lado y espaldas: opuestos */
      double angle_me=((k*19)%7-3)*M_PI/180.0;
      double angle_foe=((k*23)%7-3)*M_PI/180.0;
      place(&me,   h * ax + jit,  h * ay,        yaw_me+angle_me);
      place(&foe, -h * ax,       -h * ay + jit,  yaw_foe+angle_foe);
    }
    wb_supervisor_simulation_reset_physics();

    const double t_settle_end = wb_robot_get_time() * 1000.0 + SETTLE_MS;
    while (wb_robot_get_time() * 1000.0 < t_settle_end)
      if (wb_robot_step(step) == -1) goto done;

    /* --- combate ---------------------------------------------------------- */
    const double armed_at=wb_robot_get_time()*1000.0+5000.0;
    char arm_msg[80];snprintf(arm_msg,sizeof arm_msg,"ARM %.0f",armed_at);
    broadcast(tx,arm_msg);
    printf("[arranque] pulsador=%.0f permiso=%.0f ms\n",wb_robot_get_time()*1000.0,armed_at);
    while(wb_robot_get_time()*1000.0<armed_at)
      if(wb_robot_step(step)==-1)goto done;
    const double t_start = wb_robot_get_time();
    double last_contact = -99.0;
    int result = 0;
    const char *reason = "tiempo agotado";

    while (wb_robot_get_time() - t_start < timeout) {
      if (wb_robot_step(step) == -1) goto done;
      const double t_now = wb_robot_get_time() - t_start;

      const double *pm = wb_supervisor_node_get_position(me.node);
      const double *pf = wb_supervisor_node_get_position(foe.node);
      const double sx = pf[0] - pm[0], sy = pf[1] - pm[1];
      if (sqrt(sx * sx + sy * sy) < CONTACT_D) last_contact = t_now;

      const bool mo = is_out(&me), fo = is_out(&foe);
      if (mo && fo) { result = 0;  reason = "doble salida"; break; }
      if (fo)       { result = 1;  reason = "rival fuera";  break; }
      if (mo) {
        result = -1;
        reason = (t_now - last_contact < 0.40) ? "expulsado" : "auto-salida";
        break;
      }
    }
    const double dur = wb_robot_get_time() - t_start;

    if (result > 0)      { wins++;   win_time_sum += dur; cw[col]++; }
    else if (result < 0) { losses++; cl[col]++; if (!strcmp(reason, "auto-salida")) self_outs++; }
    else                 { draws++;  cd[col]++; }

    printf("[arbitro] asalto %2d/%d  %-8s %-14s  %+d  %5.2f s\n",
           k + 1, rounds, COL_NAME[col], reason, result, dur);
    fflush(stdout);
  }

done:
  broadcast(tx, "STOP");
  {
    const int total = wins + losses + draws;
    const double wr = total ? (double)wins / total : 0.0;
    printf("\n[arbitro] RESULTADO  %dW %dL %dD  win rate %.1f%%  "
           "auto-salidas %d  t medio de victoria %.2f s\n\n",
           wins, losses, draws, wr * 100.0, self_outs,
           wins ? win_time_sum / wins : 0.0);

    /* desglose del reglamento: por colocacion y combate a 3 rondas */
    char extra[1024] = "", extra_top[96] = "";
    if (reg) {
      double pw[3], pd[3], pl[3], mw, mj, ml;
      size_t o = (size_t)snprintf(extra, sizeof extra, ",\"placements\":[");
      for (int c = 1; c <= 3; ++c) {
        const int n = cw[c] + cl[c] + cd[c];
        pw[c - 1] = n ? (double)cw[c] / n : 0.0;
        pd[c - 1] = n ? (double)cd[c] / n : 1.0;
        pl[c - 1] = n ? (double)cl[c] / n : 0.0;
        printf("[arbitro]   %-8s %dW %dL %dD\n", COL_NAME[c], cw[c], cl[c], cd[c]);
        o += (size_t)snprintf(extra + o, sizeof extra - o,
                              "%s{\"name\":\"%s\",\"rounds\":%d,\"wins\":%d,\"losses\":%d,\"draws\":%d}",
                              c > 1 ? "," : "", COL_NAME[c], n, cw[c], cl[c], cd[c]);
      }
      match_prob(pw, pd, pl, &mw, &mj, &ml);
      printf("[arbitro]   combate: gana %.1f%%  jueces %.1f%%  pierde %.1f%%\n",
             100.0 * mw, 100.0 * mj, 100.0 * ml);
      snprintf(extra + o, sizeof extra - o,
               "],\"match\":{\"win\":%.3f,\"judges\":%.3f,\"loss\":%.3f}", mw, mj, ml);
      snprintf(extra_top, sizeof extra_top, "    \"match_win_rate\": %.3f,\n", mw);
    }

    FILE *f = fopen(out_path, "w");
    if (f) {
      fprintf(f,
        "{\n  \"version\": \"%s\",\n  \"engine\": \"webots\",\n"
        "  \"mode\": \"%s\",\n  \"round_max_s\": %.0f,\n"
        "  \"metrics\": {\n"
        "    \"rounds\": %d,\n    \"wins\": %d,\n    \"losses\": %d,\n    \"draws\": %d,\n"
        "    \"win_rate\": %.3f,\n    \"avg_win_time_s\": %.2f,\n    \"self_outs\": %d,\n%s"
        "    \"opponents\": [{\"name\":\"%s\",\"rounds\":%d,\"wins\":%d,"
        "\"losses\":%d,\"draws\":%d,\"win_rate\":%.3f%s}]\n  }\n}\n",
        version, reg ? "reglamento" : "banco", timeout, total, wins, losses, draws, wr,
        wins ? win_time_sum / wins : 0.0, self_outs, extra_top,
        rival, total, wins, losses, draws, wr, extra);
      fclose(f);
      printf("[arbitro] resultados -> %s\n", out_path);
    } else {
      fprintf(stderr, "[arbitro] no puedo escribir %s\n", out_path);
    }
    fflush(stdout);
  }

  wb_supervisor_simulation_set_mode(WB_SUPERVISOR_SIMULATION_MODE_PAUSE);
  wb_robot_cleanup();
  return 0;
}
