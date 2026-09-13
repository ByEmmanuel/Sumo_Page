/* Actor congelado con el mismo HAL físico que las máquinas de estados. */
#include "hal.h"
#include "nn_adapter.h"
int main(int argc,char **argv) {
  if(!hal_init(argc,argv))return 1;
  nn_memory memory;nn_reset(&memory);
  sumo_sensors_t s;bool was_armed=false;uint32_t elapsed=0;
  while(hal_poll(&s)) {
    if(was_armed && !s.armed){nn_reset(&memory);elapsed=0;}
    float obs[21],action[2],applied[2];
    nn_observation(&memory,elapsed,s.armed?s.t_ms:0,s.dist_mm,s.line,obs);
    nn_politica(obs,action);nn_apply(&memory,s.armed,action,applied);
    sumo_actuators_t a={applied[0],applied[1],0};hal_apply(&a);
    elapsed+=hal_period_ms();was_armed=s.armed;
  }
  hal_shutdown();return 0;
}
