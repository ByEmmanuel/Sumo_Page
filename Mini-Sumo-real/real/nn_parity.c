/* Reproductor nativo de secuencias; emite obs21, actor2 y salida física2. */
#include <stdio.h>
#include "nn_adapter.h"
int main(int argc,char **argv) {
  int common=argc>1 && !strcmp(argv[1],"--common-history");
  int seq,old_seq=-1,armed,mask;unsigned t,armed_ms,x[5];nn_memory memory;
  while(scanf("%d %u %u %d %u %u %u %u %u %d",&seq,&t,&armed_ms,&armed,&x[0],&x[1],&x[2],&x[3],&x[4],&mask)==10) {
    if(seq!=old_seq){nn_reset(&memory);old_seq=seq;}
    if(common && scanf("%f %f",&memory.l,&memory.r)!=2)return 3;
    uint16_t d[5];bool line[4];float obs[21],out[2],applied[2];
    for(int i=0;i<5;i++)d[i]=x[i];for(int i=0;i<4;i++)line[i]=(mask&(1<<i))!=0;
    nn_observation(&memory,t,armed_ms,d,line,obs);nn_politica(obs,out);nn_apply(&memory,armed,out,applied);
    for(int i=0;i<21;i++)printf("%.9g ",obs[i]);
    printf("%.9g %.9g %.9g %.9g\n",out[0],out[1],applied[0],applied[1]);
  }
  return 0;
}
