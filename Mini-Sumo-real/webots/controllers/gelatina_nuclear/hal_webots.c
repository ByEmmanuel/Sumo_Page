/* ==========================================================================
 *  hal_webots.c  --  Backend de Webots para Gelatina Nuclear
 *
 *  Traduce entre la API de Webots y el contrato sumo_types.h. Aqui viven
 *  TODOS los detalles sucios: nombres de dispositivos, unidades, umbrales de
 *  calibracion y la senal de arranque del arbitro. Nada de esto contamina el
 *  algoritmo.
 * ========================================================================== */

#include "hal.h"

#include <webots/robot.h>
#include <webots/motor.h>
#include <webots/distance_sensor.h>
#include <webots/position_sensor.h>
#include <webots/inertial_unit.h>
#include <webots/gyro.h>
#include <webots/receiver.h>
#include <webots/led.h>

#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "motor_real.h"
#include "sensor_real.h"
#include "diagnostics.h"

/* ---- calibracion de la plataforma -------------------------------------- */
#define WHEEL_MAX_RADS   75.0    /* consigna 1.0 -> 75 rad/s (motor: 80 max) */
#define DIST_MAX_RAW   1190.0    /* por encima de esto, no hay objetivo      */
#define LINE_TH_DEFAULT   400    /* blanco ~900, negro ~20: umbral holgado   */
#define AUTO_ARM_MS      5000    /* reglamento: 5 s. Solo si no hay arbitro. */

static const char *DIST_NAMES[SUMO_N_DIST] = { "d_l60", "d_l30", "d_c", "d_r30", "d_r60" };
static const char *LINE_NAMES[SUMO_N_LINE] = { "l_fl", "l_fr", "l_rl", "l_rr" };

static int  g_step_ms   = 8;
static int  g_line_th   = LINE_TH_DEFAULT;
static bool g_calib     = false;
static bool g_armed     = false;
static bool g_saw_ref   = false;   /* hemos oido alguna vez al arbitro */
static double g_t0_ms   = 0.0;
static double g_arm_deadline = -1;

static WbDeviceTag g_mot[2];
static WbDeviceTag g_enc[2];
static WbDeviceTag g_dist[SUMO_N_DIST];
static WbDeviceTag g_line[SUMO_N_LINE];
static WbDeviceTag g_imu, g_gyro, g_rx, g_led;
static bool g_has_imu, g_has_gyro, g_has_rx, g_has_led;


bool hal_init(int argc, char **argv)
{
  wb_robot_init();
  g_step_ms = (int)wb_robot_get_basic_time_step();

  for (int i = 1; i < argc; ++i) {
    if (!strcmp(argv[i], "--line-th") && i + 1 < argc) g_line_th = atoi(argv[++i]);
    else if (!strcmp(argv[i], "--calib")) g_calib = true;
  }

  g_mot[0] = wb_robot_get_device("motor_izq");
  g_mot[1] = wb_robot_get_device("motor_der");
  g_enc[0] = wb_robot_get_device("enc_izq");
  g_enc[1] = wb_robot_get_device("enc_der");
  for (int i = 0; i < 2; ++i) {
    wb_motor_set_position(g_mot[i], INFINITY);   /* modo velocidad */
    wb_motor_set_velocity(g_mot[i], 0.0);
    wb_position_sensor_enable(g_enc[i], g_step_ms);
  }

  for (int i = 0; i < SUMO_N_DIST; ++i) {
    g_dist[i] = wb_robot_get_device(DIST_NAMES[i]);
    wb_distance_sensor_enable(g_dist[i], g_step_ms);
  }
  for (int i = 0; i < SUMO_N_LINE; ++i) {
    g_line[i] = wb_robot_get_device(LINE_NAMES[i]);
    wb_distance_sensor_enable(g_line[i], g_step_ms);
  }

  g_imu  = wb_robot_get_device("imu");    g_has_imu  = (g_imu  != 0);
  g_gyro = wb_robot_get_device("giro");   g_has_gyro = (g_gyro != 0);
  g_rx   = wb_robot_get_device("receptor"); g_has_rx = (g_rx   != 0);
  g_led  = wb_robot_get_device("led");    g_has_led  = (g_led  != 0);
  if (g_has_imu)  wb_inertial_unit_enable(g_imu, g_step_ms);
  if (g_has_gyro) wb_gyro_enable(g_gyro, g_step_ms);
  if (g_has_rx)   wb_receiver_enable(g_rx, g_step_ms);

  real_motor_init(g_mot[0], g_mot[1], g_step_ms);
  real_sensor_init(g_step_ms);
  hal_log("HAL Webots listo: paso %d ms, umbral de linea %d", g_step_ms, g_line_th);
  return true;
}


uint16_t hal_period_ms(void) { return (uint16_t)g_step_ms; }


/* Vacia el buzon del arbitro. Protocolo de texto plano, canal 1:
 *   "ARM"  -> empieza el asalto (reinicia el reloj del algoritmo)
 *   "STOP" -> alto el fuego, el arbitro esta recolocando a los robots      */
static void drain_referee(void)
{
  if (!g_has_rx) return;
  while (wb_receiver_get_queue_length(g_rx) > 0) {
    const char *msg = (const char *)wb_receiver_get_data(g_rx);
    g_saw_ref = true;
    if (msg) diag_message(msg);
    if (msg && !strncmp(msg, "ARM", 3)) {
      if (!g_armed && g_arm_deadline < 0) {
        real_motor_round();real_sensor_round();
        g_arm_deadline=wb_robot_get_time()*1000.0+AUTO_ARM_MS;
        double deadline;if(sscanf(msg+3,"%lf",&deadline)==1)g_arm_deadline=deadline;
        hal_log("pulsador recibido: permiso previsto %.0f ms",g_arm_deadline);
      }
    } else if (msg && !strncmp(msg, "STOP", 4)) {
      if(g_armed)hal_log("fin de asalto motor=%s",real_motor_status());
      g_armed = false;g_arm_deadline=-1;
    }
    wb_receiver_next_packet(g_rx);
  }
}


bool hal_poll(sumo_sensors_t *s)
{
  if (wb_robot_step(g_step_ms) == -1) return false;

  drain_referee();
  const double now_ms = wb_robot_get_time() * 1000.0;

  if(!g_armed && g_arm_deadline>=0 && now_ms>=g_arm_deadline) {
    g_armed=true;g_t0_ms=now_ms;
    hal_log("permiso de arranque a los %.0f ms",now_ms);
  }
  /* Sin arbitro en el mundo, el robot se arma solo tras los 5 s de reglamento
   * para que el mundo siga siendo util abriendolo a pelo. */
  if (!g_saw_ref && !g_armed && now_ms >= AUTO_ARM_MS) {
    g_armed = true;
    g_t0_ms = now_ms;
    hal_log("sin arbitro: auto-arranque a los %.0f ms", now_ms);
  }

  real_sensor_poll(now_ms);
  memset(s, 0, sizeof(*s));
  s->armed = g_armed;
  s->t_ms  = g_armed ? (uint32_t)(now_ms - g_t0_ms) : 0u;

  for (int i = 0; i < SUMO_N_DIST; ++i) {
    const double raw = tof_value[i];
    diag_dist[i] = raw;
    s->dist_mm[i] = (raw > DIST_MAX_RAW) ? SUMO_DIST_NONE : (uint16_t)raw;
  }

  diag_line_mask = 0;
  for (int i = 0; i < SUMO_N_LINE; ++i) {
    const double raw = qtr_value[i];
    s->line[i] = (raw > (double)g_line_th);
    diag_line[i] = raw;
    if (s->line[i]) diag_line_mask |= 1u << i;
  }

  if (g_has_imu) {
    const double *rpy = wb_inertial_unit_get_roll_pitch_yaw(g_imu);
    s->yaw_rad = (float)rpy[2];
  }
  if (g_has_gyro) {
    const double *g = wb_gyro_get_values(g_gyro);
    s->gyro_z_rads = (float)g[2];
  }
  s->wheel_rad[0] = (float)wb_position_sensor_get_value(g_enc[0]);
  s->wheel_rad[1] = (float)wb_position_sensor_get_value(g_enc[1]);

  if (g_calib) {
    hal_log("CALIB linea  FL=%6.1f FR=%6.1f RL=%6.1f RR=%6.1f   dist C=%5u",
            wb_distance_sensor_get_value(g_line[0]),
            wb_distance_sensor_get_value(g_line[1]),
            wb_distance_sensor_get_value(g_line[2]),
            wb_distance_sensor_get_value(g_line[3]),
            s->dist_mm[DIST_C]);
  }
  return true;
}


static double clamp_unit(double v)
{
  if (v >  1.0) return  1.0;
  if (v < -1.0) return -1.0;
  return v;
}


void hal_apply(const sumo_actuators_t *a)
{
  const double l = clamp_unit(diag_active ? diag_command[0] : a->left);
  const double r = clamp_unit(diag_active ? diag_command[1] : a->right);
  real_motor_apply(l, r);
  diag_publish(l, r);
  if (g_has_led) wb_led_set(g_led, (a->led == 4 || a->led == 5) ? 1 : 0);
}


void hal_log(const char *fmt, ...)
{
  va_list ap;
  printf("[%s] ", wb_robot_get_name());
  va_start(ap, fmt);
  vprintf(fmt, ap);
  va_end(ap);
  printf("\n");
  fflush(stdout);
}


void hal_shutdown(void)
{
  wb_motor_set_velocity(g_mot[0], 0.0);
  wb_motor_set_velocity(g_mot[1], 0.0);
  wb_robot_cleanup();
}
