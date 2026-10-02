from __future__ import annotations

import stat
import time
from dataclasses import replace
from pathlib import Path
from threading import Lock

from .campaign_page_refresh import (
    CampaignRefreshTransactionError, StaleCampaignRefreshPlan, ancestor_witnesses, discover_source_snapshot,
    observe_path, validate_witnesses,
)
from .db import get_db
from .repository import Repository, load_campaign, load_campaign_config, resolve_campaign_links


class _DatabaseAuthoritativePageStore:
    """Delegate page reads while suppressing filesystem-to-database seeding."""

    def __init__(self, page_store) -> None:
        self._page_store = page_store

    @staticmethod
    def ensure_campaign_seeded(_campaign_slug: str, _content_dir: Path) -> None:
        return None

    def __getattr__(self, name: str):
        return getattr(self._page_store, name)


class RepositoryStore:
    def __init__(self, campaigns_dir: Path, *, page_store, reload_enabled: bool,
                 scan_interval_seconds: int) -> None:
        self.campaigns_dir = campaigns_dir
        self.page_store = page_store
        self.reload_enabled = reload_enabled
        self.scan_interval_seconds = max(scan_interval_seconds, 0)
        self._lock = Lock()
        self._repository: Repository | None = None
        self._repository_input_specs: tuple[tuple[Path, Path], ...] = ()
        self._config_inventory: tuple = ()
        self._source_tokens: dict[Path, tuple | None] = {}
        self._last_check_monotonic = 0.0
        self._last_loaded_unix = 0.0

    @staticmethod
    def _require_refresh_admission() -> None:
        if get_db().in_transaction:
            raise CampaignRefreshTransactionError("Campaign refresh requires a connection without an active transaction.")

    def get(self) -> Repository:
        from .committed_publication import active
        if active():
            return self.refresh_from_database()
        with self._lock:
            if self._repository is None:
                self._reload_repository()
            elif self.reload_enabled:
                now = time.monotonic()
                if now - self._last_check_monotonic >= self.scan_interval_seconds:
                    try:
                        paths, inventory = self._discover_configs()
                        old_specs = {spec.config_path: spec for spec in self._repository.config_specs}
                        specs = []
                        selected = set()
                        for path in paths:
                            old = old_specs.get(path)
                            witnesses = ancestor_witnesses(path)
                            if old is None or witnesses != old.witnesses:
                                self._require_refresh_admission()
                                spec = load_campaign_config(path)
                                selected.add(path)
                            else:
                                spec = replace(old, witnesses=witnesses)
                            specs.append(spec)
                        observed = {}
                        for spec in specs:
                            snapshot = discover_source_snapshot(spec.content_root)
                            token = (snapshot.witnesses, self.page_store.protection_identity(spec.slug))
                            observed[spec.config_path] = token
                            if token != self._source_tokens.get(spec.config_path):
                                selected.add(spec.config_path)
                        removed = set(old_specs) - set(paths)
                        slugs = [spec.slug for spec in specs]
                        prior_slugs = [spec.slug for spec in self._repository.config_specs]
                        ambiguous = (len(slugs) != len(set(slugs))
                                     or len(prior_slugs) != len(set(prior_slugs))
                                     or len(old_specs) != len(self._repository.config_specs))
                        if selected or removed or inventory != self._config_inventory:
                            self._reload_repository(
                                specs=tuple(specs), inventory=inventory,
                                selected=None if ambiguous else selected,
                            )
                        else:
                            self._validate_generation(tuple(specs), inventory, observed)
                            self._last_check_monotonic = now
                    except CampaignRefreshTransactionError:
                        raise
                    except Exception:
                        self._invalidate_failed_generation()
                        raise
            return self._repository

    def status(self) -> dict[str, object]:
        result = dict(reload_enabled=self.reload_enabled, scan_interval_seconds=self.scan_interval_seconds,
                      last_loaded_unix=self._last_loaded_unix, campaigns_dir=str(self.campaigns_dir))
        from .committed_publication import active
        if active():
            result.update(config_mirror_conflicts=getattr(self, "_config_conflicts", ()),
                          page_mirror_conflicts=dict(self.page_store.mirror_conflicts))
        return result

    def refresh(self) -> Repository:
        with self._lock:
            self._reload_repository()
            return self._repository

    def refresh_from_database(self) -> Repository:
        """Build from committed rows only; filesystem source evidence is not consumed."""
        with self._lock:
            self._reload_repository(seed_from_filesystem=False)
            return self._repository

    def _discover_configs(self) -> tuple[tuple[Path, ...], tuple]:
        witnesses = list(ancestor_witnesses(self.campaigns_dir))
        root = witnesses[-1]
        paths = []
        if root.target_identity is not None:
            if root.target_identity[2] != stat.S_IFDIR:
                raise ValueError("Campaign configuration root must be a directory.")
            for child in sorted(self.campaigns_dir.iterdir()):
                witness = observe_path(child)
                if witness.target_identity is None or witness.target_identity[2] != stat.S_IFDIR:
                    continue
                witnesses.append(witness)
                path = child / "campaign.yaml"
                config_witness = observe_path(path)
                witnesses.append(config_witness)
                if config_witness.target_identity is not None:
                    paths.append(path)
                elif config_witness.lexical_identity is not None:
                    raise ValueError("Campaign configuration target is unavailable.")
        elif root.lexical_identity is not None:
            raise ValueError("Campaign configuration root target is unavailable.")
        validate_witnesses(witnesses, reason="config")
        return tuple(sorted(paths)), tuple(witnesses)

    def _validate_generation(self, specs, inventory, tokens) -> None:
        validate_witnesses(inventory, reason="config")
        for spec in specs:
            validate_witnesses(spec.witnesses, reason="config")
            token = tokens.get(spec.config_path)
            if token is not None:
                validate_witnesses(token[0])
                if self.page_store.protection_identity(spec.slug) != token[1]:
                    raise StaleCampaignRefreshPlan("protection")

    def _invalidate_failed_generation(self) -> None:
        # Earlier campaigns may already have committed. The next call must build
        # all views anew; never acknowledge a failed or partial shared generation.
        self._repository = None
        self._repository_input_specs = ()
        self._config_inventory = ()
        self._source_tokens = {}
        self._last_check_monotonic = 0.0

    def _reload_repository(self, *, seed_from_filesystem: bool = True,
                           specs=None, inventory=None, selected=None) -> None:
        # Admission happens before source planning and outside failure cleanup;
        # rejecting a caller transaction neither rolls it back nor invalidates
        # the previously committed shared view.
        from .committed_publication import active
        if not active():
            self._require_refresh_admission()
        try:
            if active():
                from .committed_publication import read_snapshot
                read_snapshot(self._reload_committed_repository)()
                return
            if specs is None:
                paths, inventory = self._discover_configs()
                specs = tuple(load_campaign_config(path) for path in paths)
            if inventory is None:
                raise RuntimeError("Campaign refresh requires configuration evidence.")
            loading_store = self.page_store if seed_from_filesystem else _DatabaseAuthoritativePageStore(self.page_store)
            campaigns = {}
            replacements = set()
            tokens = {}
            old_repository = self._repository
            old_specs = {spec.config_path: spec for spec in old_repository.config_specs} if old_repository else {}
            for spec in specs:
                rebuild = selected is None or spec.config_path in selected or old_repository is None
                if rebuild:
                    if seed_from_filesystem:
                        pages, token = self.page_store.sync_campaign_view(spec.slug, spec.content_root)
                        campaign = load_campaign(spec.config_path, loading_store, config_spec=spec, page_snapshot=pages)
                        tokens[spec.config_path] = token
                    else:
                        campaign = load_campaign(spec.config_path, loading_store, config_spec=spec)
                        old = old_specs.get(spec.config_path)
                        tokens[spec.config_path] = (self._source_tokens.get(spec.config_path)
                                                   if old is not None and old.slug == spec.slug
                                                   and old.content_root == spec.content_root else None)
                    replacements.add(spec.slug)
                else:
                    campaign = old_repository.campaigns[spec.slug]
                    tokens[spec.config_path] = self._source_tokens.get(spec.config_path)
                campaigns[spec.slug] = campaign
            for slug, campaign in campaigns.items():
                if slug in replacements:
                    resolve_campaign_links(campaign)
            # Only filesystem-consuming builds validate/publish source evidence.
            # DB-authoritative recovery retains previous source tokens as dirty
            # evidence for a subsequent ordinary check, without scanning source.
            self._validate_generation(specs, inventory, tokens if seed_from_filesystem else {})
            repository = Repository(campaigns, self.page_store,
                                    tuple((spec.config_path, spec.content_root) for spec in specs), specs)
            self._repository = repository
            self._repository_input_specs = repository.input_specs
            self._config_inventory = inventory
            self._source_tokens = tokens
            self._last_check_monotonic = time.monotonic()
            self._last_loaded_unix = time.time()
        except Exception:
            self._invalidate_failed_generation()
            raise

    def _reload_committed_repository(self):
        rows = get_db().execute("SELECT campaign_slug FROM committed_source_current WHERE object_kind='config' ORDER BY campaign_slug").fetchall()
        campaigns, committed_specs = {}, []
        config_conflicts = []
        for row in rows:
            try:
                spec = load_campaign_config(self.campaigns_dir / row[0] / "campaign.yaml")
                campaign = load_campaign(spec.config_path, _DatabaseAuthoritativePageStore(self.page_store), config_spec=spec)
            except ValueError:
                continue
            from .committed_publication import inspect_page_mirrors, config, digest, _mirror_bytes
            self.page_store.mirror_conflicts[spec.slug] = inspect_page_mirrors(spec.slug, spec.content_root)
            source, _ = config(spec.slug)
            try:
                observed = _mirror_bytes(spec.config_path)
                if digest(observed) != source["primary_sha256"]:
                    config_conflicts.append(spec.slug)
            except (OSError, ValueError):
                config_conflicts.append(spec.slug)
            committed_specs.append(spec)
            resolve_campaign_links(campaign)
            campaigns[campaign.slug] = campaign
        self._repository = Repository(campaigns, self.page_store, (), tuple(committed_specs))
        self._config_conflicts = tuple(config_conflicts)
        self._last_loaded_unix = time.time()
        return
