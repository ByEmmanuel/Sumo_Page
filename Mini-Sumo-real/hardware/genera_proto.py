#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
genera_proto.py -- escribe el PROTO de Webots y el BOM desde modelo_robot.py.

    python3 hardware/genera_proto.py

Nunca se edita webots/protos/GelatinaNuclear.proto a mano: se cambia la
pieza en modelo_robot.py y se regenera. Asi la masa, el centro de masas y la
inercia del simulador son siempre los de la lista de materiales.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import modelo_robot as mr  # noqa: E402

MAT = dict(mr.MAT, inox="baseColor IS bladeColor metalness 0.60 roughness 0.22")
_usados = set()


def f(v):
    s = f"{v:.5f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def v3(t):
    return " ".join(f(x) for x in t)


def ap(mat):
    if mat in _usados:
        return f"USE AP_{mat.upper()}"
    _usados.add(mat)
    return f"DEF AP_{mat.upper()} PBRAppearance {{ {MAT[mat]} }}"


def forma(p, ind="      "):
    if p["forma"] == "caja":
        g, rot, nodo, esc = f"Box {{ size {v3(p['s'])} }}", "", "Pose", ""
        if p["roty"]:
            rot = f" rotation 0 1 0 {f(p['roty'])}"
    elif p["forma"] == "cil":
        g = f"Cylinder {{ radius {f(p['r'])} height {f(p['h'])} subdivision 24 }}"
        rot = {"y": " rotation 1 0 0 1.5708", "x": " rotation 0 1 0 1.5708", "z": ""}[p["eje"]]
        nodo, esc = ("Transform", f" scale {f(p['sx'])} 1 1") if p["sx"] != 1.0 else ("Pose", "")
    else:
        g, rot, nodo, esc = f"Sphere {{ radius {f(p['r'])} subdivision 2 }}", "", "Pose", ""
    return (f"{ind}{nodo} {{ translation {v3(p['c'])}{rot}{esc} children [ "
            f"Shape {{ appearance {ap(p['mat'])} geometry {g} }} ] }}  # {p['n']}")


def shape(mat, geom, t=(0, 0, 0), rot="", ind="            "):
    return (f"{ind}Pose {{ translation {v3(t)}{rot} children [ "
            f"Shape {{ appearance {ap(mat)} geometry {geom} }} ] }}")


def rueda(sg, lado, eje, trans):
    y = sg * 0.0425
    r90 = " rotation 1 0 0 1.5708"
    agujeros = "\n".join(
        shape("pla_negro", "Cylinder { radius 0.003 height 0.0004 subdivision 12 }",
              (0.0095 * math.cos(a), sg * 0.0078, 0.0095 * math.sin(a)), r90)
        for a in (0.3, 0.3 + 2.0944, 0.3 + 4.1888))
    return f"""      HingeJoint {{
        jointParameters HingeJointParameters {{ axis 0 1 0 anchor -0.010 {f(y)} 0.021 }}
        device [
          RotationalMotor {{ name "motor_{lado}" maxVelocity {mr.MAX_VEL:.1f} maxTorque {mr.MAX_TORQUE:.4f} }}
          PositionSensor  {{ name "enc_{lado}" }}
        ]
        endPoint Solid {{
          translation -0.010 {f(y)} 0.021
          name "rueda_{lado}"
          contactMaterial "rueda"
          children [
{shape("silicona", "Cylinder { radius 0.021 height 0.015 subdivision 32 }", rot=r90)}
{shape("pla_gris", "Cylinder { radius 0.0165 height 0.0154 subdivision 32 }", rot=r90)}
{shape("acero_neg", "Cylinder { radius 0.0035 height 0.0158 subdivision 16 }", rot=r90)}
{agujeros}
          ]
          boundingObject Pose {{{r90} children [ Cylinder {{ radius 0.021 height 0.015 subdivision 24 }} ] }}
          physics DEF RUEDA_FISICA_{lado.upper()} Physics {{ density -1 mass {f(mr.MASA_RUEDA)} centerOfMass [ 0 0 0 ] inertiaMatrix IS inertia_{lado} }}
        }}
      }}"""


def tof(n, x, y, yaw):
    return f"""      DistanceSensor {{
        translation {f(x)} {f(y)} 0.026
        rotation 0 0 1 {f(yaw)}
        name "{n}"
        type "generic" numberOfRays 1
        lookupTable [ 0 0 0, 2.0 2000 0 ]
        children [
{shape("pla_color", "Box { size 0.008 0.016 0.020 }", (-0.0035, 0, 0))}
{shape("epoxi", "Box { size 0.0012 0.0070 0.0045 }", (0.0011, 0, 0))}
        ]
      }}"""


def tof_aux(n, x, y, yaw):
    # Abanico horizontal de25 grados: evita falsos impactos con el suelo.
    # Equivalente a una máscara vertical ideal; pendiente validación óptica.
    return '\n'.join(f'      DistanceSensor {{ translation {f(x)} {f(y)} 0.026 rotation 0 0 1 {yaw+offset:.9f} name "{n}_r{j}" type "generic" numberOfRays 1 lookupTable [ 0 0 0, 2 2000 0 ] }}'
                      for j,offset in enumerate([-math.radians(12.5),-math.radians(6.25),math.radians(6.25),math.radians(12.5)],1))


def qtr(n, x, y):
    # el QRE1113 queda 0.2 mm por encima del origen del rayo: el IR de Webots
    # ve piezas del propio robot y no debe chocar con su propio encapsulado
    return f"""      DistanceSensor {{
        translation {f(x)} {f(y)} 0.006
        rotation 0 1 0 1.5708
        name "{n}"
        type "infra-red" numberOfRays 1 aperture 0.12
        lookupTable [ 0 4095 0, 0.003 3800 0, 0.006 3300 0, 0.012 1500 0, 0.024 400 0, 0.06 50 0, 0.5 0 0 ]
        children [
{shape("pcb_azul", "Box { size 0.0016 0.0076 0.0127 }", (-0.0027, 0, 0))}
{shape("chip", "Box { size 0.0017 0.0029 0.0036 }", (-0.00105, 0, 0))}
        ]
      }}"""


def proto(M, cdm, I, eje, trans, pala, total):
    (bcx, bcz), blargo = pala
    cuerpo = "\n".join(forma(p) for p in mr.piezas if p["vis"])
    z0 = mr.Z0
    return f"""#VRML_SIM R2025a utf8
# tags: static
# ===========================================================================
#  Gelatina Nuclear -- mini-sumo 10 x 10 cm / 500 g, con componentes reales.
#  GENERADO por hardware/genera_proto.py desde hardware/modelo_robot.py.
#  NO EDITAR A MANO: cambiar la pieza alli y regenerar. BOM en hardware/BOM.md.
#
#  Techos numericos Webots: {mr.MAX_VEL:.1f} rad/s, {mr.MAX_TORQUE:.4f} N*m.
#  El HAL calcula velocidad y par electricos desde los datos de Pololu #3063.
#  Masa {total['m'] * 1000:.1f} g; CdM ({total['c'][0] * 1000:+.1f}, {total['c'][1] * 1000:+.1f}, {total['c'][2] * 1000:+.1f}) mm,
#  {-(total['c'][0] + 0.010) * 1000:.1f} mm por detras del eje: casi toda la carga va a las ruedas.
#
#  Distancia: 5 x VL53L0X, cada uno con abanico horizontal de 5 rayos.
#  El HAL aplica periodo, alcance, ruido y minimo fiable. La mascara vertical
#  es ideal y debe validarse en el montaje; no reproduce un cono optico 3D.
#  Linea: QTR analogico; HAL cuantiza ADC12bits y normaliza blanco alto.
#  Curva y reflectancia nominales, pendientes de medir tambien frente a pala.
#  Las esquinas delanteras van tras la pala (x = 0.022): bajo ella no caben.
#  Cylinder tiene su eje en z (R2022a+): ruedas y ejes se giran 90 grados.
# ===========================================================================

PROTO GelatinaNuclear [
  field SFVec3f    translation    0 0 0.001
  field SFRotation rotation       0 0 1 0
  field SFString   name           "gelatina"
  field SFString   controller     "gelatina_nuclear"
  field MFString   controllerArgs []
  field SFColor    color          0.78 0.92 0.12
  field SFColor    bladeColor     0.82 0.83 0.85
  field MFVec3f    inertia_izq    [ {trans:.3e} {eje:.3e} {trans:.3e}, 0 0 0 ]
  field MFVec3f    inertia_der    [ {trans:.3e} {eje:.3e} {trans:.3e}, 0 0 0 ]
]
{{
  Robot {{
    translation IS translation
    rotation IS rotation
    name IS name
    controller IS controller
    controllerArgs IS controllerArgs
    contactMaterial "patin"
    children [
{cuerpo}

{rueda(1, "izq", eje, trans)}
{rueda(-1, "der", eje, trans)}

{chr(10).join(tof(*d) + chr(10) + tof_aux(*d) for d in mr.DIST)}

{chr(10).join(qtr(*l) for l in mr.LINEA)}

      InertialUnit {{ translation -0.012 -0.010 {f(z0 + 0.0009)} name "imu" }}
      Gyro         {{ translation -0.012 -0.010 {f(z0 + 0.0009)} name "giro" }}

      Receiver {{
        translation -0.044 0.010 {f(z0)}
        name "receptor" channel 1
        children [
{shape("pla_negro", "Box { size 0.0012 0.013 0.011 }", (0, 0, 0.0065))}
{shape("epoxi", "Box { size 0.004 0.006 0.005 }", (-0.0026, 0, 0.0085))}
{shape("epoxi", "Sphere { radius 0.0022 subdivision 2 }", (-0.0047, 0, 0.0085))}
        ]
      }}

      LED {{
        translation -0.030 0 {f(z0)}
        name "led"
        children [
          Pose {{ translation 0 0 0.0015 children [ Shape {{ appearance PBRAppearance {{ baseColor 1 1 1 emissiveColor 0 0 0 roughness 0.2 metalness 0 }} geometry Sphere {{ radius 0.0015 subdivision 2 }} }} ] }}
        ]
      }}
    ]

    boundingObject Group {{
      children [
        Pose {{ translation -0.010 0 0.02045 children [ Box {{ size 0.080 0.068 0.0329 }} ] }}
        Pose {{ translation 0.033 0 0.0269 children [ Box {{ size 0.006 0.068 0.0200 }} ] }}
        Pose {{ translation {f(bcx)} 0 {f(bcz)} rotation 0 1 0 {f(mr.TH_PALA)} children [ Box {{ size {f(blargo)} 0.098 0.003 }} ] }}
        Pose {{ translation -0.046 0 0.004 children [ Sphere {{ radius 0.004 subdivision 2 }} ] }}
      ]
    }}
    physics Physics {{
      density -1
      mass {f(M)}
      centerOfMass [ {v3(cdm)} ]
      inertiaMatrix [ {I[0][0]:.4e} {I[1][1]:.4e} {I[2][2]:.4e}, {I[0][1]:.4e} {I[0][2]:.4e} {I[1][2]:.4e} ]
    }}
  }}
}}
"""


# ------------------------------------------------------------------- BOM --
BOM = [
    (2, "Motorreductor", "Pololu #3063: 50:1 Micro Metal Gearmotor HPCB 6V (51,45:1)", ("reductora", "motor (lata)", "tapa del motor"),
     "650 rpm y 0,74 kg·cm a 6 V; a 7,4 V, 802 rpm (84 rad/s) y 0,090 N·m"),
    (2, "Soporte de motor", "Soporte para micro metal gearmotor (Pololu)", ("soporte del motor",), ""),
    (2, "Rueda", "Llanta de PLA impresa + neumático de silicona colada, Ø42 × 15 mm", None,
     "Ø y ancho del modelo desde v0.1.0; 4 g de llanta + 10 g de neumático"),
    (5, "Sensor de distancia ToF", "Pololu #2490: VL53L0X, placa de 13 × 18 mm", ("VL53L0X",),
     "hasta 2 m con FoV de 25°; en la simulación, 1 rayo hasta 1,2 m"),
    (4, "Sensor de línea + soporte", "Pololu #958: QTR-1A (QRE1113), 7,6 × 12,7 mm", ("soporte QTR",),
     "a ~6 mm del suelo; los delanteros van tras la pala"),
    (1, "PCB principal", "FR4 de 1,6 mm, 78 × 68 mm", ("PCB FR4",), "cara superior del robot"),
    (1, "Componentes de la PCB", "STM32F411CEU6, MPU-6050, TB6612FNG, AMS1117-3.3, cristal, XT30, JST-SH, interruptor",
     ("componentes de la PCB",), "el MPU-6050 aporta los dispositivos imu y giro"),
    (1, "Pulsador de arranque", "Pulsador táctil de 6 × 6 mm con capuchón y cableado", ("pulsador de arranque",),
     "reglamento p. 4: arranque con pulsador o interruptor; en Webots, la señal ARM del árbitro"),
    (1, "Batería", "LiPo 2S 7,4 V 300 mAh 45C con XT30 (46 × 16 × 14 mm)", ("LiPo",), "p. ej. TATTU 300 mAh 2S"),
    (1, "Placa base", "Aluminio 6061, 80 × 68 × 2 mm", ("placa base",), ""),
    (1, "Carcasa", "PLA impreso: paredes y barra de sensores", ("pared", "barra de sensores"), "color del robot"),
    (1, "Pala", "Acero inoxidable de 1,5 mm, 98 × 30 mm a 34°", ("pala",), "arista a 0,8 mm del suelo"),
    (1, "Patín trasero", "PTFE Ø8 mm", ("patin",), ""),
    (1, "Cableado", "Silicona 26-28 AWG", ("cableado",), ""),
    (1, "Tornillería", "M2 inox", ("tornilleria",), ""),
    (1, "Lastre", "Aleación de tungsteno W-Ni-Fe (18 g/cm³)", ("lastre",),
     "dimensionado para cerrar 500 g con el CdM 4 mm tras el eje"),
]


def bom_md(M, cdm, I, total, m_w, largo_w, eje, trans):
    filas, suma = [], 0.0
    cubiertas = set()
    for qty, comp, ref, claves, nota in BOM:
        if claves is None:
            m = 2 * mr.MASA_RUEDA
        else:
            sel = [p for p in mr.piezas if p["m"] > 0 and any(p["n"].startswith(k) for k in claves)]
            cubiertas.update(id(p) for p in sel)
            m = sum(p["m"] for p in sel)
        suma += m
        filas.append(f"| {qty} | {comp} | {ref} | {m * 1000:.1f} | {nota} |")
    sueltas = [p["n"] for p in mr.piezas if p["m"] > 0 and id(p) not in cubiertas]
    assert not sueltas, f"piezas con masa fuera del BOM: {sueltas}"
    assert abs(suma - mr.MASA_TOTAL) < 1e-6, f"el BOM suma {suma * 1000:.2f} g"
    c = total["c"]
    return f"""# Gelatina Nuclear: hardware

> Generado por `hardware/genera_proto.py` desde `hardware/modelo_robot.py`.
> Cambia las piezas allí y regenera: el PROTO de Webots sale de los mismos datos.

Configuración típica de competición de mini-sumo, elegida para que coincida
con lo que el proyecto ya asumía: motor N20 con reductora, puente en H,
ruedas de 42 mm, 5 sensores de distancia al frente, 4 de línea en las
esquinas, IMU y pulsador de arranque. **Si tus piezas reales son otras,
cámbialas en `modelo_robot.py` y regenera.**

## Lista de materiales

| Cant. | Componente | Referencia | Masa total (g) | Notas |
|---|---|---|---|---|
{chr(10).join(filas)}
| | **Total** | | **{suma * 1000:.1f}** | reglamento: ≤ 500 g |

## Propiedades físicas (las que usa Webots)

- Centro de masas del robot completo: x = {c[0] * 1000:+.1f} mm, y = {c[1] * 1000:+.1f} mm,
  z = {c[2] * 1000:.1f} mm. Queda {-(c[0] + 0.010) * 1000:.1f} mm por detrás del eje de las ruedas.
- Cuerpo sin ruedas: {M * 1000:.1f} g; inercia respecto a su CdM (kg·m²):
  Ixx = {I[0][0]:.3e}, Iyy = {I[1][1]:.3e}, Izz = {I[2][2]:.3e}.
- Rueda: {mr.MASA_RUEDA * 1000:.0f} g; inercia respecto al eje {eje:.2e} kg·m², transversal {trans:.2e} kg·m².
- Lastre: {m_w * 1000:.1f} g de tungsteno, placa de {largo_w * 1000:.1f} × 60 × 8 mm en el suelo del chasis.
- Motor #3063: referencia de fabricante650rpm,0.74kg·cm,1.5A a6V.
  El HAL calcula el par electrico, las perdidas y la tension; ver `real/parameters.json`.
  Los limites Webots {mr.MAX_VEL:.1f}rad/s y {mr.MAX_TORQUE:.4f}N·m son techos numericos, no prestaciones del motor.

## Limitaciones conocidas del modelo

- El motor usa control por par electrico en el HAL. No se modelan temperatura ni inductancia.
- La inercia del rotor reflejada se estima geometricamente y se aleatoriza; falta medirla.
- A menos de ~2 cm del canto del dohyo, el contacto cilindro-cilindro de ODE
  empuja la rueda hacia fuera (verificado con una prueba A/B).

## Fuentes

- Motor: https://www.pololu.com/product/3063/specs
- VL53L0X: https://www.pololu.com/product/2490/specs
- QTR-1A: https://www.pololu.com/product/958
- LiPo 2S 300 mAh: TATTU 45C XT30, 46 × 16 × 14 mm y 20 g según el fabricante.
"""


def main():
    m_w, largo_w = mr.dimensiona_lastre()
    M, cdm, I = mr.propiedades(mr.piezas)
    eje, trans = mr.rueda_inercia()
    mt = M + 2 * mr.MASA_RUEDA
    ct = [(M * cdm[i] + 2 * mr.MASA_RUEDA * (-0.010, 0.0, 0.021)[i]) / mt for i in range(3)]
    total = {"m": mt, "c": ct}
    pala = mr.pala_colision()
    (mr.ROOT / "webots/protos/GelatinaNuclear.proto").write_text(
        proto(M, cdm, I, eje, trans, pala, total), encoding="utf-8")
    (mr.ROOT / "hardware/BOM.md").write_text(
        bom_md(M, cdm, I, total, m_w, largo_w, eje, trans), encoding="utf-8")
    print(f"masa {mt * 1000:.1f} g | CdM ({ct[0] * 1000:+.1f}, {ct[1] * 1000:+.1f}, {ct[2] * 1000:.1f}) mm"
          f" | lastre {m_w * 1000:.1f} g ({largo_w * 1000:.1f} mm)"
          f" | motor {mr.MAX_VEL:.1f} rad/s {mr.MAX_TORQUE:.4f} N*m | pala colision {pala[1] * 1000:.1f} mm")


if __name__ == "__main__":
    main()
