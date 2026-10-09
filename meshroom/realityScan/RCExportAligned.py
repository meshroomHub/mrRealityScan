"""
RCExportAligned.py — Meshroom / RealityCapture pipeline node
============================================================
Exports XMP camera sidecar files and the sparse point cloud from an aligned
RC project.

RC CLI sequence
---------------
  -headless
  -load                          <inputProject>
  -setMinComponentSize           <n>
  -selectMaximalComponent
  -exportXMP                     [xmpParamsFile]
  -exportSparsePointCloud        <sparsePointCloud>
  -save                          <outputProject>
  -quit

XMP note: RC always writes XMP files next to the source images — the
output location cannot be changed via the CLI alone.
"""

import os
import logging

from meshroom.core import desc
from ._rc_utils import normalize_path, run_rc, check_output_file

logger = logging.getLogger(__name__)


class RCExportAligned(desc.Node):
    """
    Exports aligned camera metadata (XMP) and the sparse point cloud from an
    existing RealityCapture / RealityScan project.

    **XMP files** are written directly alongside each source image; their
    location is fixed by RC and cannot be redirected via the CLI.

    The **sparse point cloud** (3-D tie points) is exported to the node cache
    folder.  Format is determined by the chosen extension.

    Predecessor: **RCStructureFromMotion**.
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
                "Path to the aligned ``.rsproj`` project.  "
                "Typically the ``outputProject`` of **RCStructureFromMotion**."
            ),
            value="",
        ),
        desc.IntParam(
            name="minComponentSize",
            label="Min Component Size",
            description=(
                "Minimum number of aligned images a component must contain before "
                "it is included in the export.  RC default is 5."
            ),
            value=5,
            range=(1, 10000, 1),
        ),
        desc.ChoiceParam(
            name="sparseCloudFormat",
            label="Sparse Cloud Format",
            description="File format for the exported sparse (tie-point) point cloud.",
            value=".ply",
            values=[".ply", ".pts", ".xyz", ".las", ".laz", ".e57"],
            exclusive=True,
        ),
        desc.File(
            name="xmpParamsFile",
            label="XMP Params XML (optional)",
            description=(
                "Optional ``params.xml`` exported from RC's XMP Metadata Export "
                "dialog.  Leave empty to use RC's current default settings."
            ),
            value="",
        ),
    ]

    outputs = [
        desc.File(
            name="sparsePointCloud",
            label="Sparse Point Cloud",
            description="Exported sparse (tie-point) point cloud file.",
            value="{nodeCacheFolder}/sparse_point_cloud.ply",
        ),
        desc.File(
            name="outputProject",
            label="Output Project File",
            description=(
                "Project file saved after export (camera poses unchanged).  "
                "Connect to downstream RC nodes."
            ),
            value="{nodeCacheFolder}/project_exported.rsproj",
        ),
    ]

    def processChunk(self, chunk):
        if not chunk.node.inputProject.value:
            raise ValueError("inputProject must not be empty.")

        out_project = normalize_path(chunk.node.outputProject.value)
        out_dir = os.path.dirname(out_project)
        os.makedirs(out_dir, exist_ok=True)

        # Sparse cloud path: use the chosen extension.
        cloud_path = normalize_path(
            os.path.join(out_dir, "sparse_point_cloud" + chunk.node.sparseCloudFormat.value)
        )

        # -exportXMP [params.xml]
        xmp_args = ["-exportXMP"]
        if chunk.node.xmpParamsFile.value and os.path.isfile(chunk.node.xmpParamsFile.value):
            xmp_args.append(normalize_path(chunk.node.xmpParamsFile.value))

        cmd = (
            [
                chunk.node.rcExecutable.value,
                "-headless",
                "-load", chunk.node.inputProject.value,
                "-setMinComponentSize", str(chunk.node.minComponentSize.value),
                "-selectMaximalComponent",
            ]
            + xmp_args
            + [
                "-exportSparsePointCloud", cloud_path,
                "-save", out_project,
                "-quit",
            ]
        )

        run_rc(cmd, node_logger=chunk.logger)
        check_output_file(cloud_path, label="sparse point cloud")
        check_output_file(out_project, label="project file")
        logger.info("Sparse cloud → %s", cloud_path)
        logger.info("XMP files written alongside source images.")
        logger.info("Project saved → %s", out_project)
