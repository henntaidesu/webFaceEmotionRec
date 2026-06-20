# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Real-time facial emotion recognition web app. A Vue 3 SPA streams webcam frames over a WebSocket to a FastAPI backend, which runs MTCNN face detection + emotion classification on the GPU and returns per-face emotion probabilities. The classifier is **pluggable**: a built-in HSEmotion (EfficientNet-B2) model ships by default, and the app can also **train custom image-FER models from the browser** and hot-swap them for inference. Two more SPA panels cover that training workflow and an embedded ComfyUI client.

> **Note:** `README.md` is out of date — it describes a DeepFace-based pipeline on ports 8000/5173. The real implementation uses MTCNN + HSEmotion on **port 9501 (backend)** and **port 9500 (frontend)**. Trust the code over the README.

## Commands

The app expects a conda env named `webFaceEmotionRec` (not the venv shown in README).

```powershell
# Full stack (both services), from repo root:
.\start.bat          # Windows — opens two cmd windows
./start.sh           # bash/conda — runs both, Ctrl+C stops both

# Backend only
cd backend
python main.py       # serves on 0.0.0.0:9501 (thin entry point → src/use_web/app.py)

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
HSEmotion model weights download from the network on first run. By default CUDA is **required** (`select_device` raises if no GPU); set `REQUIRE_CUDA=0` to fall back to CPU.

### Training datasets
Image data is **not** committed (see `.gitignore`) — only the prep scripts in [DataSet/](DataSet/). Regenerate locally before training:
```
python DataSet/prepare_fer2013.py      # then apply_ferplus.py / prepare_rafdb.py / prepare_affectnet.py
```
Each script writes `DataSet/<name>/{train,val[,test]}/<emotion>/*` as torchvision `ImageFolder` trees. The 7 class dirs are alphabetical: `angry disgust fear happy neutral sad surprise`. See [DataSet/README.md](DataSet/README.md) for sources/licensing (RAF-DB/AffectNet mirrors are a license gray area) and VR-occlusion datasets.

## Architecture

### Backend package layout
`backend/main.py` is a thin entry point; all logic lives in `backend/src/`, split by responsibility:
- [src/config.py](backend/src/config.py) — central config, env-overridable (ports, CUDA, model name, thresholds, train defaults, paths).
- [src/use_web/](backend/src/use_web/) — frontend-facing layer: `app.py` (FastAPI routes + WebSocket), `image_utils.py` (base64 decode).
- [src/use_model/](backend/src/use_model/) — **inference**: `torch_patch.py`, `device.py`, `labels.py`, `models.py` (MTCNN + HSEmotion singleton), `emotion.py` (`analyze_frame`), `model_registry.py` (active-model switching).
- [src/use_train/](backend/src/use_train/) — **training**: `training.py` (job manager), `train_store.py` (disk persistence), `cnn_model.py` (custom VR CNN + occlusion augmentation).

### Frontend → Backend communication
- The frontend **never hardcodes the backend host**. It opens `new WebSocket(...location.host.../ws/emotion)` and relies on the Vite proxy ([webside/vite.config.js](webside/vite.config.js)) to forward `/ws`, `/health`, and `/api` to `localhost:9501` (and `/comfyui` to the ComfyUI server). In production the SPA and API must be served behind a reverse proxy that preserves these paths.
- Frames: `EmotionDetector.vue` captures the `<video>` to a canvas at `TARGET_FPS = 5`, encodes JPEG via `canvas.toDataURL('image/jpeg', 0.75)`, and sends JSON `{ frame: <dataURL>, detector_backend: <string> }`.
- Backend ([src/use_web/app.py](backend/src/use_web/app.py)) decodes base64 → OpenCV BGR, runs `analyze_frame` in a `ThreadPoolExecutor` (off the asyncio loop), and replies with `{ success, faces: [{ region, emotions, dominant, dominant_en }] }`. `emotions` keys are **Chinese labels**; `dominant_en` carries the English key the frontend uses for color/emoji lookup.
- `detector_backend` is accepted and validated against `ALLOWED_DETECTOR_BACKENDS` but currently **unused** — detection is always MTCNN regardless of the dropdown value.

### Emotion label pipeline (three label spaces)
Labels pass through three vocabularies; the mapping tables in [src/use_model/labels.py](backend/src/use_model/labels.py) are the source of truth:
1. **Model output** (HSEmotion: `anger`, `happiness`, ...; trained models emit English keys directly) →
2. **English / DeepFace-compatible keys** (`angry`, `happy`, `sad`, ...) via `HSEMOTION_TO_EN` (identity for already-English keys) →
3. **Chinese display** (`愤怒`, `开心`, ...) via `EMOTION_ZH`.

The built-in model is `enet_b2_7` — **7 classes, no "contempt"** — deliberately matched to DeepFace's label set. Trained models use the same 7 classes (`config.TRAIN_CLASSES`, alphabetical). If you change the class set, update both mapping dicts and `TRAIN_CLASSES`.

### Pluggable inference models (model registry)
[src/use_model/model_registry.py](backend/src/use_model/model_registry.py) lets inference swap between the built-in HSEmotion and any browser-trained model at runtime (`/api/models`, `/api/models/active`, `DELETE /api/models/{id}`). `analyze_frame` calls `get_active_recognizer()` each frame. `TrainedEmotionRecognizer` is **interface-compatible** with `HSEmotionRecognizer` (`idx_to_class` attr + `predict_emotions(rgb, logits=False) -> (label, scores)`) so `emotion.py` stays model-agnostic. Recognizers are cached; after a process restart the active one is lazily reloaded.

### Training subsystem
[src/use_train/training.py](backend/src/use_train/training.py) runs a **single** training job in a background daemon thread; the frontend polls `/api/train/status` for a live snapshot (per-epoch metrics, running loss, log tail). Endpoints: `/api/train/datasets`, `/start`, `/stop`, `/status`, `/runs`, `/runs/{id}`. Key facts:
- **Two backbones** (`config.TRAIN_BACKBONE_CHOICES`): `efficientnet_b2` (timm, pretrained — warmup with frozen backbone for `freeze_epochs`) and `vr_cnn` (custom `VRFaceCNN` in `cnn_model.py`, trained from scratch, never frozen).
- **VR occlusion augmentation** (`VRMask`): masks the eye band to simulate a VR headset occluding the upper face. Training randomizes the mask; **validation uses a fixed mask**, so reported `val_acc`/`macro_f1` reflect accuracy *while wearing VR*.
- Heavy deps (torch/torchvision/timm) are imported **lazily inside training functions**, keeping backend startup fast.
- `ImageFolder` class order is asserted to equal `config.TRAIN_CLASSES`; multiple selected datasets are merged via `ConcatDataset`. Class-weighted `CrossEntropyLoss` + AdamW + AMP (`GradScaler`).

### Two separate model stores (don't confuse them)
- `Model/<run_id>/` (`config.MODEL_DIR`) — **training history**: `meta.json`, `metrics.csv` (one row/epoch, survives restart), and rolling `epoch_NN.pt` weights (last `KEEP_CHECKPOINTS`). Read by the training panel's run dropdown via `train_store.py`.
- `backend/checkpoints/` (`config.CHECKPOINT_DIR`) — **inference registry**: only the *best* `<id>.pt` plus a `<id>.json` sidecar, written when a new best macro-F1 is hit. This is what `model_registry` lists/loads.

### PyTorch 2.6 compatibility shim
[src/use_model/torch_patch.py](backend/src/use_model/torch_patch.py) monkeypatches `torch.load` to force `weights_only=False`. `models.py` calls `patch_torch_load()` **before** importing `facenet_pytorch`/`hsemotion`, whose shipped weights are incompatible with PyTorch 2.6's new default. Do not reorder these imports or remove the patch.

### Thresholds (tunable, in [src/config.py](backend/src/config.py))
- MTCNN detection: per-stage `MTCNN_THRESHOLDS=[0.6, 0.7, 0.7]`, `MIN_FACE_SIZE=20`.
- Per-face confidence gate: faces with `prob < FACE_CONFIDENCE_THRESHOLD` (0.75) are dropped before classification.

### Localization & routing
Vue Router ([webside/src/router.js](webside/src/router.js)) serves three pages — `EmotionDetector`, `TrainingPanel`, `ComfyUIPanel` — each at both `/cn/*` (zh) and `/jp/*` (ja), passing a `locale` object as a prop. The sidebar nav and language switch live in [webside/src/App.vue](webside/src/App.vue). All UI strings live in [webside/src/locales/zh.js](webside/src/locales/zh.js) and [ja.js](webside/src/locales/ja.js). Add a language by adding a locale file + routes. The root `/` redirects to `/cn`.

### ComfyUI panel
[webside/src/components/ComfyUIPanel.vue](webside/src/components/ComfyUIPanel.vue) + [api/comfyuiApi.js](webside/src/api/comfyuiApi.js) talk to an external ComfyUI server. In dev, requests go to `/comfyui` and Vite proxies (with path rewrite) to `VITE_COMFYUI_PROXY_TARGET`. Configure via env (see [webside/.env.example](webside/.env.example)): `VITE_COMFYUI_HOST`, `VITE_COMFYUI_BASE`, `VITE_COMFYUI_PROXY_TARGET` — defaults now point at the **local** `127.0.0.1:8188` ComfyUI launched from the root `comfyui/` 绘世 launcher (started with `--listen`). This panel is independent of the emotion pipeline. (Note: `comfyui/` at the repo root is a bundled ComfyUI runtime, not project source — ignore it when searching.)

The panel also has a **batch dataset generator**: pick emotion classes + count-per-class, and it loops `buildTxt2ImgWorkflow` (one random prompt per image drawn from `public/vr_emotion_prompts.csv` via `vrPrompts.js`, 1000/emotion) with `filename_prefix: <folder>/<emotion>/<emotion>`, so ComfyUI writes the images straight into per-emotion subfolders of its `output/` dir — ready to feed the FER trainer's `ImageFolder` tree. Generation is sequential (queue → wait via the same WS progress events, history-poll fallback) with stop support.
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
