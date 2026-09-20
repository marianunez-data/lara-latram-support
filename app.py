"""Entrypoint with dual personality:
- On Hugging Face Spaces (SPACE_ID set): gradio-native launch. ZeroGPU accepts
  the Space only after the `spaces` client posts its startup report, and that
  report is sent from inside Blocks.launch(). So launch() must be the first
  thing that opens port 7860.
- Locally / Docker / other clouds: full FastAPI stack via uvicorn
  (chat + /ask + /health + /report).

SSR is switched off on Spaces on purpose. With SSR on, gradio spawns a Node
server. Combined with mount_gradio_app() at import time, that Node process
took port 7860 before launch() ran, pushed the real app to 7861, and made the
Space look "up" before the ZeroGPU report existed. Result: the runtime error
"No @spaces.GPU function detected during startup".

CPU-only by design: the embedding model is pinned to CPU in ingest.py.
"""
import os

if os.getenv("SPACE_ID"):
    # Must be set BEFORE gradio is imported anywhere.
    os.environ["GRADIO_SSR_MODE"] = "false"

    from src.app.api import demo

    demo.queue(default_concurrency_limit=4).launch(
        server_name="0.0.0.0", server_port=7860, ssr_mode=False)
else:
    import uvicorn

    from src.app.api import app

    if __name__ == "__main__":
        uvicorn.run(app, host="0.0.0.0", port=7860)
