import folder_paths

# NOTE: This is an experiment
# Add .gguf extension to supported_pt_extensions
folder_paths.supported_pt_extensions.add(".gguf")
# ZipNN delta files (`<ft>_delta_<base>.znn`) are managed models too: without
# this they would be invisible in the grids and could never be restored from
# the UI. (Batch-compressed bundles use `.znn.safetensors`, which already
# matches via `.safetensors`.)
folder_paths.supported_pt_extensions.add(".znn")

import os

from .py import config, utils

extension_uri = utils.normalize_path(os.path.dirname(__file__))

# Install requirements
requirements_path = utils.join_path(extension_uri, "requirements.txt")

with open(requirements_path, encoding="utf-8") as f:
    requirements = f.readlines()

requirements = [x.strip() for x in requirements]
requirements = [x for x in requirements if not x.startswith("#")]

uninstalled_package = [p for p in requirements if not utils.is_installed(p)]

if len(uninstalled_package) > 0:
    utils.print_info("Install dependencies...")
    for p in uninstalled_package:
        utils.pip_install(p)

# Init config settings
config.extension_uri = extension_uri

# Try to download web distribution
version = utils.get_current_version()
utils.download_web_distribution(version)

# Add api routes
from .py import compress, download, identify, information, manager, search, upload, upload_hf, upload_modelscope

routes = config.routes

manager.ModelManager().add_routes(routes)
# NOTE: use the shared singleton so that py/upload.py can register local
# upload tasks into the same download task system.
download.get_model_download().add_routes(routes)
information.Information().add_routes(routes)
upload.ModelUploader().add_routes(routes)
upload_hf.HfUploader().add_routes(routes)
upload_modelscope.MsUploader().add_routes(routes)
compress.ZipNNRoutes().add_routes(routes)
search.SearchRoutes().add_routes(routes)
identify.IdentifyRoutes().add_routes(routes)

WEB_DIRECTORY = "web"
NODE_CLASS_MAPPINGS = {}
__all__ = ["NODE_CLASS_MAPPINGS", "WEB_DIRECTORY"]
