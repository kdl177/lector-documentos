import json
import math
import os
import sys
import threading
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote

PUERTO = int(os.environ.get("LECTOR_PUERTO", "8413"))
OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODELO = os.environ.get("LECTOR_MODELO", "qwen3:14b")
MODELO_EMB = os.environ.get("LECTOR_MODELO_EMBEDDINGS", "nomic-embed-text")
CARPETA = Path(__file__).parent
DOCS = Path(os.environ.get("LECTOR_CARPETA", CARPETA / "documentos"))
INDICE = CARPETA / "indice.json"
HTML = CARPETA / "index.html"
EXTENSIONES = {".pdf", ".txt", ".md"}
TROZO, SOLAPE, CONTEXTO = 900, 150, 6
MAX_SUBIDA = 200 * 1024**2

estado = {"indexando": False, "hecho": 0, "total": 0, "error": None}
cerrojo = threading.Lock()


def ollama(ruta: str, datos: dict, espera=600) -> dict:
    # Ambos modelos se quedan cargados media hora: recargarlos entre preguntas tardaba minutos.
    datos = {"keep_alive": "30m", **datos}
    pet = urllib.request.Request(f"{OLLAMA}{ruta}", data=json.dumps(datos).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(pet, timeout=espera) as r:
        return json.load(r)


def vectores(textos: list[str], tipo: str) -> list[list[float]]:
    # nomic-embed-text distingue documentos y preguntas por este prefijo.
    salida = ollama("/api/embed", {"model": MODELO_EMB, "input": [f"{tipo}: {t}" for t in textos]})["embeddings"]
    return [[x / (math.sqrt(sum(y * y for y in v)) or 1) for x in v] for v in salida]


def paginas(ruta: Path) -> list[tuple[int, str]]:
    if ruta.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        return [(i + 1, p.extract_text() or "") for i, p in enumerate(PdfReader(ruta).pages)]
    return [(1, ruta.read_text(encoding="utf-8", errors="replace"))]


def trocear(texto: str) -> list[str]:
    texto = " ".join(texto.split())
    if len(texto) <= TROZO:
        return [texto] if texto else []
    return [texto[i:i + TROZO] for i in range(0, len(texto) - SOLAPE, TROZO - SOLAPE)]


def leer_indice() -> dict:
    try:
        return json.loads(INDICE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def documentos() -> list[Path]:
    DOCS.mkdir(exist_ok=True)
    return sorted(p for p in DOCS.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONES)


def indexar():
    with cerrojo:
        if estado["indexando"]:
            return
        estado.update(indexando=True, error=None)
    try:
        viejo = leer_indice()
        nuevo = {}
        pendientes = []
        for p in documentos():
            firma = f"{p.stat().st_size}-{int(p.stat().st_mtime)}"
            if viejo.get(p.name, {}).get("firma") == firma:
                nuevo[p.name] = viejo[p.name]
            else:
                pendientes.append((p, firma))
        estado.update(hecho=0, total=len(pendientes))
        for p, firma in pendientes:
            trozos = [(n, t) for n, texto in paginas(p) for t in trocear(texto)]
            vecs = []
            for i in range(0, len(trozos), 32):
                vecs += vectores([t for _, t in trozos[i:i + 32]], "search_document")
            nuevo[p.name] = {"firma": firma, "trozos": [{"pag": n, "texto": t, "v": v} for (n, t), v in zip(trozos, vecs)]}
            estado["hecho"] += 1
            # Se guarda tras cada documento: si se corta, no se pierde lo hecho.
            INDICE.write_text(json.dumps({**viejo, **nuevo}), encoding="utf-8")
        INDICE.write_text(json.dumps(nuevo), encoding="utf-8")
    except Exception as e:
        estado["error"] = f"No se pudo indexar: {e}"
    finally:
        estado["indexando"] = False


def preguntar(pregunta: str) -> dict:
    indice = leer_indice()
    trozos = [(doc, t) for doc, d in indice.items() for t in d["trozos"]]
    if not trozos:
        return {"respuesta": "Todavía no hay documentos indexados. Añade alguno y pulsa Indexar.", "fuentes": []}
    q = vectores([pregunta], "search_query")[0]
    mejores = sorted(trozos, key=lambda dt: -sum(a * b for a, b in zip(q, dt[1]["v"])))[:CONTEXTO]
    contexto = "\n\n".join(f"[{i + 1}] {doc}, página {t['pag']}:\n{t['texto']}" for i, (doc, t) in enumerate(mejores))
    prompt = (
        "Responde a la pregunta usando solo los fragmentos de documentos de abajo. "
        "Cita cada dato con el número del fragmento entre corchetes, por ejemplo [2]. "
        "Si los fragmentos no contienen la respuesta, dilo claramente y no la inventes. "
        "Responde en el idioma de la pregunta, en texto plano, sin markdown.\n\n"
        f"FRAGMENTOS:\n{contexto}\n\nPREGUNTA: {pregunta}"
    )
    r = ollama("/api/chat", {
        "model": MODELO,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {"temperature": 0.1, "num_ctx": 8192},
    })
    return {
        "respuesta": r["message"]["content"].replace("**", "").strip(),
        "fuentes": [{"n": i + 1, "doc": doc, "pag": t["pag"], "texto": t["texto"][:300]} for i, (doc, t) in enumerate(mejores)],
    }


class Manejador(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def responder(self, codigo: int, datos, tipo="application/json"):
        cuerpo = datos if isinstance(datos, bytes) else json.dumps(datos, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", f"{tipo}; charset=utf-8" if tipo.startswith(("text/", "application/json")) else tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        if self.path == "/":
            return self.responder(200, HTML.read_bytes(), "text/html")
        if self.path == "/estado":
            indice = leer_indice()
            docs = [{"nombre": p.name, "url": f"/doc/{quote(p.name)}", "indexado": p.name in indice,
                     "trozos": len(indice.get(p.name, {}).get("trozos", []))} for p in documentos()]
            return self.responder(200, {**estado, "documentos": docs, "carpeta": str(DOCS.resolve())})
        if self.path.startswith("/doc/"):
            nombre = Path(unquote(self.path.removeprefix("/doc/").split("#")[0])).name
            ruta = DOCS / nombre
            if ruta.suffix.lower() in EXTENSIONES and ruta.is_file():
                tipo = "application/pdf" if ruta.suffix.lower() == ".pdf" else "text/plain"
                return self.responder(200, ruta.read_bytes(), tipo)
        self.responder(404, {"error": "No existe"})

    def do_POST(self):
        # Solo desde la propia página: otra web abierta en el navegador no puede usarlo.
        if self.headers.get("Origin") not in (None, f"http://127.0.0.1:{PUERTO}", f"http://localhost:{PUERTO}"):
            return self.responder(403, {"error": "Origen no permitido"})
        tam = int(self.headers.get("Content-Length") or 0)
        if self.path == "/subir":
            nombre = Path(unquote(self.headers.get("X-Nombre", ""))).name
            if Path(nombre).suffix.lower() not in EXTENSIONES:
                return self.responder(400, {"error": "Solo PDF, TXT o MD."})
            if not 0 < tam <= MAX_SUBIDA:
                return self.responder(400, {"error": "El archivo está vacío o pasa de 200 MB."})
            DOCS.mkdir(exist_ok=True)
            (DOCS / nombre).write_bytes(self.rfile.read(tam))
            return self.responder(200, {"ok": True})
        if self.path == "/indexar":
            threading.Thread(target=indexar, daemon=True).start()
            return self.responder(200, {"ok": True})
        if self.path == "/preguntar":
            try:
                pregunta = str(json.loads(self.rfile.read(min(tam, 20_000)) or b"{}").get("pregunta", "")).strip()[:2000]
            except json.JSONDecodeError:
                pregunta = ""
            if not pregunta:
                return self.responder(400, {"error": "Escribe una pregunta."})
            try:
                return self.responder(200, preguntar(pregunta))
            except Exception as e:
                return self.responder(502, {"error": f"No se pudo hablar con Ollama ({OLLAMA}). ¿Está abierto y tiene {MODELO} y {MODELO_EMB}? Detalle: {e}"})
        self.responder(404, {"error": "No existe"})


def calentar():
    try:
        vectores(["hola"], "search_query")
        ollama("/api/generate", {"model": MODELO})  # sin prompt: solo lo carga
    except Exception:
        pass  # Sin Ollama la página ya lo explica al preguntar.


def main():
    servidor = ThreadingHTTPServer(("127.0.0.1", PUERTO), Manejador)
    url = f"http://127.0.0.1:{PUERTO}"
    print(f"Lector de documentos en {url}  (Ctrl+C para cerrar)\nCarpeta: {DOCS.resolve()}")
    # La primera carga del modelo de búsqueda puede tardar: se hace mientras se abre la página.
    threading.Thread(target=calentar, daemon=True).start()
    if "--sin-navegador" not in sys.argv:
        webbrowser.open(url)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
