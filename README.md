# Lector de documentos · SIMBAI Lab

Le das tus PDF y le preguntas en lenguaje normal: "¿cuál es el plazo de preaviso?", "¿qué cubre la garantía?". Responde citando el documento y la página de donde sale cada dato, y si la respuesta no está en tus documentos, te lo dice en vez de inventarla. Todo pasa en tu ordenador con [Ollama](https://ollama.com): nada se sube a internet.

- **PDF, TXT y MD.** Arrastras los archivos o los copias a la carpeta `documentos/`.
- **Citas con página.** Cada `[n]` de la respuesta lleva a su fragmento, y el enlace abre el PDF en esa página.
- **Solo reindexa lo que cambia.** Los documentos ya leídos no se vuelven a procesar.

Los PDF escaneados como imagen no tienen texto que leer: pásalos antes por un OCR.

## Instalar (Windows)

1. Python 3.11 o superior.
2. Doble clic en `instalar.bat`.
3. [Ollama](https://ollama.com) y los dos modelos:
   ```
   ollama pull qwen3:14b
   ollama pull nomic-embed-text
   ```
4. Doble clic en `iniciar.bat`: se abre en `http://127.0.0.1:8413`.

La primera pregunta tarda más: Ollama carga los modelos en memoria. Con menos de 12 GB de memoria de vídeo, usa `qwen3:8b` (`set LECTOR_MODELO=qwen3:8b` antes de `iniciar.bat`).

## Configuración

| Variable | Por defecto |
|---|---|
| `LECTOR_PUERTO` | `8413` |
| `LECTOR_CARPETA` | `documentos/` junto al programa |
| `OLLAMA_URL` | `http://localhost:11434` |
| `LECTOR_MODELO` | `qwen3:14b` |
| `LECTOR_MODELO_EMBEDDINGS` | `nomic-embed-text` |

## Licencia

MIT. Puedes usar, copiar, modificar y distribuir el código libremente, también con fines comerciales, manteniendo el aviso de autoría. Ver [LICENSE](LICENSE).
