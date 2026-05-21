# Meshroom — RealityCapture Pipeline Nodes

Six custom Meshroom nodes that wrap the **RealityCapture / RealityScan** CLI
to create a complete photogrammetry pipeline runnable from inside Meshroom's
graph editor.

---

## Node overview

| # | File | Category | What it does |
|---|------|----------|--------------|
| 1 | `RCCreateProject.py` | RealityCapture | Create a new RC project, import images from a folder, group by EXIF |
| 2 | `RCStructureFromMotion.py` | RealityCapture | Run SfM alignment — compute all camera poses |
| 3 | `RCExportAligned.py` | RealityCapture | Export XMP camera files + sparse point cloud |
| 4 | `RCDepthMaps.py` | RealityCapture | Configure per-image depth-map downscale factor |
| 5 | `RCMeshing.py` | RealityCapture | Compute the dense mesh (Preview / Normal / High quality) |
| 6 | `RCTexturing.py` | RealityCapture | Compute UV unwrap + photo-textures, export textured model |

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| **Meshroom** | Any recent version supporting `desc.Node` with `process()` |
| **Python 3.7+** | Required for `subprocess.run(capture_output=True)` |
| **RealityCapture / RealityScan** | Must have a valid licence for CLI/headless use |

---

## Installation

Meshroom loads plugin nodes from directories listed in the
`MESHROOM_NODES_PATH` environment variable (colon-separated on Linux/macOS,
semicolon-separated on Windows).

```bash
# Linux / macOS
export MESHROOM_NODES_PATH=/path/to/MeshroomRCNodes

# Windows (Command Prompt)
set MESHROOM_NODES_PATH=C:\path\to\MeshroomRCNodes

# Windows (PowerShell)
$env:MESHROOM_NODES_PATH = "C:\path\to\MeshroomRCNodes"
```

Then launch Meshroom normally.  All six nodes will appear under the
**RealityCapture** category in the node library.

> **Alternative**: Copy the six `.py` files into any folder already on
> `MESHROOM_NODES_PATH`, or into `<MeshroomInstall>/lib/meshroom/nodes/`.

---

## Recommended pipeline

```
RCCreateProject
      │ outputProject
      ▼
RCStructureFromMotion
      │ outputProject
      ├──────────────────────► RCExportAligned   (XMP + sparse cloud)
      ▼
RCDepthMaps
      │ outputProject
      ▼
RCMeshing
      │ outputProject
      ▼
RCTexturing
      │ outputTexturedModel
      ▼
   (final OBJ / FBX / …)
```

Connect each node's `outputProject` to the next node's `inputProject`.
All six nodes share the same `rcExecutable` parameter — set it once on each
node to the full path of your `RealityCapture.exe` / `RealityScan.exe`.

---

## Node reference

### 1 · RCCreateProject

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `rcExecutable` | File | `RealityCapture.exe` | Full path to the RC binary |
| `imageFolder` | File | _(empty)_ | Root folder of images to import |
| `includeSubdirs` | Bool | `false` | Recurse into sub-folders |
| **`outputProject`** | File (out) | `{cache}/project.rsproj` | Created project file |

RC commands: `-newScene` → `-set appIncSubdirs=…` → `-addFolder` →
`-selectAllImages` → `-setCalibrationGroupByExif` → `-save` → `-quit`

---

### 2 · RCStructureFromMotion

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `rcExecutable` | File | `RealityCapture.exe` | |
| `inputProject` | File | _(empty)_ | From RCCreateProject |
| `draftMode` | Bool | `false` | Use `-draft` for fast preview alignment |
| **`outputProject`** | File (out) | `{cache}/project_aligned.rsproj` | |

RC commands: `-load` → `-align` (or `-draft`) → `-selectMaximalComponent` →
`-save` → `-quit`

---

### 3 · RCExportAligned

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `rcExecutable` | File | `RealityCapture.exe` | |
| `inputProject` | File | _(empty)_ | From RCStructureFromMotion |
| `minComponentSize` | Int | `5` | Skip components with fewer than N images |
| `sparseCloudFormat` | Choice | `.ply` | `.ply` / `.pts` / `.xyz` / `.las` / `.laz` / `.e57` |
| `xmpParamsFile` | File | _(empty)_ | Optional params.xml from RC XMP dialog |
| **`sparsePointCloud`** | File (out) | `{cache}/sparse_point_cloud.ply` | |
| **`outputProject`** | File (out) | `{cache}/project_exported.rsproj` | |

**XMP note**: RC always writes XMP files *next to the source images* —
the output folder cannot be overridden via the CLI alone.

RC commands: `-load` → `-setMinComponentSize` → `-selectMaximalComponent` →
`-exportXMP` → `-exportSparsePointCloud` → `-save` → `-quit`

---

### 4 · RCDepthMaps

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `rcExecutable` | File | `RealityCapture.exe` | |
| `inputProject` | File | _(empty)_ | From RCStructureFromMotion |
| `downscaleFactor` | Int (1–8) | `2` | 1 = full-res, 2 = half-res, 4 = quarter-res |
| `autoReconRegion` | Bool | `true` | Auto-fit the reconstruction box |
| **`outputProject`** | File (out) | `{cache}/project_depthmaps_cfg.rsproj` | |

> **Architecture note**: RC has no standalone "compute depth maps" CLI command.
> This node *configures* depth-map settings; the actual computation is
> triggered by **RCMeshing** (`calculateNormalModel` etc.).

RC commands: `-load` → `-selectAllImages` → `-setDownscaleForDepthMaps` →
`[-setReconstructionRegionAuto]` → `-save` → `-quit`

---

### 5 · RCMeshing

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `rcExecutable` | File | `RealityCapture.exe` | |
| `inputProject` | File | _(empty)_ | From RCDepthMaps |
| `meshQuality` | Choice | `Normal` | `Preview` / `Normal` / `High` |
| `exportFormat` | Choice | `OBJ` | `OBJ` / `FBX` / `PLY` / `STL` / `COLLADA` / `3DS` |
| `keepLargestComponent` | Bool | `true` | Discard stray geometry fragments |
| **`outputMesh`** | File (out) | `{cache}/mesh.obj` | Exported mesh |
| **`outputProject`** | File (out) | `{cache}/project_meshed.rsproj` | |

Quality → RC command mapping:

| Quality | RC command |
|---------|-----------|
| Preview | `-calculatePreviewModel` |
| Normal | `-calculateNormalModel` |
| High | `-calculateHighModel` |

RC commands: `-load` → `-selectMaximalComponent` →
`-calculate{Quality}Model` → `[-selectLargestModelComponent]` →
`-exportSelectedModel` → `-save` → `-quit`

---

### 6 · RCTexturing

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `rcExecutable` | File | `RealityCapture.exe` | |
| `inputProject` | File | _(empty)_ | From RCMeshing |
| `modelName` | String | _(empty)_ | Override which model to texture |
| `exportFormat` | Choice | `OBJ` | `OBJ` / `FBX` / `PLY` / `COLLADA` |
| `unwrapParamsFile` | File | _(empty)_ | Optional params.xml from RC Unwrap dialog |
| `textureParamsFile` | File | _(empty)_ | Optional params.xml from RC Texture dialog |
| **`outputTexturedModel`** | File (out) | `{cache}/textured_model.obj` | |
| **`outputProject`** | File (out) | `{cache}/project_textured.rsproj` | Final project |

Texture atlas images are written alongside the mesh file with the same base
name (e.g. `textured_model_u1_v1.jpg`).

RC commands: `-load` → `-selectMaximalComponent` → `[-selectModel]` →
`-unwrap` → `-calculateTexture` → `-exportSelectedModel` → `-save` → `-quit`

---

## Tips

- **Params XML files** — For production pipelines, export `params.xml` files
  from the RC dialogs (Unwrap, Texture, XMP Export) and wire them into the
  optional parameters.  This lets you version-control your quality settings
  independently of the Meshroom graph.

- **RC licence** — Headless / batch execution requires a valid RealityCapture
  PPI or Enterprise licence.  The nodes will fail at runtime without one.

- **Windows paths with spaces** — All subprocess calls use list-style
  argument passing, which handles spaces in paths automatically.

- **Logging** — All six nodes use Python's standard `logging` module.
  RC's own stdout/stderr is captured and forwarded to Meshroom's log output.
