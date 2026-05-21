"""
_rc_utils.py
============
Internal helper shared by all RealityCapture Meshroom nodes.

Key responsibilities
--------------------
* normalize_path    — backslash conversion + mapped-drive → UNC resolution
                      via the Windows MPR API (WNetGetUniversalNameW).
                      Resolves in the CURRENT process (Meshroom) which does
                      have access to the user's drive mappings, unlike the
                      RC child process.
* run_rc            — Windows-safe subprocess launch (CREATE_NO_WINDOW).
* check_output_file — existence check that handles .rsproj directory bundles.
"""

import os
import ctypes
import platform
import subprocess
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# UNC resolution via Windows MPR API
# ─────────────────────────────────────────────────────────────────────────────

if platform.system() == "Windows":
    class _UNIVERSAL_NAME_INFO(ctypes.Structure):
        """
        Maps to Win32 UNIVERSAL_NAME_INFOW:
            typedef struct { LPWSTR lpUniversalName; } UNIVERSAL_NAME_INFOW;
        The pointer field is followed in the same buffer by the actual
        null-terminated wide-char string it points to.
        """
        _fields_ = [("lpUniversalName", ctypes.c_wchar_p)]


def _drive_to_unc(p: str) -> str:
    """
    Resolve a mapped drive letter to its UNC path using WNetGetUniversalNameW.

    Called in the Meshroom process, which inherits the user's drive mappings.
    The RC child process (CREATE_NO_WINDOW) does NOT inherit them, hence the
    "Access denied" errors when paths contain  T:\\  S:\\  etc.

    Returns the original path unchanged if:
    - not on Windows
    - the path does not start with a drive letter
    - the drive is local (not a network mapping)
    - the MPR call fails for any reason
    """
    if platform.system() != "Windows":
        return p
    if len(p) < 3 or p[1] != ":" or not p[0].isalpha():
        return p

    try:
        UNIVERSAL_NAME_INFO_LEVEL = 1
        buf_size = ctypes.c_ulong(1024)
        buf = ctypes.create_string_buffer(1024)

        ret = ctypes.windll.mpr.WNetGetUniversalNameW(
            ctypes.c_wchar_p(p),
            UNIVERSAL_NAME_INFO_LEVEL,
            buf,
            ctypes.byref(buf_size),
        )

        if ret == 0:  # NO_ERROR
            info = _UNIVERSAL_NAME_INFO.from_buffer(buf)
            unc = info.lpUniversalName
            if unc and unc.startswith("\\\\"):
                logger.debug("UNC resolved: %s  ->  %s", p, unc)
                return unc
        else:
            # ERROR_NOT_CONNECTED (2250) means local drive — not an error
            logger.debug("WNetGetUniversalNameW returned %d for %s", ret, p)

    except Exception as exc:
        logger.debug("_drive_to_unc failed for %s: %s", p, exc)

    return p


def normalize_path(p: str) -> str:
    """
    Prepare a path for RealityCapture:
      1. os.path.normpath  — forward slashes → backslashes
      2. _drive_to_unc     — T:\\... → \\\\server\\share\\...
    """
    if not p:
        return p
    p = os.path.normpath(p)
    p = _drive_to_unc(p)
    return p


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _looks_like_path(s: str) -> bool:
    return os.sep in s or "/" in s or (len(s) > 2 and s[1] == ":")


def _normalize_cmd(cmd: list) -> list:
    return [
        normalize_path(a) if (isinstance(a, str) and _looks_like_path(a) and "=" not in a) else a
        for a in cmd
    ]


def _fmt_cmd(cmd: list) -> str:
    return " ".join('"{}"'.format(a) if " " in str(a) else str(a) for a in cmd)


# ─────────────────────────────────────────────────────────────────────────────
# RC launcher
# ─────────────────────────────────────────────────────────────────────────────

def run_rc(cmd: list, node_logger: logging.Logger = None) -> str:
    """
    Launch RealityCapture and return its captured output.
    Raises RuntimeError on non-zero exit code.
    """
    log = node_logger or logger
    norm_cmd = _normalize_cmd(cmd)
    log.info("Launching RC:\n  %s", _fmt_cmd(norm_cmd))

    kwargs = dict(
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if platform.system() == "Windows":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    proc = subprocess.run(norm_cmd, **kwargs)

    output = proc.stdout or ""
    if output.strip():
        log.info("RC output:\n%s", output)

    if proc.returncode != 0:
        raise RuntimeError(
            "RealityCapture exited with code {}.\nOutput:\n{}".format(
                proc.returncode, output or "(no output captured)"
            )
        )
    return output


# ─────────────────────────────────────────────────────────────────────────────
# Output verification
# ─────────────────────────────────────────────────────────────────────────────

def check_output_file(path: str, label: str = "output file") -> None:
    """
    Assert that *path* exists after RC has run.
    Uses os.path.exists (not isfile) because .rsproj is a directory bundle.
    """
    norm = normalize_path(path)
    if os.path.exists(norm):
        return

    out_dir = os.path.dirname(norm)
    if os.path.isdir(out_dir):
        items = os.listdir(out_dir)
        detail = "Directory contents ({}):\n  {}".format(
            out_dir, "\n  ".join(items) if items else "(empty)"
        )
    else:
        detail = "Output directory does not exist: {}".format(out_dir)

    raise RuntimeError(
        "RC exited cleanly but the expected {} was not found:\n"
        "  {}\n\n{}".format(label, norm, detail)
    )
