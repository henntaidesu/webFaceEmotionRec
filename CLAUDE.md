# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Real-time facial emotion recognition web app. A Vue 3 SPA streams webcam frames over a WebSocket to a FastAPI backend, which runs MTCNN face detection + HSEmotion (EfficientNet-B2) emotion classification on the GPU and returns per-face emotion probabilities. A second panel embeds a ComfyUI client (image generation), reached through a Vite dev proxy.

> **Note:** `README.md` is out of date — it describes a DeepFace-based pipeline on ports 8000/5173. The real implementation uses MTCNN + HSEmotion on **port 9501 (backend)** and **port 9500 (frontend)**. Trust the code over the README.

## Commands

The app expects a conda env named `webFaceEmotionRec` (not the venv shown in README).

```powershell
# Full stack (both services), from repo root:
.\start.bat          # Windows — opens two cmd windows
./start.sh           # bash/conda — runs both, Ctrl+C stops both

# Backend only
cd backend
python main.py       # serves on 0.0.0.0:9501

# Frontend only
cd webside
npm install
npm run dev          # Vite dev server on 0.0.0.0:9500 (strictPort)
npm run build        # production build to webside/dist
npm run preview      # preview built bundle on :9500
```

There is no test suite or linter configured.

### Python dependencies
PyTorch (CUDA) must be installed **separately** before `pip install -r backend/requirements.txt`:
```
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
```
HSEmotion model weights download from the network on first run. GPU is auto-detected; falls back to CPU with a warning.

## Architecture

### Frontend → Backend communication
- The frontend **never hardcodes the backend host**. It opens `new WebSocket(...location.host.../ws/emotion)` and relies on the Vite proxy ([webside/vite.config.js](webside/vite.config.js)) to forward `/ws` and `/health` to `localhost:9501`. In production the SPA and API must be served behind a reverse proxy that preserves these paths.
- Frames: `EmotionDetector.vue` captures the `<video>` to a canvas at `TARGET_FPS = 5`, encodes JPEG via `canvas.toDataURL('image/jpeg', 0.75)`, and sends JSON `{ frame: <dataURL>, detector_backend: <string> }`.
- Backend ([backend/main.py](backend/main.py)) decodes base64 → OpenCV BGR, runs `analyze_frame` in a `ThreadPoolExecutor` (off the asyncio loop), and replies with `{ success, faces: [{ region, emotions, dominant, dominant_en }] }`. `emotions` keys are **Chinese labels**; `dominant_en` carries the English key the frontend uses for color/emoji lookup.
- `detector_backend` is accepted and validated against `ALLOWED_DETECTOR_BACKENDS` but currently **unused** — detection is always MTCNN regardless of the dropdown value.

### Emotion label pipeline (three label spaces)
Labels pass through three vocabularies, and the mapping tables in [backend/main.py](backend/main.py) are the source of truth:
1. **HSEmotion output** (`anger`, `happiness`, `sadness`, ...) →
2. **English / DeepFace-compatible keys** (`angry`, `happy`, `sad`, ...) via `HSEMOTION_TO_EN` →
3. **Chinese display** (`愤怒`, `开心`, ...) via `EMOTION_ZH`.

The model is `enet_b2_7` — **7 classes, no "contempt"** — deliberately matched to DeepFace's label set. If you change the model, update both mapping dicts.

### PyTorch 2.6 compatibility shim
`main.py` monkeypatches `torch.load` to force `weights_only=False` **before** importing `facenet_pytorch`/`hsemotion`. Those libs ship weights incompatible with PyTorch 2.6's new default. Do not reorder these imports or remove the patch.

### Thresholds (tunable, in `analyze_frame`)
- MTCNN detection: per-stage `thresholds=[0.6, 0.7, 0.7]`, `min_face_size=20`.
- Per-face confidence gate: faces with `prob < 0.75` are dropped before emotion classification.

### Localization & routing
Vue Router serves the **same** `EmotionDetector` component at `/cn` (zh) and `/jp` (ja), passing a `locale` object as a prop ([webside/src/router.js](webside/src/router.js)). All UI strings live in [webside/src/locales/zh.js](webside/src/locales/zh.js) and [ja.js](webside/src/locales/ja.js) — including the `detectorOptions` dropdown list. Add a language by adding a locale file + route. The root `/` redirects to `/cn`.

### ComfyUI panel
[webside/src/components/ComfyUIPanel.vue](webside/src/components/ComfyUIPanel.vue) + [api/comfyuiApi.js](webside/src/api/comfyuiApi.js) talk to an external ComfyUI server. In dev, requests go to `/comfyui` and Vite proxies (with path rewrite) to `VITE_COMFYUI_PROXY_TARGET`. Configure via env (see [webside/.env.example](webside/.env.example)): `VITE_COMFYUI_HOST`, `VITE_COMFYUI_BASE`, `VITE_COMFYUI_PROXY_TARGET`. This panel is independent of the emotion pipeline.
"" 
# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
