"""
RCCreateProject.py — Meshroom / RealityCapture pipeline node
=============================================================
Creates a new RC project, imports all images from a folder, assigns
calibration groups from EXIF data, and saves the project.

RC CLI sequence
---------------
  -headless
  -newScene
  -set "appIncSubdirs=<true|false>"
  -addFolder  <imageFolder>
  -selectAllImages
  -setCalibrationGroupByExif
  -save       <outputProject>
  -quit
"""

import os
import logging

from meshroom.core import desc

# Shared RC subprocess helper (path normalisation + Windows-safe launch).
# _rc_utils.py must live in the same plugin folder as this file.
from . _rc_utils import normalize_path, run_rc, check_output_file   # noqa: E402

logger = logging.getLogger(__name__)


class RCCreateProject(desc.Node):
    """
    Creates a new RealityCapture / RealityScan project from a folder of images.

    All images are imported and automatically grouped into calibration groups
    based on their EXIF metadata (camera model, focal length …) using
    ``-setCalibrationGroupByExif``.  The saved ``.rsproj`` file is written to
    this node's cache folder and can be wired into subsequent RC pipeline nodes.
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
            name="imageFolder",
            label="Image Folder",
            description=(
                "Root folder containing the input images to import.\n"
                "Supported: JPG, PNG, TIFF, RAW and any other RC-supported type."
            ),
            value="",
        ),
        desc.BoolParam(
            name="includeSubdirs",
            label="Include Sub-directories",
            description=(
                "When enabled, images found in any sub-directory are also imported "
                "(sets ``appIncSubdirs=true`` via ``-set``)."
            ),
            value=False,
        ),
    ]

    outputs = [
        desc.File(
            name="outputProject",
            label="Output Project File",
            description=(
                "Path to the saved ``.rcproj`` project file.  "
                "Connect this to the ``inputProject`` of subsequent RC nodes."
            ),
            value="{nodeCacheFolder}/project.rcproj",
        ),
    ]

    def processChunk(self, chunk):
        # ── validate inputs ──────────────────────────────────────────────────
        if not chunk.node.imageFolder.value:
            raise ValueError("imageFolder must not be empty.")

        # ── prepare output directory ─────────────────────────────────────────
        # normalize_path converts T:/foo → T:\foo on Windows so RC accepts it.
        out_project = normalize_path(chunk.node.outputProject.value)
        os.makedirs(os.path.dirname(out_project), exist_ok=True)

        # ── build RC command ─────────────────────────────────────────────────
        inc_subdirs = "true" if chunk.node.includeSubdirs.value else "false"

        cmd = [
            # run_rc will normalise the executable path too
            chunk.node.rcExecutable.value,
            "-headless",
            "-newScene",
            "-set", "appIncSubdirs={}".format(inc_subdirs),
            "-addFolder", chunk.node.imageFolder.value,   # normalised by run_rc
            "-selectAllImages",
            "-setCalibrationGroupByExif",
            "-save", out_project,
            "-quit",
        ]

        # ── run RC ───────────────────────────────────────────────────────────
        run_rc(cmd, node_logger=chunk.logger)

        # ── verify output ────────────────────────────────────────────────────
        check_output_file(out_project, label="project file")
        logger.info("Project saved → %s", out_project)
