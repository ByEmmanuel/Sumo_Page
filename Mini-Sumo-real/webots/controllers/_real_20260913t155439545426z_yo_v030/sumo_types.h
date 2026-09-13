/* ==========================================================================
 *  sumo_types.h  --  Contrato estable entre el MUNDO y el ALGORITMO
 *
 *  Este fichero define la unica frontera que ve la estrategia. Ni Webots ni
 *  ningun microcontrolador aparecen aqui: la estrategia solo consume un
 *  sumo_sensors_t y produce un sumo_actuators_t.
 *
 *  Consecuencia practica: el mismo strategy.c compila sin cambios en
 *      - el controlador de Webots      (backend hal_webots.c)
 *      - el firmware del robot real    (backend hal_<mcu>.c, por escribir)
 *      - el banco de pruebas nativo    (tests/harness.c)
 *
 *  Regla: este fichero cambia MUY poco. Cada cambio aqui rompe todos los
 *  backends, asi que exige subir version MINOR como minimo.
 * ========================================================================== */
#ifndef SUMO_TYPES_H
#define SUMO_TYPES_H

#include <stdint.h>
#include <stdbool.h>

/* -------------------------------------------------------------------------
 *  Geometria del robot (clase mini-sumo: 10 x 10 cm, 500 g)
 * ------------------------------------------------------------------------- */
#define SUMO_BODY_MM        100.0f   /* lado maximo reglamentario            */
#define SUMO_MASS_G         500.0f   /* masa maxima reglamentaria            */
#define SUMO_WHEEL_R_M      0.021f   /* radio de rueda                       */
#define SUMO_TRACK_M        0.085f   /* distancia entre centros de rueda     */

/* -------------------------------------------------------------------------
 *  Sensores de distancia: 5 al frente, de izquierda a derecha
 *
 *          L60   L30   C   R30   R60
 *            \    \    |    /    /
 *             \    \   |   /    /
 *              +---------------+
 *              |   GELATINA    |
 * ------------------------------------------------------------------------- */
#define SUMO_N_DIST 5
enum sumo_dist_idx {
  DIST_L60 = 0,   /* +60 grados (a babor)  */
  DIST_L30 = 1,   /* +30 grados            */
  DIST_C   = 2,   /*   0 grados (proa)     */
  DIST_R30 = 3,   /* -30 grados            */
  DIST_R60 = 4    /* -60 grados (estribor) */
};

/* Angulo de montaje de cada sensor, en CENTIGRADOS (1/100 de grado),
 * positivo = a babor. int16_t llega a +-327 grados, margen de sobra. */
extern const int16_t SUMO_DIST_ANGLE_CDEG[SUMO_N_DIST];

/* Valor centinela: no hay nada dentro del alcance util del sensor. */
#define SUMO_DIST_NONE  ((uint16_t)0xFFFFu)

/* -------------------------------------------------------------------------
 *  Sensores de linea: 4 en las esquinas, mirando al suelo
 * ------------------------------------------------------------------------- */
#define SUMO_N_LINE 4
enum sumo_line_idx {
  LINE_FL = 0,   /* frontal izquierdo */
  LINE_FR = 1,   /* frontal derecho   */
  LINE_RL = 2,   /* trasero izquierdo */
  LINE_RR = 3    /* trasero derecho   */
};

#define SUMO_LINE_FRONT_MASK ((1u << LINE_FL) | (1u << LINE_FR))
#define SUMO_LINE_REAR_MASK  ((1u << LINE_RL) | (1u << LINE_RR))
#define SUMO_LINE_LEFT_MASK  ((1u << LINE_FL) | (1u << LINE_RL))
#define SUMO_LINE_RIGHT_MASK ((1u << LINE_FR) | (1u << LINE_RR))

/* -------------------------------------------------------------------------
 *  Entrada de la estrategia
 * ------------------------------------------------------------------------- */
typedef struct {
  uint32_t t_ms;                      /* ms desde la senal de arranque      */
  uint16_t dist_mm[SUMO_N_DIST];      /* mm, o SUMO_DIST_NONE               */
  bool     line[SUMO_N_LINE];         /* true = borde blanco bajo el sensor */
  float    yaw_rad;                   /* rumbo absoluto, IMU                */
  float    gyro_z_rads;               /* velocidad de guinada               */
  float    wheel_rad[2];              /* [0]=izq [1]=der, angulo acumulado  */
  bool     armed;                     /* true tras los 5 s de reglamento    */
} sumo_sensors_t;

/* -------------------------------------------------------------------------
 *  Salida de la estrategia
 * ------------------------------------------------------------------------- */
typedef struct {
  float   left;    /* consigna rueda izquierda, normalizada [-1 .. +1] */
  float   right;   /* consigna rueda derecha,   normalizada [-1 .. +1] */
  uint8_t led;     /* bitmap de depuracion, opcional                   */
} sumo_actuators_t;

#endif /* SUMO_TYPES_H */
