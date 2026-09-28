"""
PASO 4 — Frontend: bandeja de entrada de soporte con Streamlit.

Streamlit convierte un script de Python en una web. Truco clave para entenderlo:
CADA VEZ que pulsas un botón, Streamlit vuelve a ejecutar este archivo de arriba abajo.
Por eso lo que tiene que sobrevivir entre clics (el agente y su memoria) se guarda con
@st.cache_resource, y lo que eliges (el email abierto) en st.session_state.

Ejecuta:  streamlit run app.py
"""
import runpy
import sqlite3

import streamlit as st
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from paso3_agente import crear_agente

st.set_page_config(page_title="Soporte · Pedalea", page_icon="🚲", layout="wide")

ETIQUETAS = {
    "nuevo": "🔵 Nuevo",
    "pendiente": "🟠 Pendiente de aprobar",
    "revisar": "🟣 Necesita revisión humana",
    "enviado": "🟢 Enviado",
    "descartado": "⚪ Descartado",
}
ICONOS = {"buscar_documentacion": "📚", "consultar_pedidos": "🗄️", "enviar_email": "📧"}


# ---------------------------------------------------------------------------
# Datos y agente
# ---------------------------------------------------------------------------
@st.cache_resource
def obtener_agente():
    """Se crea UNA sola vez: si no, el agente perdería su memoria en cada clic."""
    return crear_agente()


def consulta(sql: str, parametros: tuple = ()) -> list:
    with sqlite3.connect("tienda.db") as con:
        con.row_factory = sqlite3.Row          # filas accesibles por nombre: fila["asunto"]
        return con.execute(sql, parametros).fetchall()


def actualizar_email(id_: int, estado: str, respuesta: str | None = None) -> None:
    consulta("UPDATE emails SET estado = ?, respuesta = COALESCE(?, respuesta) WHERE id = ?",
             (estado, respuesta, id_))


def config_de(id_: int) -> dict:
    return {"configurable": {"thread_id": f"email-{id_}"}}   # cada email = una conversación


def procesar(id_: int, resultado: dict, cuerpo_enviado: str | None = None) -> None:
    """Mira cómo ha terminado el agente y actualiza el estado del email."""
    if resultado.get("__interrupt__"):
        actualizar_email(id_, "pendiente")
        return
    envios = [m for m in resultado["messages"]
              if isinstance(m, ToolMessage) and m.name == "enviar_email"]
    if envios and envios[-1].content.startswith("Email enviado"):
        actualizar_email(id_, "enviado", cuerpo_enviado)
    else:
        actualizar_email(id_, "revisar")       # el agente no preparó respuesta: que lo mire una persona


def analizar(email) -> None:
    texto = (
        "Ha llegado este email a soporte.\n"
        f"De: {email['remitente']}\nAsunto: {email['asunto']}\n\n"
        f"<email_del_cliente>\n{email['cuerpo']}\n</email_del_cliente>\n\n"
        "Investiga el caso y prepara la respuesta al cliente con enviar_email."
    )
    procesar(email["id"], agente.invoke({"messages": [("user", texto)]}, config_de(email["id"])))


def mostrar_razonamiento(mensajes: list) -> None:
    """Enseña cada herramienta que usó el agente, con sus parámetros y su resultado."""
    resultados = {m.tool_call_id: m.content for m in mensajes if isinstance(m, ToolMessage)}
    for m in mensajes:
        if not isinstance(m, AIMessage):
            continue
        for llamada in m.tool_calls:
            icono = ICONOS.get(llamada["name"], "🔧")
            with st.expander(f"{icono} {llamada['name']}"):
                st.caption("Parámetros")
                st.json(llamada["args"])
                if llamada["id"] in resultados:
                    st.caption("Resultado")
                    st.code(resultados[llamada["id"]], language=None, wrap_lines=True)
        if m.content and not m.tool_calls:
            st.info(f"🤖 {m.content}")


agente = obtener_agente()

# ---------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("🚲 Pedalea")
    st.caption("Empresa ficticia · asistente de soporte con RAG + agentes")
    if st.button("🔄 Reiniciar demo", width="stretch"):
        runpy.run_path("crear_base_datos.py")    # recrea la base de datos y los emails de ejemplo
        st.cache_resource.clear()                # borra la memoria del agente
        st.session_state.clear()
        st.rerun()

# ---------------------------------------------------------------------------
# Cabecera con métricas
# ---------------------------------------------------------------------------
emails = consulta("SELECT * FROM emails ORDER BY recibido DESC")
st.title("Bandeja de soporte")
contar = lambda estado: sum(e["estado"] == estado for e in emails)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Nuevos", contar("nuevo"))
c2.metric("Pendientes de aprobar", contar("pendiente"))
c3.metric("Necesitan revisión", contar("revisar"))
c4.metric("Enviados", contar("enviado"))

lista, detalle = st.columns([1, 2], gap="large")

# ---------------------------------------------------------------------------
# Columna izquierda: la lista de emails
# ---------------------------------------------------------------------------
with lista:
    for e in emails:
        with st.container(border=True):
            st.markdown(f"**{e['asunto']}**  \n{e['remitente']} · {e['recibido'][11:]}")
            st.caption(ETIQUETAS[e["estado"]])
            if st.button("Abrir", key=f"abrir-{e['id']}", width="stretch"):
                st.session_state.seleccionado = e["id"]

# ---------------------------------------------------------------------------
# Columna derecha: el email abierto
# ---------------------------------------------------------------------------
with detalle:
    id_sel = st.session_state.get("seleccionado")
    if id_sel is None:
        st.info("👈 Abre un email de la bandeja para empezar.")
        st.stop()

    email = consulta("SELECT * FROM emails WHERE id = ?", (id_sel,))[0]
    config = config_de(email["id"])
    snapshot = agente.get_state(config)
    mensajes = snapshot.values.get("messages", [])

    st.subheader(email["asunto"])
    st.caption(f"De {email['remitente']} · {email['recibido']} · {ETIQUETAS[email['estado']]}")
    with st.container(border=True):
        st.write(email["cuerpo"])

    # --- Nuevo: todavía no lo ha visto el agente
    if email["estado"] == "nuevo":
        if st.button("🤖 Analizar con IA", type="primary"):
            with st.spinner("El asistente está investigando el caso..."):
                analizar(email)
            st.rerun()
        st.stop()

    # --- El razonamiento del agente
    if mensajes:
        st.markdown("#### Qué ha hecho el asistente")
        mostrar_razonamiento(mensajes)

    # --- Pendiente: hay un borrador esperando aprobación
    if email["estado"] == "pendiente":
        if not snapshot.interrupts:
            st.warning("Se perdió la memoria del asistente (¿reiniciaste la app?). Vuelve a analizarlo.")
            if st.button("🤖 Volver a analizar", type="primary"):
                with st.spinner("Analizando..."):
                    analizar(email)
                st.rerun()
            st.stop()

        borrador = snapshot.interrupts[0].value
        st.markdown("#### 📧 Borrador de respuesta")
        st.text_input("Para", borrador["destinatario"], disabled=True)
        st.text_input("Asunto", borrador["asunto"], disabled=True)
        cuerpo = st.text_area("Mensaje (puedes editarlo antes de enviar)", borrador["cuerpo"], height=220)

        b1, b2 = st.columns(2)
        if b1.button("✅ Aprobar y enviar", type="primary", width="stretch"):
            with st.spinner("Enviando..."):
                resultado = agente.invoke(Command(resume={"aprobado": True, "cuerpo": cuerpo}), config)
                procesar(email["id"], resultado, cuerpo_enviado=cuerpo)
            st.rerun()
        if b2.button("🗑️ Descartar", width="stretch"):
            actualizar_email(email["id"], "descartado")
            st.rerun()

        cambios = st.text_input("¿Quieres que lo rehaga? Explica qué cambiar",
                                placeholder="Ej.: más corto y ofrece llamarle por teléfono")
        if st.button("🔁 Pedir cambios", disabled=not cambios):
            with st.spinner("Rehaciendo el borrador..."):
                procesar(email["id"], agente.invoke(Command(resume=cambios), config))
            st.rerun()

    # --- Revisar: el agente no ha querido o no ha podido responder
    elif email["estado"] == "revisar":
        st.warning("El asistente no ha preparado respuesta. Lee su nota de arriba y decide.")
        instrucciones = st.text_input("Dale instrucciones al asistente",
                                      placeholder="Ej.: responde amablemente que no podemos hacer eso")
        c_a, c_b = st.columns(2)
        if c_a.button("💬 Enviar instrucciones", type="primary", disabled=not instrucciones, width="stretch"):
            with st.spinner("Trabajando..."):
                procesar(email["id"], agente.invoke({"messages": [("user", instrucciones)]}, config))
            st.rerun()
        if c_b.button("🗑️ Descartar", width="stretch"):
            actualizar_email(email["id"], "descartado")
            st.rerun()

    elif email["estado"] == "enviado":
        st.success("✅ Respuesta enviada")
        if email["respuesta"]:
            with st.container(border=True):
                st.write(email["respuesta"])

    elif email["estado"] == "descartado":
        st.info("Este email se descartó sin responder.")
