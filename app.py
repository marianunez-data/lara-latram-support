"""Entrypoint with dual personality:
- On Hugging Face Spaces (SPACE_ID set): gradio-native launch (the path
  ZeroGPU inspects for the @spaces.GPU contract). We answer torch's
  "is CUDA available?" probe with False so no library triggers low-level
  CUDA init outside a GPU function.
- Locally / Docker / other clouds: full FastAPI stack via uvicorn
  (chat + /ask + /health + /report).
"""

import os

if os.getenv("SPACE_ID"):
    import spaces  # noqa: F401  MUST precede torch: ZeroGPU's shim

    # instruments torch at its own import; importing torch first blinds it.
    import torch

    torch.cuda.is_available = lambda: False  # CPU-only app, by design

    from src.app.api import demo

    # Known-good launch (matches the configuration that ran successfully).
    # The __main__ guard prevents a second import from starting a duplicate
    # server and colliding on the port.
    if __name__ == "__main__":
        demo.queue(default_concurrency_limit=4).launch(
            server_name="0.0.0.0", server_port=7860
        )
else:
    import uvicorn
    from src.app.api import app

    if __name__ == "__main__":
        uvicorn.run(app, host="0.0.0.0", port=7860)
