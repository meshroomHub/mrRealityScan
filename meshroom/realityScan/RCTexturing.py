"""
RCTexturing.py — Meshroom / RealityCapture pipeline node
=========================================================
Computes UV unwrap and photo-textures on a meshed RC project, then exports
the fully textured model with its companion atlas images.

RC CLI sequence
---------------
  -headless
  -load                    <inputProject>
  -selectMaximalComponent
  [-selectModel            <modelName>]
  -unwrap                  [unwrapParamsFile]
  -calculateTexture        [textureParamsFile]
  -exportSelectedModel     <outputTexturedModel>
  -save                    <outputProject>
  -quit

Texture atlas note
------------------
RC writes the mesh file AND one or more companion atlas images (jpg/png) into
the same directory, sharing the base name of the exported mesh file.
"""

import os
import logging

from meshroom.core import desc
from ._rc_utils import normalize_path, run_rc, check_output_file

logger = logging.getLogger(__name__)

_FORMAT_EXT = {
    "OBJ":     ".obj",
    "FBX":     ".fbx",
    "PLY":     ".ply",
    "COLLADA": ".dae",
}


class RCTexturing(desc.Node):
    """
    Computes UV unwrap and photo-realistic textures for a mesh in an existing
    RealityCapture / RealityScan project.

    Three steps are run in sequence:

    1. **UV Unwrap** (``-unwrap``) — parameterises the surface for atlas painting.
    2. **Texture Calculation** (``-calculateTexture``) — projects source images
       onto the mesh to build high-resolution atlas images.
    3. **Export** (``-exportSelectedModel``) — writes the mesh and atlas files.

    Optional ``params.xml`` files (exported from RC's Unwrap / Texture dialogs)
    override default quality settings.

    Predecessor: **RCMeshing**.
    """

    category = "RealityCapture"

    inputs = [
        desc.File(
            name="rcExecutable",
            label="RC Executable",
            description=(
                "Full path to the RealityCapture or RealityScan executable.\n"
                "Example: C:/Program Files/RealityCapture/RealityCapture.exe"
            ),
            value="C:/Program Files/Capturing Reality/RealityCapture/RealityCapture.exe",
        ),
        desc.File(
            name="inputProject",
            label="Input Project File",
            description=(
                "Path to an ``.rsproj`` project containing a computed mesh.  "
                "Typically the ``outputProject`` of **RCMeshing**."
            ),
            value="",
        ),
        desc.StringParam(
            name="modelName",
            label="Model Name (optional)",
            description=(
                "Name of the model to texture.  Leave empty to texture the model "
                "that is active after ``-selectMaximalComponent``."
            ),
            value="",
        ),
        desc.ChoiceParam(
            name="exportFormat",
            label="Export Format",
            description=(
                "File format for the exported textured model.  "
                "RC writes the mesh and companion atlas images to the same folder."
            ),
            value="OBJ",
            values=["OBJ", "FBX", "PLY", "COLLADA"],
            exclusive=True,
        ),
        desc.File(
            name="unwrapParamsFile",
            label="Unwrap Params XML (optional)",
            description=(
                "``params.xml`` exported from RC's Unwrap dialog.  "
                "Controls atlas resolution, padding, and algorithm.  "
                "Leave empty to use RC's current defaults."
            ),
            value="",
        ),
        desc.File(
            name="textureParamsFile",
            label="Texture Params XML (optional)",
            description=(
                "``params.xml`` exported from RC's Color and Texture Settings panel.  "
                "Controls atlas resolution, blending, and colour correction.  "
                "Leave empty to use RC's current defaults."
            ),
            value="",
        ),
    ]

    outputs = [
        desc.File(
            name="outputTexturedModel",
            label="Textured Model",
            description=(
                "Exported textured mesh file.  Companion atlas images are written "
                "to the same folder with the same base name."
            ),
            value="{nodeCacheFolder}/textured_model.obj",
        ),
        desc.File(
            name="outputProject",
            label="Output Project File",
            description="Final project file saved with texture data.",
            value="{nodeCacheFolder}/project_textured.rcproj",
        ),
    ]

    def processChunk(self, chunk):
        if not chunk.node.inputProject.value:
            raise ValueError("inputProject must not be empty.")

        out_project = normalize_path(chunk.node.outputProject.value)
        out_dir = os.path.dirname(out_project)
        os.makedirs(out_dir, exist_ok=True)

        ext = _FORMAT_EXT[chunk.node.exportFormat.value]
        model_out = normalize_path(os.path.join(out_dir, "textured_model" + ext))

        select_model_args = []
        if chunk.node.modelName.value.strip():
            select_model_args = ["-selectModel", chunk.node.modelName.value.strip()]

        unwrap_args = ["-unwrap"]
        if chunk.node.unwrapParamsFile.value and os.path.isfile(chunk.node.unwrapParamsFile.value):
            unwrap_args.append(normalize_path(chunk.node.unwrapParamsFile.value))

        texture_args = ["-calculateTexture"]
        if chunk.node.textureParamsFile.value and os.path.isfile(chunk.node.textureParamsFile.value):
            texture_args.append(normalize_path(chunk.node.textureParamsFile.value))

        cmd = (
            [
                chunk.node.rcExecutable.value,
                "-headless",
                "-load", chunk.node.inputProject.value,
                "-selectMaximalComponent",
            ]
            + select_model_args
            + unwrap_args
            + texture_args
            + [
                "-exportSelectedModel", model_out,
                "-save", out_project,
                "-quit",
            ]
        )

        run_rc(cmd, node_logger=chunk.logger)
        check_output_file(model_out, label="textured model file")
        check_output_file(out_project, label="project file")
        logger.info("Textured model → %s", model_out)
        logger.info("Atlas images written alongside the mesh.")
        logger.info("Project saved → %s", out_project)
