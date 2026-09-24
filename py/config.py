extension_tag = "ComfyUI Model Manager Neo"

extension_uri: str = ""  # set by __init__.py before any route exists


setting_key = {
    "api_key": {
        "civitai": "ModelManager.APIKey.Civitai",
        "huggingface": "ModelManager.APIKey.Hugging Face",
    },
    "download": {
        "max_task_count": "ModelManager.Download.MaxTaskCount",
    },
    # NOTE: the group name no longer says "scan" (the batch-scan feature was
    # removed) but the ID string MUST stay `ModelManager.Scan.IncludeHiddenFiles`
    # - it is the key ComfyUI persists the user's value under.
    "model_list": {"include_hidden_files": "ModelManager.Scan.IncludeHiddenFiles"},
    # ZipNN native pipeline (Phase 2): paranoid mode re-decodes and verifies
    # a compressed file before the original is removed (Plan §4.4.3-4,
    # default OFF). The env override MM_ZNN_PARANOID wins over this setting.
    "zipnn": {"paranoid": "ModelManager.ZipNN.Paranoid"},
}

user_agent = "Mozilla/5.0 (iPad; CPU OS 12_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"


from server import PromptServer

serverInstance = PromptServer.instance
routes = serverInstance.routes
