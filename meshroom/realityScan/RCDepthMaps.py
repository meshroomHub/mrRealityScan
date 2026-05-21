"""
RCDepthMaps.py — Meshroom / RealityCapture pipeline node
=========================================================
Configures per-image depth-map settings (downscale factor, reconstruction
region) and saves the project.  The actual depth-map computation is triggered
by the subsequent RCMeshing node.

RC CLI sequence
---------------
  -headless
  -load                          <inputProject>
  -selectAllImages
  -setDownscaleForDepthMaps      <factor>
  [-setReconstructionRegionAuto]
  -save                          <outputProject>
  -quit

Architecture note
-----------------
RC has no standalone "compute depth maps" CLI command; depth maps are computed
internally during ``calculateNormalModel`` / ``calculateHighModel`` etc.
This node is the *configuration* step; RCMeshing triggers the computation.
"""

import os
import logging

from meshroom.core import desc
from ._rc_utils import normalize_path, run_rc, check_output_file

logger = logging.getLogger(__name__)


class RCDepthMaps(desc.Node):
    """
    Configures depth-map computation settings in an existing RealityCapture /
    RealityScan aligned project.

    Sets the per-image downscale factor which controls depth-map resolution
    (quality ↔ speed trade-off) and optionally auto-fits the reconstruction
    region.  Connect this node's ``outputProject`` to **RCMeshing**, which
    will trigger the actual depth-map computation as part of the dense build.

    Predecessor: **RCStructureFromMotion** (or **RCExportAligned**).
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
                "Path to an aligned ``.rsproj`` project.  "
                "Typically the ``outputProject`` of **RCStructureFromMotion**."
            ),
            value="",
        ),
        desc.IntParam(
            name="downscaleFactor",
            label="Depth Map Downscale Factor",
            description=(
                "Resolution divisor applied per image before depth-map computation.\n"
                "  1 = full resolution (highest quality, most RAM/time)\n"
                "  2 = half resolution  ← recommended default\n"
                "  4 = quarter resolution (fastest)\n"
                "  8 = eighth resolution"
            ),
            value=2,
            range=(1, 8, 1),
        ),
        desc.BoolParam(
            name="autoReconRegion",
            label="Auto Reconstruction Region",
            description=(
                "Call ``-setReconstructionRegionAuto`` to fit the reconstruction "
                "box automatically around the sparse point cloud.  Recommended "
                "when no manual region has been set."
            ),
            value=True,
        ),
    ]

    outputs = [
        desc.File(
            name="outputProject",
            label="Output Project File",
            description=(
                "Project file saved with depth-map settings applied.  "
                "Connect to **RCMeshing** to trigger the actual computation."
            ),
            value="{nodeCacheFolder}/project_depthmaps_cfg.rcproj",
        ),
    ]

    def processChunk(self, chunk):
        if not chunk.node.inputProject.value:
            raise ValueError("inputProject must not be empty.")

        out_project = normalize_path(chunk.node.outputProject.value)
        os.makedirs(os.path.dirname(out_project), exist_ok=True)

        recon_args = ["-setReconstructionRegionAuto"] if chunk.node.autoReconRegion.value else []

        cmd = (
            [
                chunk.node.rcExecutable.value,
                "-headless",
                "-load", chunk.node.inputProject.value,
                "-selectAllImages",
                "-setDownscaleForDepthMaps", str(chunk.node.downscaleFactor.value),
            ]
            + recon_args
            + [
                "-save", out_project,
                "-quit",
            ]
        )

        run_rc(cmd, node_logger=chunk.logger)
        check_output_file(out_project, label="project file")
        logger.info(
            "Depth-map settings (downscale=%d) saved → %s",
            chunk.node.downscaleFactor.value, out_project,
        )
