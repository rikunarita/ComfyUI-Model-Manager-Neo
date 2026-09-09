extension_tag = "ComfyUI Model Manager Neo"

extension_uri: str = None


setting_key = {
    "api_key": {
        "civitai": "ModelManager.APIKey.Civitai",
        "huggingface": "ModelManager.APIKey.HuggingFace",
    },
    "download": {
        "max_task_count": "ModelManager.Download.MaxTaskCount",
    },
    # NOTE: the group name no longer says "scan" (the batch-scan feature was
    # removed) but the ID string MUST stay `ModelManager.Scan.IncludeHiddenFiles`
    # - it is the key ComfyUI persists the user's value under.
    "model_list": {
        "include_hidden_files": "ModelManager.Scan.IncludeHiddenFiles"
    },
}

user_agent = "Mozilla/5.0 (iPad; CPU OS 12_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"


from server import PromptServer

serverInstance = PromptServer.instance
routes = serverInstance.routes
