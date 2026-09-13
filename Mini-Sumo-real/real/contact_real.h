/* Fricción sin adhesión. Intervalos exploratorios, no medidas de silicona. */
#ifndef GN_CONTACT_REAL_H
#define GN_CONTACT_REAL_H
static char contact_config[16000];
static unsigned contact_seed=1;
static double contact_number(const char *name,double fallback) {
  char key[128];snprintf(key,sizeof key,"\"%s\"",name);
  const char *p=strstr(contact_config,key);if(!p)return fallback;
  p=strchr(p,':');return p?strtod(p+1,NULL):fallback;
}
static double contact_rand(void) {
  contact_seed=1664525u*contact_seed+1013904223u;
  return (contact_seed>>8)/16777216.0;
}
static void contact_init(void) {
  FILE *f=fopen("../../../real/parameters.json","r");
  if(f){size_t n=fread(contact_config,1,sizeof contact_config-1,f);contact_config[n]=0;fclose(f);}
  const char *s=getenv("GN_REAL_SEED");contact_seed=(s?(unsigned)strtoul(s,NULL,10):0)+1;
}
static void contact_round(int k) {
  int rnd=getenv("GN_REAL_RANDOM") && atoi(getenv("GN_REAL_RANDOM"));
  double mu=contact_number("friction_nominal",1.1),slip=contact_number("slip_nominal",0.0005);
  if(rnd) {
    mu=contact_number("friction_min",0.6)+(contact_number("friction_max",1.6)-contact_number("friction_min",0.6))*contact_rand();
    slip=contact_number("slip_min",0)+(contact_number("slip_max",0.002)-contact_number("slip_min",0))*contact_rand();
  }
  WbNodeRef info=wb_supervisor_node_get_from_def("FISICA");
  WbNodeRef cp=wb_supervisor_field_get_mf_node(wb_supervisor_node_get_field(info,"contactProperties"),0);
  wb_supervisor_field_set_mf_float(wb_supervisor_node_get_field(cp,"coulombFriction"),0,mu);
  wb_supervisor_field_set_mf_float(wb_supervisor_node_get_field(cp,"forceDependentSlip"),0,slip);
  if(rnd) {
    const char *robots[]={"GELATINA","RIVAL"};const char *wheels[]={"inertia_izq","inertia_der"};
    for(int r=0;r<2;r++)for(int w=0;w<2;w++) {
      WbNodeRef robot=wb_supervisor_node_get_from_def(robots[r]);
      WbFieldRef inertia=wb_supervisor_node_get_field(robot,wheels[w]);
      const double *old=wb_supervisor_field_get_mf_vec3f(inertia,0);
      double rotor=contact_number("rotor_inertia_min",0.9e-5)+(contact_number("rotor_inertia_max",3.6e-5)-contact_number("rotor_inertia_min",0.9e-5))*contact_rand();
      double values[3]={old[0],4.11e-6+rotor,old[2]};
      wb_supervisor_field_set_mf_vec3f(inertia,0,values);
      const double *actual=wb_supervisor_field_get_mf_vec3f(inertia,0);
      if(fabs(actual[1]-values[1])>1e-12){fprintf(stderr,"Error: inercia solicitada no aplicada\n");wb_supervisor_simulation_quit(2);return;}
      printf("[inercia] asalto=%d robot=%s rueda=%d rotor=%.9g\n",k,robots[r],w,rotor);
    }
  }
  printf("[planta] asalto=%d mu=%.9g slip=%.9g aleatorio=%d\n",k,mu,slip,rnd);fflush(stdout);
}
#endif
