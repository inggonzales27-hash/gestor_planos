"""
Importa el LOG de Documentos Contingencia.xlsx a la base de datos del gestor.
Uso:
    python -m app.migrate_excel "C:\\ruta\\LOG de Documentos Contingencia.xlsx"

Usa inserciones en bloque (bulk) para que funcione bien contra bases remotas
con latencia de red (Neon, Render, etc.), donde una inserción fila por fila
sería demasiado lenta.
"""
import sys
from datetime import date, datetime

import pandas as pd

from .database import Base, engine, SessionLocal
from .models import Plano, HistorialEstado, Usuario


def to_date(value):
    if pd.isna(value):
        return None
    if isinstance(value, (datetime, date)):
        return value.date() if isinstance(value, datetime) else value
    return None


def to_str(value):
    if pd.isna(value):
        return None
    return str(value).strip()


def migrar_usuarios(xls_path, db):
    df = pd.read_excel(xls_path, sheet_name="DATOS", usecols="A:I")
    df.columns = [
        "usuario", "entidad", "nombres", "apellidos", "dni",
        "cargo", "fecha_ingreso", "fecha_nacimiento", "correo",
    ]
    existentes = {r[0] for r in db.query(Usuario.usuario)}

    nuevos = []
    vistos = set()
    for _, row in df.iterrows():
        usuario = to_str(row["usuario"])
        if not usuario or usuario in existentes or usuario in vistos:
            continue
        vistos.add(usuario)
        nuevos.append({
            "usuario": usuario,
            "entidad": to_str(row["entidad"]),
            "nombres": to_str(row["nombres"]),
            "apellidos": to_str(row["apellidos"]),
            "correo": to_str(row["correo"]),
            "cargo": to_str(row["cargo"]),
        })

    if nuevos:
        db.bulk_insert_mappings(Usuario, nuevos)
        db.commit()
    print(f"Usuarios importados: {len(nuevos)}")


def migrar_planos(xls_path, db):
    df = pd.read_excel(xls_path, sheet_name="LOG_Planos")
    df.columns = [
        "codificacion_contrato", "ref", "edificio", "etapa", "tipo_documento",
        "esp", "tipo_archivo", "nivel", "ubicacion", "correlativo",
        "codigo_plano", "detalle", "revision_actual", "fecha_version",
        "formato_plano", "escala_plano", "revision_formal", "estado",
        "estatus_elaboracion", "estatus_envio", "codigo_nuevo",
        "codigo_origen_anterior",
    ]
    existentes = {r[0] for r in db.query(Plano.codigo)}

    nuevos = []
    vistos = set()
    for _, row in df.iterrows():
        codigo = to_str(row["codigo_plano"])
        if not codigo or codigo in existentes or codigo in vistos:
            continue
        vistos.add(codigo)
        nuevos.append({
            "codigo": codigo,
            "edificio": to_str(row["edificio"]),
            "etapa": to_str(row["etapa"]),
            "tipo_documento": to_str(row["tipo_documento"]),
            "especialidad": to_str(row["esp"]),
            "tipo_archivo": to_str(row["tipo_archivo"]),
            "nivel": to_str(row["nivel"]),
            "ubicacion": to_str(row["ubicacion"]),
            "correlativo": to_str(row["correlativo"]),
            "detalle": to_str(row["detalle"]),
            "revision_actual": to_str(row["revision_actual"]),
            "fecha_version": to_date(row["fecha_version"]),
            "formato_plano": to_str(row["formato_plano"]),
            "escala_plano": to_str(row["escala_plano"]),
            "revision_formal": to_str(row["revision_formal"]),
            "estado": to_str(row["estado"]),
            "estatus_elaboracion": to_str(row["estatus_elaboracion"]),
            "estatus_envio": to_str(row["estatus_envio"]),
            "codigo_nuevo": to_str(row["codigo_nuevo"]),
            "codigo_origen_anterior": to_str(row["codigo_origen_anterior"]),
        })

    if nuevos:
        db.bulk_insert_mappings(Plano, nuevos)
        db.commit()
    print(f"Planos importados: {len(nuevos)}")

    # Trae los ids recién asignados para poder crear el historial inicial
    codigos_nuevos = [n["codigo"] for n in nuevos]
    planos_por_codigo = {}
    if codigos_nuevos:
        for pid, codigo, estatus_elab, estado, estatus_envio, fecha in db.query(
            Plano.id, Plano.codigo, Plano.estatus_elaboracion, Plano.estado, Plano.estatus_envio, Plano.fecha_version
        ).filter(Plano.codigo.in_(codigos_nuevos)):
            planos_por_codigo[codigo] = (pid, estatus_elab, estado, estatus_envio, fecha)

    eventos = []
    for codigo, (pid, estatus_elab, estado, estatus_envio, fecha) in planos_por_codigo.items():
        eventos.append({
            "plano_id": pid,
            "fecha": fecha,
            "tipo_proceso": "ELABORACION",
            "estado": estatus_elab or estado,
            "comentario": "Estado inicial migrado desde LOG_Planos",
        })
        if estatus_envio:
            eventos.append({
                "plano_id": pid,
                "fecha": fecha,
                "tipo_proceso": "ENVIO",
                "estado": estatus_envio,
                "comentario": "Estado inicial migrado desde LOG_Planos",
            })

    if eventos:
        db.bulk_insert_mappings(HistorialEstado, eventos)
        db.commit()
    print(f"Eventos de historial inicial creados: {len(eventos)}")


def enriquecer_con_estatus_planos(xls_path, db):
    """Agrega links y eventos de historial desde la hoja EstatusPlanos, matcheando por código base."""
    df = pd.read_excel(xls_path, sheet_name="EstatusPlanos", header=1)
    df.columns = [
        "especialidad", "nivel", "num", "version_actual", "cod", "codigo_base",
        "version", "fecha_revision", "descripcion", "link_wip_acc",
        "responsable_elaborar", "estado_elaboracion", "fecha_estado",
        "fecha_entrega_proyectada", "comentario_elaborador", "estado_envio",
        "responsable_revisar", "link_wip_envio", "comentario_revisor",
        "codigo_aconex", "id_flujo_acc", "fecha_envio_cd", "fecha_envio_anin",
        "fecha_vencimiento", "fecha_respuesta", "link_aprobado",
    ]

    planos_por_codigo = {codigo: (pid, link) for pid, codigo, link in db.query(Plano.id, Plano.codigo, Plano.link_archivo)}

    eventos = []
    links_a_actualizar = {}  # plano_id -> link
    matched = 0
    for _, row in df.iterrows():
        codigo_base = to_str(row["codigo_base"])
        if not codigo_base or codigo_base not in planos_por_codigo:
            continue
        plano_id, link_actual = planos_por_codigo[codigo_base]

        link = to_str(row["link_aprobado"]) or to_str(row["link_wip_envio"]) or to_str(row["link_wip_acc"])
        if link and not link_actual and plano_id not in links_a_actualizar:
            links_a_actualizar[plano_id] = link

        fila_eventos = [
            ("ELABORACION", row["fecha_estado"], row["estado_elaboracion"], row["responsable_elaborar"], row["comentario_elaborador"], row["link_wip_acc"]),
            ("ENVIO", row["fecha_envio_cd"], "ENVIADO A CD", row["responsable_revisar"], row["comentario_revisor"], row["link_wip_envio"]),
            ("ENVIO", row["fecha_envio_anin"], "ENVIADO A ANIN", row["responsable_revisar"], None, row["link_wip_envio"]),
            ("ENVIO", row["fecha_respuesta"], row["estado_envio"], row["responsable_revisar"], None, row["link_aprobado"]),
        ]
        for tipo_proceso, fecha_raw, estado_raw, responsable_raw, comentario_raw, link_raw in fila_eventos:
            fecha = to_date(fecha_raw)
            estado = to_str(estado_raw)
            if not fecha or not estado:
                continue
            eventos.append({
                "plano_id": plano_id,
                "fecha": fecha,
                "tipo_proceso": tipo_proceso,
                "estado": estado,
                "responsable": to_str(responsable_raw),
                "comentario": to_str(comentario_raw),
                "link_archivo": to_str(link_raw),
            })
        matched += 1

    if links_a_actualizar:
        db.bulk_update_mappings(
            Plano,
            [{"id": pid, "link_archivo": link} for pid, link in links_a_actualizar.items()],
        )
    if eventos:
        db.bulk_insert_mappings(HistorialEstado, eventos)
    db.commit()
    print(f"Planos enriquecidos desde EstatusPlanos: {matched} (eventos: {len(eventos)}, links nuevos: {len(links_a_actualizar)})")


def main():
    if len(sys.argv) < 2:
        print("Uso: python -m app.migrate_excel <ruta al xlsx>")
        sys.exit(1)

    xls_path = sys.argv[1]
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        migrar_usuarios(xls_path, db)
        migrar_planos(xls_path, db)
        enriquecer_con_estatus_planos(xls_path, db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
