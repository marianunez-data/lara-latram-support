"""Entrypoint with dual personality:
- On Hugging Face Spaces (SPACE_ID set): gradio-native launch, the path the
  ZeroGPU runtime inspects for the @spaces.GPU contract (the contract itself
  is wired inside src/app/api.py as a hidden button).
- Locally / Docker / other clouds: full FastAPI stack via uvicorn
  (chat + /ask + /health + /report).

CPU-only by design: the embedding model is pinned to CPU in ingest.py, which
is the correct place for it — patching torch here interferes with the
ZeroGPU shim's own registration.
"""

import os

if os.getenv("SPACE_ID"):
    from src.app.api import demo

    demo.queue(default_concurrency_limit=4).launch(
        server_name="0.0.0.0", server_port=7860
    )
else:
    import uvicorn
    from src.app.api import app

    if __name__ == "__main__":
        uvicorn.run(app, host="0.0.0.0", port=7860)
