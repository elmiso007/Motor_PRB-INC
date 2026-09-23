from pathlib import Path


def pytest_ignore_collect(collection_path, config, **kwargs):
    path = str(collection_path)
    lower = path.lower()
    if "cloud-code" in lower or "google-cloud-sdk" in lower:
        return True
    return False
