# Copyright 2026 WATT
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""manifest_loader — Layer 1 sidecar yaml loading.

Scans `behavior_trees/**/*.meta.yaml` and parses into TreeManifest pydantic
models. The loader caches by file mtime so subsequent reloads only re-parse
changed files.

Layer 3 (self_check.py) consumes the load result to cross-check against
bt_schema_server's GetTreeSchema responses.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import ValidationError

from bt_web_bridge.models import TreeManifest

logger = logging.getLogger(__name__)


class ManifestLoadError(RuntimeError):
    """One or more manifest yaml files failed to load."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__('\n  - ' + '\n  - '.join(errors))


class ManifestLoader:
    """Loads and caches all `*.meta.yaml` sidecar files.

    Sidecars live next to the corresponding tree XML in dev-behavior-tree:
        behavior_trees/DockTree.xml
        behavior_trees/DockTree.meta.yaml

    Search rule:
      - recursively walk `manifest_dir` for files ending in `.meta.yaml`
      - file basename (minus `.meta.yaml`) must match a `tree_id` field inside.
    """

    def __init__(self, manifest_dir: str | Path):
        self.manifest_dir = Path(manifest_dir).resolve()
        self._cache: dict[str, TreeManifest] = {}
        self._mtimes: dict[Path, float] = {}

    def reload(self) -> dict[str, TreeManifest]:
        """Re-scan the manifest directory. Returns tree_id → TreeManifest map."""
        if not self.manifest_dir.is_dir():
            raise ManifestLoadError(
                [f"manifest_dir not a directory: {self.manifest_dir}"]
            )

        found: dict[str, TreeManifest] = {}
        errors: list[str] = []

        for path in sorted(self.manifest_dir.rglob('*.meta.yaml')):
            mtime = path.stat().st_mtime
            cached_mtime = self._mtimes.get(path)
            if cached_mtime == mtime:
                # Cache hit — find the manifest by path basename
                tree_id_from_name = path.name[:-len('.meta.yaml')]
                if tree_id_from_name in self._cache:
                    found[tree_id_from_name] = self._cache[tree_id_from_name]
                    continue

            try:
                with path.open('r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                if not isinstance(data, dict):
                    errors.append(f"{path}: yaml top-level must be a mapping")
                    continue
                manifest = TreeManifest.model_validate(data)
            except yaml.YAMLError as e:
                errors.append(f"{path}: yaml parse error — {e}")
                continue
            except ValidationError as e:
                errors.append(f"{path}: schema validation failed — {e}")
                continue

            # filename ↔ tree_id consistency check
            expected = path.name[:-len('.meta.yaml')]
            if manifest.tree_id != expected:
                errors.append(
                    f"{path}: tree_id '{manifest.tree_id}' does not match "
                    f"filename '{expected}'"
                )
                continue

            # Duplicate detection — meta.yaml under multiple dirs.
            if manifest.tree_id in found:
                errors.append(
                    f"{path}: duplicate tree_id '{manifest.tree_id}' "
                    f"(already loaded from another file)"
                )
                continue

            found[manifest.tree_id] = manifest
            self._mtimes[path] = mtime
            logger.info("manifest loaded: %s (%s)", manifest.tree_id, path)

        if errors:
            raise ManifestLoadError(errors)

        self._cache = found
        # Forget stale mtime entries (deleted files).
        live_paths = {path for path in self._mtimes if path.exists()}
        self._mtimes = {p: t for p, t in self._mtimes.items() if p in live_paths}

        logger.info(
            "manifest_loader: %d tree(s) loaded from %s",
            len(found), self.manifest_dir,
        )
        return found

    def get_all(self) -> dict[str, TreeManifest]:
        """Return cached manifests. Call `reload()` first."""
        return dict(self._cache)

    def get(self, tree_id: str) -> TreeManifest | None:
        return self._cache.get(tree_id)
