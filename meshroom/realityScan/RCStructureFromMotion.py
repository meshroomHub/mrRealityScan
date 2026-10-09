"""
RCStructureFromMotion.py — Meshroom / RealityCapture pipeline node
==================================================================
Loads an RC project and runs SfM alignment to compute all camera poses.

RC CLI sequence
---------------
  -headless
  -load                   <inputProject>
  -align  (or -draft)
  -selectMaximalComponent
  -save                   <outputProject>
  -quit
"""

import os
import logging

from meshroom.core import desc
from ._rc_utils import normalize_path, run_rc, check_output_file

logger = logging.getLogger(__name__)


class RCStructureFromMotion(desc.Node):
    """
    Runs the RealityCapture / RealityScan Structure-from-Motion pipeline on an
    existing project to compute camera poses and calibration.

    RC detects image features, matches them, and solves for all camera
    positions and orientations.  The largest resulting component is selected
    automatically so downstream nodes work on the most complete reconstruction.

    Predecessor: **RCCreateProject**.
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
                "Path to the ``.rsproj`` project to align.  "
                "Typically the ``outputProject`` of **RCCreateProject**."
            ),
            value="",
        ),
        desc.BoolParam(
            name="draftMode",
            label="Draft Mode",
            description=(
                "Use ``-draft`` instead of ``-align`` for a faster but "
                "lower-quality alignment pass.  Useful for quick previews."
            ),
            value=False,
        ),
    ]

    outputs = [
        desc.File(
            name="outputProject",
            label="Aligned Project File",
            description=(
                "Project file saved after SfM.  "
                "Connect to downstream RC nodes."
            ),
            value="{nodeCacheFolder}/project_aligned.rcproj",
        ),
    ]

    def processChunk(self, chunk):
        if not chunk.node.inputProject.value:
            raise ValueError("inputProject must not be empty.")

        out_project = normalize_path(chunk.node.outputProject.value)
        os.makedirs(os.path.dirname(out_project), exist_ok=True)

        align_flag = "-draft" if chunk.node.draftMode.value else "-align"

        cmd = [
            chunk.node.rcExecutable.value,
            "-headless",
            "-load", chunk.node.inputProject.value,
            align_flag,
            "-selectMaximalComponent",
            "-save", out_project,
            "-quit",
        ]

        run_rc(cmd, node_logger=chunk.logger)
        check_output_file(out_project, label="aligned project file")
        logger.info("Aligned project saved → %s", out_project)
