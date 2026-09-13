/* Planta eléctrica del motorreductor. Fuentes y rangos en parameters.json.
 * Ke en el eje de salida y Kt efectivo difieren por las pérdidas reductoras;
 * no se identifica erróneamente el motorreductor con un motor ideal sin pérdidas.
 * TB6612 no incorpora limitación de corriente: se registra la sobrecorriente. */
#ifndef GN_MOTOR_REAL_H
#define GN_MOTOR_REAL_H
#include <webots/position_sensor.h>
#include <stdint.h>
#include <stdlib.h>
static char real_config[16000];
static uint32_t real_rng=1,real_base_seed=1;
static unsigned real_round_index=0;
static int real_random=0;
static WbDeviceTag real_mot[2], real_enc[2];
static int real_encoder_ready[2]={0,0};
static double real_last_pos[2],real_omega[2],real_current[2],real_torque[2];
static double real_applied[2],real_pending[2];
static double real_dt=0.008, real_voltage=7.4;
static double real_kt=0.04837947333333333;
static double motor_r[2],motor_bridge[2],motor_i0[2],motor_ke[2];
static unsigned real_over_continuous=0, real_over_peak=0;
static double real_number(const char *key,double fallback) {
  char tag[128];snprintf(tag,sizeof tag,"\"%s\"",key);
  const char *p=strstr(real_config,tag);if(!p)return fallback;
  p=strchr(p,':');return p?strtod(p+1,NULL):fallback;
}
static double real_uniform(void) {
  real_rng=1664525u*real_rng+1013904223u;
  return (double)(real_rng>>8)/16777216.0;
}
static double real_range(const char *lo,const char *hi,double nominal) {
  return real_random?real_number(lo,nominal)+(real_number(hi,nominal)-real_number(lo,nominal))*real_uniform():nominal;
}
static void real_motor_round(void) {
  real_rng=real_base_seed^(0x9e3779b9u*(++real_round_index));
  real_voltage=real_range("battery_min_v","battery_max_v",real_number("battery_nominal_v",7.4));
  real_kt=real_number("torque_constant_nm_a",0.04837947333333333);
  for(int i=0;i<2;i++) {
    motor_r[i]=real_range("resistance_min_ohm","resistance_max_ohm",real_number("resistance_ohm",4));
    motor_bridge[i]=real_range("bridge_min_ohm","bridge_max_ohm",real_number("bridge_ohm",0.5));
    motor_i0[i]=real_range("idle_current_min_a","idle_current_max_a",real_number("idle_current_a",0.15));
    double rpm=real_range("rpm_min","rpm_max",real_number("rpm_6v",650));
    motor_ke[i]=(6-motor_i0[i]*motor_r[i])/(rpm*2*3.141592653589793/60);
    printf("[planta] %s ciclo=%u rueda=%d V=%.9g R=%.9g Rpuente=%.9g I0=%.9g Ke=%.9g Kt=%.9g\n",wb_robot_get_name(),real_round_index,i,real_voltage,motor_r[i],motor_bridge[i],motor_i0[i],motor_ke[i],real_kt);
  }
  fflush(stdout);
}
static void real_motor_init(WbDeviceTag l,WbDeviceTag r,int step) {
  FILE *f=fopen("../../../real/parameters.json","r");
  if(f){size_t n=fread(real_config,1,sizeof real_config-1,f);real_config[n]=0;fclose(f);}
  real_dt=step/1000.0;
  const char *seed=getenv("GN_REAL_SEED"),*rnd=getenv("GN_REAL_RANDOM");
  real_rng=(seed?(uint32_t)strtoul(seed,NULL,10):0)+1;
  if(strcmp(wb_robot_get_name(),"gelatina")) real_rng^=0x9e3779b9u;
  real_base_seed=real_rng;
  real_random=rnd && atoi(rnd);
  real_mot[0]=l;real_mot[1]=r;
  real_enc[0]=wb_robot_get_device("enc_izq");real_enc[1]=wb_robot_get_device("enc_der");
  for(int i=0;i<2;i++)wb_position_sensor_enable(real_enc[i],step);
  real_motor_round();
}
static void real_motor_apply(double l,double r) {
  double commands[2]={real_pending[0],real_pending[1]};
  real_pending[0]=l;real_pending[1]=r;real_applied[0]=commands[0];real_applied[1]=commands[1];
  for(int i=0;i<2;i++) {
    double p=wb_position_sensor_get_value(real_enc[i]);
    if(!real_encoder_ready[i]) {real_last_pos[i]=p;real_encoder_ready[i]=1;}
    real_omega[i]=(p-real_last_pos[i])/real_dt;real_last_pos[i]=p;
    /* PWM medio, caída del puente y fuerza contraelectromotriz. PWM=0:
     * frenado eléctrico corto, pendiente de confirmar con firmware físico. */
    real_current[i]=(commands[i]*real_voltage-motor_ke[i]*real_omega[i])/(motor_r[i]+motor_bridge[i]);
    real_torque[i]=real_kt*(real_current[i]-motor_i0[i]*tanh(real_omega[i]));
    if(fabs(real_current[i])>1.2)real_over_continuous++;
    if(fabs(real_current[i])>3.2)real_over_peak++;
    wb_motor_set_torque(real_mot[i],real_torque[i]);
  }
}
static const char *real_motor_status(void) {
  static char data[1200];
  snprintf(data,sizeof data,"{\"battery_v\":%.9g,\"resistance_ohm\":[%.9g,%.9g],\"bridge_ohm\":[%.9g,%.9g],"
    "\"omega_rad_s\":[%.9g,%.9g],\"current_a\":[%.9g,%.9g],\"torque_nm\":[%.9g,%.9g],"
    "\"applied_pwm\":[%.9g,%.9g],\"over_1_2a_samples\":%u,\"over_3_2a_samples\":%u}",
    real_voltage,motor_r[0],motor_r[1],motor_bridge[0],motor_bridge[1],real_omega[0],real_omega[1],real_current[0],real_current[1],real_torque[0],real_torque[1],real_applied[0],real_applied[1],real_over_continuous,real_over_peak);
  return data;
}
#endif
