"""
ciclo.py -- una vuelta del ciclo de aprendizaje con retroalimentacion humana.

    votos del usuario -> modelo de recompensa -> CMA-ES en la GPU (aptitud
    simulada + recompensa humana) -> campeon -> comparaciones A/B nuevas
    contra la version de partida -> liga y direccion de mejora -> votos...

Cada vuelta deja preguntas nuevas en la interfaz (python -m ml servidor).
Cuantos mas votos, mas pesa la opinion del usuario en la siguiente vuelta.
"""

from __future__ import annotations


def vuelta(generaciones: int = 60, poblacion: int = 384, log=print) -> dict:
    from .es import entrenar
    from .feedback import genera_pares
    from .liga import actualiza
    from .recompensa import entrena

    entrena(log=log)
    r = entrenar(generaciones, poblacion, log=log)
    genera_pares(r["candidato"], r["config"]["desde"], log=log)
    liga = actualiza(log=log)
    log("[ciclo] listo. Vota las comparaciones nuevas en http://localhost:8765 "
        "y vuelve a ejecutar `python -m ml ciclo`.")
    return {"entrenamiento": r, "liga": liga}
