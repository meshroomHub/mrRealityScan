"""
RCMeshing.py — Meshroom / RealityCapture pipeline node
=======================================================
Loads an RC project, computes the dense mesh at the requested quality,
exports the mesh, and saves the project.

RC CLI sequence
---------------
  -headless
  -load                          <inputProject>
  -selectMaximalComponent
  -calculate{Preview|Normal|High}Model
  [-selectLargestModelComponent]
  -exportSelectedModel           <outputMesh>
  -save                          <outputProject>
  -quit
"""

import os
import logging

from meshroom.core import desc
from ._rc_utils import normalize_path, run_rc, check_output_file

logger = logging.getLogger(__name__)

_QUALITY_FLAG = {
    "Preview": "-calculatePreviewModel",
    "Normal":  "-calculateNormalModel",
    "High":    "-calculateHighModel",
}

_FORMAT_EXT = {
    "OBJ":     ".obj",
    "FBX":     ".fbx",
    "PLY":     ".ply",
    "STL":     ".stl",
    "COLLADA": ".dae",
    "3DS":     ".3ds",
}


class RCMeshing(desc.Node):
    """
    Computes the dense 3-D mesh inside an existing RealityCapture / RealityScan
    project.

    RC internally computes per-image depth maps, fuses them, and builds the
    final triangle mesh — all triggered by a single model-calculation command.
    Depth-map resolution is controlled by the **RCDepthMaps** predecessor node.

    The mesh is exported to the node cache folder in the chosen format.

    Predecessor: **RCDepthMaps** (or **RCStructureFromMotion** if skipping
    depth-map configuration).
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
                "Path to an aligned ``.rsproj`` project, ideally with depth-map "
                "settings applied by **RCDepthMaps**."
            ),
            value="",
        ),
        desc.ChoiceParam(
            name="meshQuality",
            label="Mesh Quality",
            description=(
                "Dense reconstruction quality level.\n"
                "  Preview → ``-calculatePreviewModel``  (fast draft)\n"
                "  Normal  → ``-calculateNormalModel``   (balanced, recommended)\n"
                "  High    → ``-calculateHighModel``     (maximum quality)"
            ),
            value="Normal",
            values=["Preview", "Normal", "High"],
            exclusive=True,
        ),
        desc.ChoiceParam(
            name="exportFormat",
            label="Export Format",
            description="File format for the exported mesh.",
            value="OBJ",
            values=["OBJ", "FBX", "PLY", "STL", "COLLADA", "3DS"],
            exclusive=True,
        ),
        desc.BoolParam(
            name="keepLargestComponent",
            label="Keep Largest Geometry Component",
            description=(
                "Select only the largest connected geometry island before export, "
                "discarding stray fragments."
            ),
            value=True,
        ),
    ]

    outputs = [
        desc.File(
            name="outputMesh",
            label="Output Mesh",
            description="Exported mesh file (extension depends on Export Format).",
            value="{nodeCacheFolder}/mesh.obj",
        ),
        desc.File(
            name="outputProject",
            label="Output Project File",
            description=(
                "Project file saved after meshing.  "
                "Connect to **RCTexturing**."
            ),
            value="{nodeCacheFolder}/project_meshed.rcproj",
        ),
    ]

    def processChunk(self, chunk):
        if not chunk.node.inputProject.value:
            raise ValueError("inputProject must not be empty.")

        out_project = normalize_path(chunk.node.outputProject.value)
        out_dir = os.path.dirname(out_project)
        os.makedirs(out_dir, exist_ok=True)

        ext = _FORMAT_EXT[chunk.node.exportFormat.value]
        mesh_path = normalize_path(os.path.join(out_dir, "mesh" + ext))
        quality_flag = _QUALITY_FLAG[chunk.node.meshQuality.value]

        largest_args = (
            ["-selectLargestModelComponent"] if chunk.node.keepLargestComponent.value else []
        )

        cmd = (
            [
                chunk.node.rcExecutable.value,
                "-headless",
                "-load", chunk.node.inputProject.value,
                "-selectMaximalComponent",
                quality_flag,
            ]
            + largest_args
            + [
                "-exportSelectedModel", mesh_path,
                "-save", out_project,
                "-quit",
            ]
        )

        run_rc(cmd, node_logger=chunk.logger)
        check_output_file(mesh_path, label="mesh file")
        check_output_file(out_project, label="project file")
        logger.info("Mesh exported → %s", mesh_path)
        logger.info("Project saved → %s", out_project)
