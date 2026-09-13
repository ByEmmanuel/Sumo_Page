/* Contrato exacto de ml/ppo.py: 21 observaciones, memoria, rampa y zona muerta.
 * No se cambian los pesos del actor. Tiempo absoluto y tiempo armado separados. */
#ifndef GN_NN_ADAPTER_H
#define GN_NN_ADAPTER_H
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include "nn_politica.h"
typedef struct {
  float bearing,l,r,line[4];
  int64_t seen_ms,line_ms;
} nn_memory;
static float nn_clip(float x,float a,float b){return x<a?a:x>b?b:x;}
static void nn_reset(nn_memory *m) {
  memset(m,0,sizeof *m);m->seen_ms=m->line_ms=-10000;
}
static void nn_observation(nn_memory *m,uint32_t t_ms,uint32_t armed_ms,
                           const uint16_t d[5],const bool line[4],float obs[21]) {
  const float angles[5]={1.0471975511965977f,0.5235987755982988f,0,-0.5235987755982988f,-1.0471975511965977f};
  float sum=0,bearing=0,minimum=1;
  for(int i=0;i<5;i++) {
    bool valid=d[i]!=65535 && d[i]<=1190;
    obs[i]=valid?d[i]/1200.0f:1;
    if(obs[i]<minimum)minimum=obs[i];
    if(valid){float w=1200-d[i];sum+=w;bearing+=w*angles[i];}
  }
  bool seen=sum>0,any_line=false;
  if(seen){m->bearing=bearing/sum;m->seen_ms=t_ms;}
  for(int i=0;i<4;i++){obs[5+i]=line[i]?1:0;any_line|=line[i];}
  if(any_line){m->line_ms=t_ms;for(int i=0;i<4;i++)m->line[i]=obs[5+i];}
  obs[9]=m->l;obs[10]=m->r;obs[11]=seen?1:0;
  obs[12]=m->bearing/1.0471975511965977f;obs[13]=minimum;
  obs[14]=nn_clip((float)((int64_t)t_ms-m->seen_ms),0,1000)/1000;
  obs[15]=nn_clip((float)((int64_t)t_ms-m->line_ms),0,1000)/1000;
  for(int i=0;i<4;i++)obs[16+i]=m->line[i];
  obs[20]=nn_clip((float)armed_ms,0,3000)/3000;
}
static void nn_apply(nn_memory *m,bool armed,const float action[2],float applied[2]) {
  float l=m->l+nn_clip(nn_clip(action[0],-1,1)-m->l,-0.2f,0.2f);
  float r=m->r+nn_clip(nn_clip(action[1],-1,1)-m->r,-0.2f,0.2f);
  m->l=armed?l:0;m->r=armed?r:0;
  applied[0]=fabsf(m->l)<0.04f?0:m->l;applied[1]=fabsf(m->r)<0.04f?0:m->r;
}
#endif
