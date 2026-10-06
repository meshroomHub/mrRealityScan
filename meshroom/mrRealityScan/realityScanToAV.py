__version__ = "0.1"

import os
import json

from meshroom.core import desc
from meshroom.core.utils import VERBOSE_LEVEL

class RealityScanToSfMData(desc.Node):
    """Convert RealityScan XMP camera files to AliceVision SfMData.

    Reads a folder of RealityScan XMP files (one per image) and a folder of
    the corresponding images, then produces an AliceVision SfMData JSON file
    that can be used directly in a Meshroom pipeline.
    """

    category = "Utils"

    inputs = [
        desc.File(
            name="xmpFolder",
            label="XMP Folder",
            description="Folder containing RealityScan XMP files (one per image).",
            value="",
        ),
        desc.File(
            name="imagesFolder",
            label="Images Folder",
            description="Folder containing the source images referenced by the XMP files.",
            value="",
        ),
        desc.FloatParam(
            name="sensorWidth",
            label="Sensor Width (mm)",
            description="Physical sensor width in millimeters used to convert the 35 mm-equivalent focal length.",
            value=36.0,
            range=(1.0, 100.0, 0.1),
        ),
        desc.FloatParam(
            name="sensorHeight",
            label="Sensor Height (mm)",
            description="Physical sensor height in millimeters.",
            value=24.0,
            range=(1.0, 100.0, 0.1),
        ),
        desc.StringParam(
            name="cameraMake",
            label="Camera Make",
            description="Camera manufacturer name stored in the output SfMData metadata.",
            value="Unknown",
        ),
        desc.StringParam(
            name="cameraModel",
            label="Camera Model",
            description="Camera model name stored in the output SfMData metadata.",
            value="Unknown",
        ),
        desc.StringParam(
            name="serialNumber",
            label="Serial Number",
            description="Camera serial number used to group views into intrinsic groups.",
            value="0",
        ),
        desc.ChoiceParam(
            name="verboseLevel",
            label="Verbose Level",
            description="Verbosity level (fatal, error, warning, info, debug, trace).",
            values=VERBOSE_LEVEL,
            value="info",
        )
    ]

    outputs = [
        desc.File(
            name="output",
            label="SfMData",
            description="Path to the output AliceVision SfMData JSON file.",
            value="{nodeCacheFolder}/sfmData.json",
        ),
    ]

    def process(self, node):
        import xml.etree.ElementTree as ET
        from PIL import Image
        import logging

        logging.getLogger().setLevel(node.verboseLevel.value.upper())

        
        xmp_folder = node.xmpFolder.value
        images_folder = node.imagesFolder.value
        output_path = node.output.value

        if not os.path.exists(xmp_folder) or not os.path.exists(images_folder):
            raise ValueError("The XMP and Images folders must exist.")

        sfm_data = {
            "version": ["1", "2", "2"],
            "featuresFolders": [],
            "matchesFolders": [],
            "views": [],
            "intrinsics": [],
            "poses": []
        }

        intrinsics_map = {}
        view_id_counter = 10000000
        pose_id_counter = 20000000
        intrinsic_id_counter = 30000000

        def get_xmp_value(root, name):
            for elem in root.iter():
                # 1. Check whether the tag name matches (e.g., <xcr:Rotation>value</xcr:Rotation>)
                if elem.tag.endswith(name) and elem.text:
                    return elem.text.strip()
                # 2. Check the attributes (e.g., Rotation="value")
                for key, val in elem.attrib.items():
                    if key.endswith(name):
                        return val
            return None

        def rc_rotation_to_av(rotation):
            """Convert RealityScan rotation (world2cam, row-major) to AliceVision rotation (cam2world, column-major)."""
            rc_matrix = [float(x) for x in rotation.split()]
            av_matrix = [
                 rc_matrix[0],  rc_matrix[3],  rc_matrix[6],
                -rc_matrix[1], -rc_matrix[4], -rc_matrix[7],
                -rc_matrix[2], -rc_matrix[5], -rc_matrix[8],
            ]
            return [str(x) for x in av_matrix]

        def rc_position_to_av(position):
            """Convert RealityScan position (world coordinates) to AliceVision position (camera center in world coordinates)."""
            pos = [float(x) for x in position.split()]
            pos = [pos[0], -pos[1], -pos[2]]
            return [str(x) for x in pos]


        valid_extensions = ('.jpg', '.jpeg', '.png', '.tif', '.tiff', '.exr')
        for img_name in sorted(os.listdir(images_folder)):
            if not img_name.lower().endswith(valid_extensions):
                continue

            img_path = os.path.join(images_folder, img_name)
            base_name = os.path.splitext(img_name)[0]

            xmp_path_1 = os.path.join(xmp_folder, img_name + ".xmp")  # e.g., image.jpg.xmp
            xmp_path_2 = os.path.join(xmp_folder, base_name + ".xmp")  # e.g., image.xmp

            if os.path.exists(xmp_path_1):
                xmp_path = xmp_path_1
            elif os.path.exists(xmp_path_2):
                xmp_path = xmp_path_2
            else:
                logging.warning(f"XMP file not found (neither '{base_name}.xmp' nor '{img_name}.xmp')")
                continue

            try:
                with Image.open(img_path) as img:
                    width, height = img.size
            except Exception as e:
                logging.error(f"Unable to read image {img_path}: {e}")
                continue

            max_dim = max(width, height)

            # Read the XMP file
            tree = ET.parse(xmp_path)
            root = tree.getroot()

            sensor_width = node.sensorWidth.value
            focal_35 = float(get_xmp_value(root, "FocalLength35mm"))
            ppu = float(get_xmp_value(root, "PrincipalPointU"))
            ppv = float(get_xmp_value(root, "PrincipalPointV"))
            rot_str = get_xmp_value(root, "Rotation")
            pos_str = get_xmp_value(root, "Position")

            if not rot_str or not pos_str:
                logging.warning(f"XMP skipped (missing Rotation or Position) for {img_path}")
                continue

            focal_mm = (focal_35 / 36.0) * sensor_width
            px = ppu * max_dim
            py = ppv * max_dim

            intrinsic_key = f"{width}_{height}_{focal_35}"
            if intrinsic_key not in intrinsics_map:
                intrinsic_id = str(intrinsic_id_counter)
                intrinsics_map[intrinsic_key] = intrinsic_id
                intrinsic_id_counter += 1

                sfm_data["intrinsics"].append({
                    "intrinsicId": intrinsic_id,
                    "width": str(width),
                    "height": str(height),
                    "sensorWidth": str(node.sensorWidth.value),
                    "sensorHeight": str(node.sensorHeight.value),
                    "serialNumber": node.serialNumber.value,
                    "type": "radial3",
                    "initializationMode": "calibrated",
                    "initialFocalLength": str(focal_mm),
                    "focalLength": str(focal_mm),
                    "pixelRatio": "1.0",
                    "pixelRatioInitial": "1.0",
                    "pixelRatioLocked": "true",
                    "principalPoint": [str(px), str(py)],
                    "distortionParams": ["0.0", "0.0", "0.0"],
                    "locked": "false"
                })
            else:
                intrinsic_id = intrinsics_map[intrinsic_key]

            v_id = str(view_id_counter)
            p_id = str(pose_id_counter)
            view_id_counter += 1
            pose_id_counter += 1

            sfm_data["views"].append({
                "viewId": v_id,
                "poseId": p_id,
                "intrinsicId": intrinsic_id,
                "reconstructionId": "0",
                "path": img_path,
                "width": str(width),
                "height": str(height),
                "metadata": {
                    "Make": node.cameraMake.value,
                    "Model": node.cameraModel.value
                }
            })

            rot = rc_rotation_to_av(rot_str)
            pos = rc_position_to_av(pos_str)

            sfm_data["poses"].append({
                "poseId": p_id,
                "pose": {
                    "transform": {
                        "rotation": rot,
                        "center": pos
                    },
                    "locked": "false"
                }
            })

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(sfm_data, f, indent=4)

        logging.info(f"SfMData generated successfully: {len(sfm_data['views'])} views processed.")
