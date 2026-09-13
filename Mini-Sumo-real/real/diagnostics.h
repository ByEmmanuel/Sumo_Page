/* Diagnóstico: consignas explícitas por receptor y telemetría cada 8 ms.
 * No altera los sensores ni actuadores durante los combates. */
#ifndef GN_REAL_DIAGNOSTICS_H
#define GN_REAL_DIAGNOSTICS_H
static int diag_active = 0;
static double diag_command[2] = {0, 0};
static unsigned diag_line_mask = 0;
static double diag_dist[5], diag_line[4];
static void diag_message(const char *msg) {
  char name[64]; double l, r;
  if(sscanf(msg,"RESET %63s",name)==1 && !strcmp(name,wb_robot_get_name())) {
    real_motor_round();real_sensor_round();
  }
  if (sscanf(msg, "DRIVE %63s %lf %lf", name, &l, &r) == 3 && !strcmp(name, wb_robot_get_name())) {
    diag_active = 1; diag_command[0] = l; diag_command[1] = r;
  }
}
static void diag_publish(double l, double r) {
  char data[2048];
  snprintf(data, sizeof data,
    "{\"u\":[%.9g,%.9g],\"line_mask\":%u,\"distance_mm\":[%.9g,%.9g,%.9g,%.9g,%.9g],"
    "\"line_raw\":[%.9g,%.9g,%.9g,%.9g],\"tof_timestamp_ms\":[%.9g,%.9g,%.9g,%.9g,%.9g],\"adc\":[%.9g,%.9g,%.9g,%.9g],\"motor\":%s}", l, r, diag_line_mask,
    diag_dist[0],diag_dist[1],diag_dist[2],diag_dist[3],diag_dist[4],
    diag_line[0],diag_line[1],diag_line[2],diag_line[3],tof_stamp[0],tof_stamp[1],tof_stamp[2],tof_stamp[3],tof_stamp[4],qtr_adc[0],qtr_adc[1],qtr_adc[2],qtr_adc[3],real_motor_status());
  wb_robot_set_custom_data(data);
}
#endif
