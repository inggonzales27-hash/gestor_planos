"""
Agrega columnas nuevas a una base de datos ya existente (sqlite local o Postgres/Neon
en producción) y rellena el campo "proyecto" a partir del código de cada plano.

Uso:
    python -m app.migrate_schema
"""
from sqlalchemy import inspect, text

from .database import Base, engine, SessionLocal
from .models import Plano, detectar_proyecto


def agregar_columnas_faltantes():
    inspector = inspect(engine)
    columnas_actuales = {c["name"] for c in inspector.get_columns("planos")}
    nuevas = {
        "proyecto": "VARCHAR",
        "responsable": "VARCHAR",
        "revisor": "VARCHAR",
    }
    with engine.begin() as conn:
        for nombre, tipo in nuevas.items():
            if nombre not in columnas_actuales:
                conn.execute(text(f"ALTER TABLE planos ADD COLUMN {nombre} {tipo}"))
                print(f"Columna agregada: {nombre}")


def backfill_proyecto(db):
    planos = db.query(Plano).all()
    actualizados = 0
    for plano in planos:
        proyecto = detectar_proyecto(plano.codigo)
        if plano.proyecto != proyecto:
            plano.proyecto = proyecto
            actualizados += 1
    db.commit()
    print(f"Proyecto asignado/actualizado en {actualizados} planos")


def main():
    Base.metadata.create_all(bind=engine)
    agregar_columnas_faltantes()
    db = SessionLocal()
    try:
        backfill_proyecto(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
