"""
PASO 2 — Las herramientas del agente.

Un agente es un LLM que puede decidir usar herramientas. Aquí definimos tres:

  - buscar_documentacion  → RAG sobre las políticas de la tienda (paso 1)
  - consultar_pedidos     → SQL sobre la base de datos de pedidos
  - enviar_email          → acción con consecuencias: pide TU aprobación antes

El LLM no ve el código de cada función. Solo ve su nombre, sus parámetros y
el docstring (el texto entre comillas triples). Por eso el docstring tiene que
explicar muy bien CUÁNDO usar cada herramienta: es un prompt más.

Ejecuta:  python paso2_herramientas.py   (prueba las herramientas sin agente)
"""
import sqlite3

from langchain_core.tools import tool
from langgraph.types import interrupt

from paso1_rag import buscar


@tool
def buscar_documentacion(pregunta: str) -> str:
    """Busca en la documentación oficial de Pedalea: devoluciones, envíos,
    garantía, formas de pago y preguntas frecuentes. Úsala SIEMPRE antes de
    responder sobre políticas o condiciones, en vez de suponer."""
    resultados = buscar(pregunta, k=3)
    return "\n\n---\n\n".join(f"[Fuente: {r['fuente']}]\n{r['texto']}" for r in resultados)


@tool
def consultar_pedidos(email_cliente: str) -> str:
    """Devuelve los pedidos de un cliente a partir de su email: producto,
    importe, estado, fecha y días que lleva en ese estado. Úsala cuando el
    cliente pregunte por SUS pedidos."""
    conexion = sqlite3.connect("tienda.db")
    filas = conexion.execute(
        """
        SELECT p.id, p.producto, p.importe, p.estado, p.fecha_pedido, p.dias_en_estado, c.nombre
        FROM pedidos p
        JOIN clientes c ON c.id = p.cliente_id
        WHERE c.email = ?            -- el "?" evita inyección SQL: nunca metas texto del usuario con f-strings
        ORDER BY p.fecha_pedido DESC
        """,
        (email_cliente.strip().lower(),),
    ).fetchall()
    conexion.close()

    if not filas:
        return f"No hay ningún cliente con el email {email_cliente}."
    lineas = [f"Cliente: {filas[0][6]}"]
    for id_, producto, importe, estado, fecha, dias, _ in filas:
        lineas.append(f"- Pedido {id_}: {producto} | {importe:.2f} € | {estado} "
                      f"(desde hace {dias} días) | pedido el {fecha}")
    return "\n".join(lineas)


@tool
def enviar_email(destinatario: str, asunto: str, cuerpo: str) -> str:
    """Envía un email al cliente. Úsala solo cuando la respuesta esté completa.
    Un humano del equipo de soporte revisará el email antes de que salga."""
    # interrupt() PAUSA todo el agente y le pasa este borrador a un humano.
    # El agente se queda esperando hasta que alguien responda "si" o "no".
    decision = interrupt({"destinatario": destinatario, "asunto": asunto, "cuerpo": cuerpo})

    # Desde el frontend (app.py) llega un diccionario: {"aprobado": True, "cuerpo": texto_editado}
    if isinstance(decision, dict) and decision.get("aprobado"):
        # Aquí iría el envío real (SMTP, Gmail API, n8n...). Lo simulamos.
        return f"Email enviado a {destinatario} (revisado y editado por un humano)."
    # Desde la terminal (paso3) llega un texto: "si" o qué cambiar
    if str(decision).strip().lower() in ("si", "sí", "s", "yes", "y"):
        return f"Email enviado a {destinatario}."
    return f"El humano NO aprobó el email. Motivo o indicaciones: {decision}"


HERRAMIENTAS = [buscar_documentacion, consultar_pedidos, enviar_email]


if __name__ == "__main__":
    print(consultar_pedidos.invoke({"email_cliente": "marcos@ejemplo.com"}))
    print()
    print(buscar_documentacion.invoke({"pregunta": "¿Cuánto tarda el reembolso?"})[:400], "...")
