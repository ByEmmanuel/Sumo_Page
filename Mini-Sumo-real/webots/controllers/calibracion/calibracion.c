/* Ensayos reproducibles de la planta; no contiene estrategias de combate. */
#include <webots/robot.h>
#include <webots/supervisor.h>
#include <webots/emitter.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "contact_real.h"

static WbNodeRef me, foe;
static WbDeviceTag tx;
static FILE *out;
static int rows=0;
static int duration_steps(int test){return test==1?125:(test==2||test==3)?500:250;}
static void drive(const char *name, double l, double r) {
  char msg[128]; snprintf(msg,sizeof msg,"DRIVE %s %.9g %.9g",name,l,r);
  wb_emitter_send(tx,msg,strlen(msg)+1);
}
static void place(WbNodeRef n,double x,double y,double yaw) {
  double p[3]={x,y,0.001}, r[4]={0,0,1,yaw};
  wb_supervisor_field_set_sf_vec3f(wb_supervisor_node_get_field(n,"translation"),p);
  wb_supervisor_field_set_sf_rotation(wb_supervisor_node_get_field(n,"rotation"),r);
  wb_supervisor_node_reset_physics(n);
}
static void reset(double x,double y,double fx,double fy,double fyaw) {
  wb_emitter_send(tx,"RESET gelatina",15);wb_emitter_send(tx,"RESET rival",12);
  drive("gelatina",0,0); drive("rival",0,0);
  for(int k=0;k<10;k++) wb_robot_step(8);
  place(me,x,y,0); place(foe,fx,fy,fyaw);
  wb_supervisor_simulation_reset_physics();
  for(int k=0;k<50;k++) wb_robot_step(8);
}
static const char *telemetry(WbNodeRef n) {
  const char *s=wb_supervisor_field_get_sf_string(wb_supervisor_node_get_base_node_field(n,"customData"));
  return s && *s ? s : "{}";
}
static void record(const char *name,int k,int phase) {
  rows++;
  const double *p=wb_supervisor_node_get_position(me);
  double q[3]={p[0],p[1],p[2]};
  const double *v=wb_supervisor_node_get_velocity(me);
  double vel[6]; memcpy(vel,v,sizeof vel);
  const double *orientation=wb_supervisor_node_get_orientation(me);
  double yaw=atan2(orientation[3],orientation[0]);
  const double *f=wb_supervisor_node_get_position(foe);
  char tm[2048]; snprintf(tm,sizeof tm,"%s",telemetry(me));
  fprintf(out,"{\"test\":\"%s\",\"t_ms\":%d,\"phase\":%d,\"position_m\":[%.9g,%.9g,%.9g],"
    "\"velocity\":[%.9g,%.9g,%.9g,%.9g,%.9g,%.9g],\"yaw_rad\":%.9g,\"rival_position_m\":[%.9g,%.9g,%.9g],\"hal\":%s}\n",
    name,k*8,phase,q[0],q[1],q[2],vel[0],vel[1],vel[2],vel[3],vel[4],vel[5],yaw,f[0],f[1],f[2],tm);
}
int main(int argc,char **argv) {
  wb_robot_init();
  contact_init();
  if(argc!=2) return 2;
  out=fopen(argv[1],"w"); if(!out) return 3;
  me=wb_supervisor_node_get_from_def("GELATINA"); foe=wb_supervisor_node_get_from_def("RIVAL");
  tx=wb_robot_get_device("emisor");
  const char *names[]={"reposo","aceleracion","frenada_inversa","frenada_cero","giro_positivo","giro_negativo","empuje_frenado","empuje_igual","borde_03","borde_06","borde_10","sensor_vacio","sensor_005","sensor_010","sensor_030","sensor_050","sensor_100","sensor_flanco","qtr_blanco","qtr_pala","qtr_negro"};
  for(int test=0;test<21;test++) {
    contact_round(test);
    int edge=test>=8 && test<=10, sensor=test>=11;
    double fx=3.8,fy=2;
    if(test==6 || test==7) fx=0.104;
    if(sensor) {fx=test==11?1.8:test==12?0.13:test==13?0.18:test==14?0.38:test==15?0.58:1.08;fy=2;}
    if(test==17) {fx=0.38;fy=2.06;}
    WbNodeRef blade=NULL;
    if(test==19) {
      wb_supervisor_field_import_mf_node_from_string(wb_supervisor_node_get_field(wb_supervisor_node_get_root(),"children"),-1,
        "DEF PALA_PRUEBA Solid { translation 0.022 2 0.002 children [ Shape { appearance PBRAppearance { baseColor 0.82 0.83 0.85 metalness 0.60 roughness 0.22 } geometry Box { size 0.03 0.095 0.003 } } ] boundingObject Box { size 0.03 0.095 0.003 } }");
      blade=wb_supervisor_node_get_from_def("PALA_PRUEBA");
    }
    reset(test==18?0.348:edge?0.18:0,test==18?0:edge?0:2,fx,fy,3.141592653589793);
    double l=0,r=0;
    if(test>=1 && test<=3) l=r=1;
    if(test==4) {l=-1;r=1;}
    if(test==5) {l=1;r=-1;}
    if(test==6 || test==7) {l=r=1;drive("rival",test==7?1:0,test==7?1:0);}
    if(edge) l=r=test==8?0.3:test==9?0.6:1;
    drive("gelatina",l,r);
    int phase=0,braked=0;
    for(int k=0;k<=duration_steps(test);k++) {
      if((test==2 || test==3) && k==188) {drive("gelatina",test==2?-1:0,test==2?-1:0);phase=1;}
      if(edge && !braked) {
        const char *tm=telemetry(me), *mask=strstr(tm,"\"line_mask\":");
        if(mask && atoi(mask+12)!=0) {drive("gelatina",0,0);phase=1;braked=1;}
      }
      record(names[test],k,phase);
      if(wb_robot_step(8)==-1) goto done;
    }
    if(blade)wb_supervisor_node_remove(blade);
  }
done:
  fclose(out); drive("gelatina",0,0);drive("rival",0,0);
  int expected=0;for(int t=0;t<21;t++)expected+=duration_steps(t)+1;
  char done_path[1024];snprintf(done_path,sizeof done_path,"%s.done",argv[1]);
  FILE *done_file=fopen(done_path,"w");
  if(done_file){fprintf(done_file,"{\"expected\":%d,\"actual\":%d,\"complete\":%s}\n",expected,rows,expected==rows?"true":"false");fclose(done_file);}
  wb_supervisor_simulation_quit(0); wb_robot_cleanup(); return 0;
}
