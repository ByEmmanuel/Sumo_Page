/* VL53L0X: proyección horizontal del FoV de25°, cinco rayos sin suelo.
 * Aproximación explícita: no simula la integración óptica del cono vertical.
 * El blanco debe cubrir algún rayo; la superficie determina alcance/ruido.
 * Cadencia33ms muestreada en la rejilla física8ms: intervalos32/40ms. */
#ifndef GN_SENSOR_REAL_H
#define GN_SENSOR_REAL_H
static WbDeviceTag tof_rays[5][5];
static double tof_value[5]={65535,65535,65535,65535,65535};
static double tof_next[5],tof_stamp[5];
static double tof_limit=1200,tof_min=30,tof_noise=0.07;
static unsigned tof_rng=1;
static double tof_uniform(void) {
  tof_rng=1664525u*tof_rng+1013904223u;return ((tof_rng>>8)+0.5)/16777216.0;
}
static double tof_normal(void) {
  return sqrt(-2*log(tof_uniform()))*cos(6.283185307179586*tof_uniform());
}
static WbDeviceTag qtr_tags[4];
static double qtr_value[4],qtr_pending[4],qtr_adc[4],qtr_pending_adc[4];
static unsigned qtr_rng=0x12345678u;
static double qtr_normal(void) {
  qtr_rng=1664525u*qtr_rng+1013904223u;double u=((qtr_rng>>8)+0.5)/16777216.0;
  qtr_rng=1664525u*qtr_rng+1013904223u;double v=((qtr_rng>>8)+0.5)/16777216.0;
  return sqrt(-2*log(u))*cos(6.283185307179586*v);
}
static double qtr_gain=1,qtr_offset=0,qtr_noise=3;
static void real_line_poll(void) {
  for(int i=0;i<4;i++) {
    qtr_value[i]=qtr_pending[i];qtr_adc[i]=qtr_pending_adc[i];
    double reflect=wb_distance_sensor_get_value(qtr_tags[i]);
    double adc=4095-reflect*qtr_gain+qtr_offset+qtr_noise*qtr_normal();
    adc=fmax(0,fmin(4095,round(adc)));
    qtr_pending_adc[i]=adc;qtr_pending[i]=1000*(4095-adc)/4095;
  }
}
static void real_sensor_round(void) {
  qtr_gain=real_range("qtr_gain_min","qtr_gain_max",1);
  qtr_offset=real_range("qtr_offset_min_adc","qtr_offset_max_adc",0);
  qtr_noise=real_range("qtr_noise_min_adc","qtr_noise_max_adc",real_number("qtr_noise_adc",3));
  tof_limit=real_range("tof_range_min_mm","tof_range_max_mm",real_number("tof_range_mm",1200));
  tof_min=real_range("tof_minimum_min_mm","tof_minimum_max_mm",real_number("tof_minimum_mm",30));
  tof_noise=real_range("tof_noise_fraction_min","tof_noise_fraction_max",real_number("tof_noise_fraction",0.07));
  tof_rng=real_rng^0xa341316cu;qtr_rng=real_rng^0x12345678u;
  double now=wb_robot_get_time()*1000;
  for(int i=0;i<5;i++) {tof_next[i]=now+real_number("tof_period_ms",33)+i*real_number("i2c_read_ms",0.36);tof_value[i]=65535;tof_stamp[i]=now;}
  printf("[sensores] %s ToF alcance=%.9g minimo=%.9g sigma_rel=%.9g\n",wb_robot_get_name(),tof_limit,tof_min,tof_noise);
}
static void real_sensor_init(int step) {
  const char *names[]={"d_l60","d_l30","d_c","d_r30","d_r60"};
  for(int i=0;i<5;i++)for(int j=0;j<5;j++) {
    char name[64];if(j==0)snprintf(name,sizeof name,"%s",names[i]);
    else snprintf(name,sizeof name,"%s_r%d",names[i],j);
    tof_rays[i][j]=wb_robot_get_device(name);wb_distance_sensor_enable(tof_rays[i][j],step);
  }
  const char *lines[]={"l_fl","l_fr","l_rl","l_rr"};
  for(int i=0;i<4;i++){qtr_tags[i]=wb_robot_get_device(lines[i]);wb_distance_sensor_enable(qtr_tags[i],step);}
  qtr_rng=real_rng^0x12345678u;
  tof_rng=real_rng^0xa341316cu;
  real_sensor_round();
  for(int i=0;i<5;i++) tof_next[i]=real_number("tof_period_ms",33)+i*real_number("i2c_read_ms",0.36);
}
static void real_sensor_poll(double now_ms) {
  real_line_poll();
  for(int i=0;i<5;i++)if(now_ms>=tof_next[i]) {
    double raw=2000;
    for(int j=0;j<5;j++) {
      double v=wb_distance_sensor_get_value(tof_rays[i][j]);if(v<raw)raw=v;
    }
    double measured=65535;
    if(raw<1999 && raw>=tof_min && raw<=tof_limit) {
      double sigma=hypot(real_number("tof_noise_floor_mm",2),tof_noise*raw);
      measured=fmax(0,raw+sigma*tof_normal());
      if(real_random && tof_uniform()<real_number("tof_dropout_probability",0.03)) measured=65535;
    }
    tof_value[i]=measured;tof_stamp[i]=now_ms;
    double period=real_number("tof_period_ms",33);
    do{tof_next[i]+=period;}while(tof_next[i]<=now_ms);
  }
}
#endif
