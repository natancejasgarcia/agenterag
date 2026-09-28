"""
PASO 1 — RAG: buscar en la documentación de la empresa por significado.

Qué hace este archivo:
  1. Lee los documentos de la carpeta docs/
  2. Los trocea en fragmentos (chunks), uno por cada sección "## ..."
  3. Convierte cada fragmento en un vector con el modelo de embeddings de OpenAI
  4. Guarda todo en indice.json (nuestra "base de datos vectorial" casera)
  5. Busca los fragmentos más parecidos a una pregunta con similitud coseno

No usamos Pinecone ni pgvector a propósito: así ves lo que hacen por dentro.
Una base de datos vectorial es, en el fondo, esto mismo pero rápida y a gran escala.

Ejecuta:  python paso1_rag.py
"""
import json
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()  # carga OPENAI_API_KEY desde el archivo .env

CARPETA_DOCS = Path("docs")
ARCHIVO_INDICE = Path("indice.json")
MODELO_EMBEDDINGS = "text-embedding-3-small"


# ---------------------------------------------------------------------------
# 1. Trocear los documentos
# ---------------------------------------------------------------------------
def trocear_documentos() -> list[dict]:
    """Devuelve una lista de fragmentos: {"fuente": ..., "texto": ...}.

    Cortamos por secciones "## " porque cada sección habla de un solo tema.
    Así, cuando busquemos, recuperamos un trozo con sentido completo.
    """
    fragmentos = []
    for archivo in sorted(CARPETA_DOCS.glob("*.md")):
        contenido = archivo.read_text(encoding="utf-8")
        titulo_doc = contenido.splitlines()[0].lstrip("# ").strip()
        for seccion in contenido.split("\n## ")[1:]:
            fragmentos.append({
                "fuente": archivo.name,
                # Añadimos el título del documento al fragmento: da contexto al embedding
                "texto": f"{titulo_doc} — {seccion.strip()}",
            })
    return fragmentos


# ---------------------------------------------------------------------------
# 2. Convertir texto en vectores (embeddings)
# ---------------------------------------------------------------------------
def embeber(textos: list[str]) -> list[list[float]]:
    """Convierte cada texto en un vector de 1536 números que representa su significado."""
    cliente = OpenAI()
    respuesta = cliente.embeddings.create(model=MODELO_EMBEDDINGS, input=textos)
    return [item.embedding for item in respuesta.data]


# ---------------------------------------------------------------------------
# 3. Crear el índice (se hace una vez, o cada vez que cambian los documentos)
# ---------------------------------------------------------------------------
def crear_indice() -> None:
    fragmentos = trocear_documentos()
    vectores = embeber([f["texto"] for f in fragmentos])
    for fragmento, vector in zip(fragmentos, vectores):
        fragmento["vector"] = vector
    ARCHIVO_INDICE.write_text(json.dumps(fragmentos, ensure_ascii=False), encoding="utf-8")
    print(f"Índice creado con {len(fragmentos)} fragmentos → {ARCHIVO_INDICE}")


# ---------------------------------------------------------------------------
# 4. Buscar: la "R" de RAG (Retrieval)
# ---------------------------------------------------------------------------
def buscar(pregunta: str, k: int = 3) -> list[dict]:
    """Devuelve los k fragmentos más parecidos a la pregunta, con su puntuación."""
    if not ARCHIVO_INDICE.exists():
        crear_indice()
    fragmentos = json.loads(ARCHIVO_INDICE.read_text(encoding="utf-8"))

    matriz = np.array([f["vector"] for f in fragmentos])   # una fila por fragmento
    consulta = np.array(embeber([pregunta])[0])

    # Similitud coseno: 1 = mismo significado, 0 = nada que ver
    similitudes = matriz @ consulta / (np.linalg.norm(matriz, axis=1) * np.linalg.norm(consulta))

    mejores = np.argsort(similitudes)[::-1][:k]              # índices de mayor a menor
    return [
        {"fuente": fragmentos[i]["fuente"], "texto": fragmentos[i]["texto"], "puntuacion": float(similitudes[i])}
        for i in mejores
    ]


if __name__ == "__main__":
    crear_indice()
    while True:
        pregunta = input("\nPregunta sobre la tienda (Enter vacío para salir): ").strip()
        if not pregunta:
            break
        for r in buscar(pregunta):
            print(f"\n[{r['puntuacion']:.2f}] {r['fuente']}\n{r['texto'][:250]}...")
