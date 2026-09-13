/* ==========================================================================
 *  oponente.c  --  Rivales de referencia (banco de pruebas de Webots)
 *
 *  NO forma parte del sistema de control de Gelatina Nuclear y por eso NO se
 *  versiona en la bitacora: es el examen, no el alumno. Si se cambia, las
 *  metricas de versiones anteriores dejan de ser comparables, asi que cualquier
 *  modificacion aqui debe anotarse a mano en la version afectada.
 *
 *  Comportamientos (controllerArgs[0]):
 *     static   -- no se mueve. Mide si sabemos empujar sin autoexpulsarnos.
 *     charger  -- embiste al contacto mas cercano y respeta el borde.
 *     spinner  -- gira sobre si mismo. Dificil de enganchar de frente.
 * ========================================================================== */

#include <webots/robot.h>
#include <webots/motor.h>
#include <webots/distance_sensor.h>
#include <webots/receiver.h>

#include <math.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "motor_real.h"
#include "sensor_real.h"

#define N_DIST 5
#define N_LINE 4
#define WHEEL_MAX_RADS 75.0
#define DIST_MAX_RAW 1190.0
#define LINE_TH 400.0
#define AUTO_ARM_MS 5000.0

static const char *DIST_NAMES[N_DIST] = { "d_l60", "d_l30", "d_c", "d_r30", "d_r60" };
static const char *LINE_NAMES[N_LINE] = { "l_fl", "l_fr", "l_rl", "l_rr" };
static const double ANG_CDEG[N_DIST]  = { 6000, 3000, 0, -3000, -6000 };

typedef enum { K_STATIC, K_CHARGER, K_SPINNER, K_FLANK } kind_t;

static double clamp_unit(double v)
{
  if (v >  1.0) return  1.0;
  if (v < -1.0) return -1.0;
  return v;
}

int main(int argc, char **argv)
{
  wb_robot_init();
  const int step = (int)wb_robot_get_basic_time_step();

  kind_t kind = K_CHARGER;
  if (argc > 1) {
    if      (!strcmp(argv[1], "static"))  kind = K_STATIC;
    else if (!strcmp(argv[1], "spinner")) kind = K_SPINNER;
    else if (!strcmp(argv[1], "flanco")) kind = K_FLANK;
  }

  WbDeviceTag ml = wb_robot_get_device("motor_izq");
  WbDeviceTag mr = wb_robot_get_device("motor_der");
  wb_motor_set_position(ml, INFINITY); wb_motor_set_velocity(ml, 0.0);
  wb_motor_set_position(mr, INFINITY); wb_motor_set_velocity(mr, 0.0);

  real_motor_init(ml,mr,step);
  real_sensor_init(step);

  WbDeviceTag ds[N_DIST], ls[N_LINE];
  for (int i = 0; i < N_DIST; ++i) { ds[i] = wb_robot_get_device(DIST_NAMES[i]); wb_distance_sensor_enable(ds[i], step); }
  for (int i = 0; i < N_LINE; ++i) { ls[i] = wb_robot_get_device(LINE_NAMES[i]); wb_distance_sensor_enable(ls[i], step); }

  WbDeviceTag rx = wb_robot_get_device("receptor");
  if (rx) wb_receiver_enable(rx, step);

  bool armed = false, saw_ref = false;
  double arm_deadline=-1,armed_since=-1;
  double back_t = -1.0;   /* cronometro de la maniobra de retroceso */

  printf("[rival] comportamiento: %s\n", argc > 1 ? argv[1] : "charger");
  fflush(stdout);

  while (wb_robot_step(step) != -1) {
    const double now_ms = wb_robot_get_time() * 1000.0;

    while (rx && wb_receiver_get_queue_length(rx) > 0) {
      const char *m = (const char *)wb_receiver_get_data(rx);
      saw_ref = true;
      if (m && !strncmp(m, "ARM", 3) && !armed && arm_deadline<0) {
        real_motor_round();real_sensor_round();arm_deadline=now_ms+AUTO_ARM_MS;
        double deadline;if(sscanf(m+3,"%lf",&deadline)==1)arm_deadline=deadline;
        back_t=-1;
      }
      if (m && !strncmp(m, "STOP", 4)) { if(armed)printf("[rival] fin de asalto motor=%s\n",real_motor_status()); armed = false; arm_deadline=-1; }
      wb_receiver_next_packet(rx);
    }
    if(!armed && arm_deadline>=0 && now_ms>=arm_deadline){armed=true;armed_since=now_ms;}
    if (!saw_ref && !armed && now_ms >= AUTO_ARM_MS) armed = true;

    real_sensor_poll(now_ms);
    double l = 0.0, r = 0.0;
    if (armed && kind != K_STATIC) {
      const bool lf = qtr_value[0] > LINE_TH ||
                      qtr_value[1] > LINE_TH;
      const bool lr = qtr_value[2] > LINE_TH ||
                      qtr_value[3] > LINE_TH;

      if(kind==K_FLANK && now_ms-armed_since<350 && !lf && !lr) {l=1;r=0.4;}
      else if (kind == K_SPINNER) {
        if (lf || lr) { l = -0.6; r = -0.6; }
        else          { l = -0.5; r =  0.5; }
      } else {
        if (lf && back_t < 0.0) back_t = 0.0;
        if (back_t >= 0.0) {
          back_t += (double)step / 1000.0;
          l = (back_t < 0.30) ? -0.85 : -0.6;
          r = (back_t < 0.30) ? -0.85 :  0.6;
          if (back_t > 0.70) back_t = -1.0;
        } else if (lr) {
          l = 0.9; r = 0.9;
        } else {
          double best = DIST_MAX_RAW; int bi = -1;
          for (int i = 0; i < N_DIST; ++i) {
            const double v = tof_value[i];
            if (v < DIST_MAX_RAW && v < best) { best = v; bi = i; }
          }
          if (bi < 0) { l = -0.45; r = 0.45; }
          else {
            const double turn = ANG_CDEG[bi] / 6000.0 * 0.55;
            l = 0.95 - turn; r = 0.95 + turn;
          }
        }
      }
    }
    l = clamp_unit(l);
    r = clamp_unit(r);
    real_motor_apply(l,r);
  }

  wb_robot_cleanup();
  return 0;
}
