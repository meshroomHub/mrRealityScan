__version__ = "0.1"

import os

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
        desc.BoolParam(
            name="matchByFrameNumber",
            label="Match By Frame Number",
            description="Match XMP files and images using the last number in their filenames instead of their names.\n"
                        "Images without XMP are skipped. The node fails if an XMP has no matching image\n"
                        "or if a frame number is shared by several images or several XMP files.",
            value=False,
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
            description="Path to the output AliceVision SfMData file.",
            value="{nodeCacheFolder}/sfmData.usda",
        ),
    ]

    def process(self, node):
        import re
        import xml.etree.ElementTree as ET
        import logging
        import numpy as np
        from pyalicevision import sfmData, sfmDataIO, camera, geometry, image as avimage

        logging.getLogger().setLevel(node.verboseLevel.value.upper())

        
        xmp_folder = node.xmpFolder.value
        images_folder = node.imagesFolder.value
        output_path = node.output.value

        if not os.path.exists(xmp_folder) or not os.path.exists(images_folder):
            raise ValueError("The XMP and Images folders must exist.")

        data = sfmData.SfMData()

        intrinsics_map = {}
        id_counter = 0

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

        # RealityScan world is Z-up, AliceVision is Y-down, plus 90° around Y: (x, y, z) -> (y, -z, -x)
        world_rc_to_av = np.array([[0.0, 1.0, 0.0],
                                   [0.0, 0.0, -1.0],
                                   [-1.0, 0.0, 0.0]])

        def rc_rotation_to_av(rotation):
            """Convert RealityScan rotation (world2cam, row-major, Z-up world) to AliceVision rotation (Y-up world)."""
            rc_matrix = np.array([float(x) for x in rotation.split()]).reshape(3, 3)
            return rc_matrix @ world_rc_to_av.T

        def rc_position_to_av(position):
            """Convert RealityScan position (Z-up world) to AliceVision camera center (Y-up world)."""
            pos = np.array([float(x) for x in position.split()])
            return world_rc_to_av @ pos


        valid_extensions = ('.jpg', '.jpeg', '.png', '.tif', '.tiff', '.exr')
        img_names = sorted(f for f in os.listdir(images_folder) if f.lower().endswith(valid_extensions))

        def frame_number(filename):
            """Return the last number found in the filename (extensions excluded), or None."""
            stem = filename
            if stem.lower().endswith(".xmp"):
                stem = stem[:-len(".xmp")]
            if stem.lower().endswith(valid_extensions):
                stem = os.path.splitext(stem)[0]
            numbers = re.findall(r"\d+", stem)
            return int(numbers[-1]) if numbers else None

        def index_by_frame(names, kind):
            """Map frame number -> filename, failing on missing or duplicated frame numbers."""
            frames = {}
            for name in names:
                frame = frame_number(name)
                if frame is None:
                    raise ValueError(f"No frame number found in {kind} filename '{name}'.")
                if frame in frames:
                    raise ValueError(f"Frame number {frame} is shared by {kind} files "
                                     f"'{frames[frame]}' and '{name}'.")
                frames[frame] = name
            return frames

        pairs = []  # (image path, xmp path)
        images_without_xmp = 0
        if node.matchByFrameNumber.value:
            xmp_names = sorted(f for f in os.listdir(xmp_folder) if f.lower().endswith(".xmp"))
            img_frames = index_by_frame(img_names, "image")
            xmp_frames = index_by_frame(xmp_names, "XMP")
            missing_img = sorted(set(xmp_frames) - set(img_frames))
            if missing_img:
                raise ValueError(f"XMP files without a matching image frame number: {missing_img}.")
            for frame in sorted(img_frames):
                if frame not in xmp_frames:
                    logging.debug(f"No XMP file for frame {frame} ('{img_frames[frame]}')")
                    images_without_xmp += 1
                    continue
                pairs.append((os.path.join(images_folder, img_frames[frame]),
                              os.path.join(xmp_folder, xmp_frames[frame])))
        else:
            for img_name in img_names:
                base_name = os.path.splitext(img_name)[0]
                xmp_path_1 = os.path.join(xmp_folder, img_name + ".xmp")  # e.g., image.jpg.xmp
                xmp_path_2 = os.path.join(xmp_folder, base_name + ".xmp")  # e.g., image.xmp
                if os.path.exists(xmp_path_1):
                    pairs.append((os.path.join(images_folder, img_name), xmp_path_1))
                elif os.path.exists(xmp_path_2):
                    pairs.append((os.path.join(images_folder, img_name), xmp_path_2))
                else:
                    logging.debug(f"XMP file not found (neither '{base_name}.xmp' nor '{img_name}.xmp')")
                    images_without_xmp += 1

        for img_path, xmp_path in pairs:
            logging.debug(f"Matched image '{img_path}' with XMP '{xmp_path}'")

            try:
                width, height = avimage.readImageSize(img_path)
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

            # RealityScan coefficients: k1 k2 k3 k4 t1 t2
            disto_model = get_xmp_value(root, "DistortionModel")
            disto_str = get_xmp_value(root, "DistortionCoeficients")
            coeffs = [float(x) for x in disto_str.split()] if disto_str else [0.0] * 6
            if disto_model and not disto_model.startswith("brown"):
                logging.warning(f"Unsupported distortion model '{disto_model}' for {img_path}, distortion ignored")
                coeffs = [0.0] * 6
            elif coeffs[3] != 0.0:
                logging.warning(f"k4 coefficient not supported by AliceVision Brown model, ignored for {img_path}")
            k1, k2, k3, _, t1, t2 = coeffs

            intrinsic_id = id_counter
            v_id = id_counter
            p_id = id_counter
            id_counter += 1

            intrinsic = camera.createPinhole(camera.DISTORTION_BROWN, camera.UNDISTORTION_NONE,
                                             width, height, 1.0, 1.0, 0.0, 0.0)
            intrinsic.setDistortionParams([k1, k2, k3, t1, t2])

            intrinsic.setSensorWidth(node.sensorWidth.value)
            intrinsic.setSensorHeight(node.sensorHeight.value)
            intrinsic.setSerialNumber(node.serialNumber.value)
            intrinsic.setInitializationMode(camera.EInitMode_CALIBRATED)
            intrinsic.setFocalLength(focal_mm, 1.0)
            intrinsic.setInitialFocalLength(focal_mm, 1.0)
            intrinsic.setOffset(np.array([px, py]))
            data.getIntrinsics()[intrinsic_id] = intrinsic

            metadata = {"Make": node.cameraMake.value, "Model": node.cameraModel.value}
            data.getViews()[v_id] = sfmData.View(img_path, v_id, intrinsic_id, p_id, width, height,
                                                 sfmData.UndefinedIndexT, sfmData.UndefinedIndexT, metadata)

            pose = geometry.Pose3(rc_rotation_to_av(rot_str), rc_position_to_av(pos_str))
            data.getPoses()[p_id] = sfmData.CameraPose(pose, False)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        if not sfmDataIO.save(data, output_path, sfmDataIO.ALL):
            raise RuntimeError(f"Unable to save SfMData to {output_path}")

        logging.info(f"SfMData generated successfully: {len(data.getViews())} views processed.")
        if images_without_xmp:
            logging.warning(f"{images_without_xmp} image(s) without XMP file were skipped.")
