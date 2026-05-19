"""Persistence backends for the Catalyst control-plane API.

The control plane currently has a small, well-bounded set of persistence
operations:

    * Idempotency cache (request key -> response payload)
    * Organisation structure (OUs, landing zones, environments, applications)
    * Service registry (config + deployment history)
    * Product instance inventory (lifecycle records)
    * Group membership ledger (audit of privileged write actions through the
      ``/iam/groups/{group}/members`` endpoint)

Two backends implement that contract:

    * :class:`InMemoryRepository` keeps everything in-process. It is used by
      unit tests (no AWS calls) and as a local-development fallback.
    * :class:`DynamoDBRepository` reads/writes a single DynamoDB table using
      the standard PK/SK single-table pattern. It is used in production when
      the runtime resolves a real DynamoDB table name from configuration.

Repositories are intentionally thin and free of HTTP / FastAPI concerns so
they can be exercised with ``moto`` integration tests.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from .errors import with_aws_retry


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _empty_org_structure() -> dict[str, list[dict]]:
    return {"ous": [], "landing_zones": [], "environments": [], "applications": []}


class Repository(ABC):
    """Persistence interface used by the Catalyst FastAPI handlers."""

    def now(self) -> datetime:
        return _now()

    @abstractmethod
    def get_idempotent(self, key: str | None) -> dict | None:
        pass

    @abstractmethod
    def put_idempotent(self, key: str, payload: dict) -> None:
        pass

    @abstractmethod
    def append_org_record(
        self,
        tenant: str,
        kind: str,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        pass

    @abstractmethod
    def get_organization(self, tenant: str) -> dict:
        pass

    @abstractmethod
    def init_service(self, construct: str) -> None:
        pass

    @abstractmethod
    def get_service(self, construct: str) -> dict | None:
        pass

    @abstractmethod
    def append_service_deployment(self, construct: str, deployment: dict) -> None:
        pass

    @abstractmethod
    def update_service_config(self, construct: str, params: dict[str, str]) -> None:
        pass

    @abstractmethod
    def record_group_action(self, group: str, action: str, user_arn: str) -> None:
        pass

    @abstractmethod
    def list_group_actions(self, group: str) -> list[str]:
        pass

    @abstractmethod
    def put_product(self, key: str, record: dict) -> None:
        pass

    @abstractmethod
    def get_product(self, key: str) -> dict | None:
        pass

    @abstractmethod
    def list_products(self) -> list[dict]:
        pass

    # ----- Product-catalog deployment records (#103 — CAT-3) ---------------
    # These are distinct from the per-tenant product_instances above (which
    # back the existing /products/deploy flow from #167). Catalog deployment
    # rows are keyed on a per-deploy UUID and looked up either by
    # deployment_id (status) or by the composite idempotency key
    # f"product:{product_id}:{construct_address}:{idempotency_key}" for replay.

    @abstractmethod
    def record_product_deployment(
        self,
        *,
        product_id: str,
        construct_address: str,
        deployment_id: str,
        idempotency_key: str | None,
        payload: dict,
        created_at: str,
    ) -> None:
        pass

    @abstractmethod
    def get_product_deployment(self, deployment_id: str) -> dict | None:
        pass

    @abstractmethod
    def get_product_deployment_by_idem_key(
        self, idempotency_key: str
    ) -> dict | None:
        pass

    @abstractmethod
    def list_product_deployments(self, product_id: str) -> list[dict]:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass


_ORG_KINDS = {"ous", "landing_zones", "environments", "applications"}


class InMemoryRepository(Repository):
    """Process-local backing store. Suitable for tests and local dev."""

    def __init__(self) -> None:
        self.organizations: dict[str, dict] = {}
        self.services: dict[str, dict] = {}
        self.idempotency: dict[str, dict] = {}
        self.product_instances: dict[str, dict] = {}
        self.groups: dict[str, set[str]] = defaultdict(set)
        # #103 — product-catalog deployments. Two indexes so the handler
        # can replay by composite idempotency key (cheap O(1) lookup) and
        # the get-status path can resolve by deployment_id without scanning.
        self.product_deployments: dict[str, dict] = {}
        self.product_deployments_by_idem: dict[str, dict] = {}

    def get_idempotent(self, key: str | None) -> dict | None:
        if not key:
            return None
        return self.idempotency.get(key)

    def put_idempotent(self, key: str, payload: dict) -> None:
        self.idempotency[key] = payload

    def append_org_record(
        self,
        tenant: str,
        kind: str,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        if kind not in _ORG_KINDS:
            raise ValueError(f"unknown org kind: {kind}")
        self.organizations.setdefault(tenant, _empty_org_structure())
        record: dict[str, Any] = {"name": name, "created_at": self.now().isoformat()}
        if attributes:
            # explicit fields take precedence over caller-supplied keys with
            # the same name (so an attacker-supplied ``created_at`` cannot
            # rewrite history)
            for key, value in attributes.items():
                if key in {"name", "created_at"}:
                    continue
                record[key] = value
        self.organizations[tenant][kind].append(record)

    def get_organization(self, tenant: str) -> dict:
        return self.organizations.get(tenant, {})

    def init_service(self, construct: str) -> None:
        self.services.setdefault(
            construct,
            {"deployments": [], "config": {}, "created_at": self.now().isoformat()},
        )

    def get_service(self, construct: str) -> dict | None:
        return self.services.get(construct)

    def append_service_deployment(self, construct: str, deployment: dict) -> None:
        self.init_service(construct)
        self.services[construct]["deployments"].append(deployment)

    def update_service_config(self, construct: str, params: dict[str, str]) -> None:
        self.init_service(construct)
        self.services[construct]["config"].update(params)

    def record_group_action(self, group: str, action: str, user_arn: str) -> None:
        self.groups[group].add(f"{action}:{user_arn}")

    def list_group_actions(self, group: str) -> list[str]:
        return sorted(self.groups.get(group, set()))

    def put_product(self, key: str, record: dict) -> None:
        self.product_instances[key] = record

    def get_product(self, key: str) -> dict | None:
        return self.product_instances.get(key)

    def list_products(self) -> list[dict]:
        return list(self.product_instances.values())

    # ----- Product-catalog deployment records (#103) ----------------------

    def record_product_deployment(
        self,
        *,
        product_id: str,
        construct_address: str,
        deployment_id: str,
        idempotency_key: str | None,
        payload: dict,
        created_at: str,
    ) -> None:
        record = {
            "product_id": product_id,
            "construct_address": construct_address,
            "deployment_id": deployment_id,
            "idempotency_key": idempotency_key,
            "payload": payload,
            "created_at": created_at,
        }
        self.product_deployments[deployment_id] = record
        if idempotency_key:
            # Store the payload directly under the idempotency key so the
            # replay path can return the exact dict the caller saw on the
            # first invocation (without us having to remap fields).
            self.product_deployments_by_idem[idempotency_key] = payload

    def get_product_deployment(self, deployment_id: str) -> dict | None:
        return self.product_deployments.get(deployment_id)

    def get_product_deployment_by_idem_key(
        self, idempotency_key: str
    ) -> dict | None:
        return self.product_deployments_by_idem.get(idempotency_key)

    def list_product_deployments(self, product_id: str) -> list[dict]:
        return [
            r for r in self.product_deployments.values()
            if r["product_id"] == product_id
        ]

    def clear(self) -> None:
        self.organizations.clear()
        self.services.clear()
        self.idempotency.clear()
        self.product_instances.clear()
        self.groups.clear()
        self.product_deployments.clear()
        self.product_deployments_by_idem.clear()


# DynamoDB single-table key conventions (kept narrow on purpose; new entities
# should add their own PK prefix rather than overload an existing one).
_PK_ORG = "ORG#"
_PK_SVC = "SVC#"
_SK_SVC_META = "META"
_SK_SVC_DEPLOY_PREFIX = "DEPLOY#"
_PK_IDEM = "IDEM#"
_SK_IDEM = "RESULT"
_PK_PRODUCT = "PROD#"
_SK_PRODUCT = "INSTANCE"
_PK_GROUP = "GROUP#"
_SK_GROUP_ACTION_PREFIX = "ACTION#"
# #103 — product-catalog deployment records. PK groups all deployments of
# a given product so list_product_deployments is a single Query; we also
# write a sidecar IDEM_PROD# row keyed by the composite idempotency key so
# replay is O(1) without a GSI.
_PK_PRODUCT_DEPLOY_PREFIX = "PRODDEP#"
_SK_PRODUCT_DEPLOY_PREFIX = "DEPLOY#"
_PK_PRODUCT_DEPLOY_IDEM_PREFIX = "PRODDEP_IDEM#"
_SK_PRODUCT_DEPLOY_IDEM = "PAYLOAD"

_IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60


class DynamoDBRepository(Repository):
    """DynamoDB-backed implementation using a single PK/SK table.

    Parameters
    ----------
    table_name:
        DynamoDB table to use. The schema must match
        ``infrastructure/modules/dynamodb`` (``pk``/``sk`` strings, optional
        ``expires_at`` TTL attribute).
    table:
        Optional pre-built ``boto3`` Table resource. Mostly useful for tests
        which pass a ``moto``-mocked resource. When omitted, a default
        ``boto3.resource('dynamodb')`` is used.
    idempotency_ttl_seconds:
        Lifetime for idempotency cache entries, written to the ``expires_at``
        attribute. The default (24h) is well under the 7d ``mock_aws`` cap and
        comfortably longer than typical client retry windows.
    """

    def __init__(
        self,
        table_name: str,
        *,
        table: Any | None = None,
        idempotency_ttl_seconds: int = _IDEMPOTENCY_TTL_SECONDS,
    ) -> None:
        if not table_name:
            raise ValueError("table_name is required")
        self._table_name = table_name
        self._idempotency_ttl_seconds = idempotency_ttl_seconds
        if table is not None:
            self._table = table
        else:
            import boto3  # imported lazily so unit tests don't require boto3

            self._table = boto3.resource("dynamodb").Table(table_name)

    @property
    def table_name(self) -> str:
        return self._table_name

    # The four internal helpers below are the only methods in this class
    # that touch the boto3 client surface — every public method routes
    # through one or more of them. Applying ``@with_aws_retry()`` here
    # (instead of at the public-method level) means a transient throttle
    # gets a fresh attempt on JUST the failed call, not a replay of the
    # whole read-modify-write — which keeps the retry semantically safe
    # for the multi-step public methods (e.g. ``append_org_record`` does
    # ``_get`` then ``_put``; we don't want the ``_get`` re-running just
    # because the ``_put`` got throttled).

    @with_aws_retry()
    def _put(self, item: dict) -> None:
        self._table.put_item(Item=item)

    @with_aws_retry()
    def _get(self, pk: str, sk: str) -> dict | None:
        response = self._table.get_item(Key={"pk": pk, "sk": sk})
        return response.get("Item")

    @with_aws_retry()
    def _query(self, pk: str, sk_prefix: str | None = None) -> list[dict]:
        from boto3.dynamodb.conditions import Key

        condition = Key("pk").eq(pk)
        if sk_prefix:
            condition = condition & Key("sk").begins_with(sk_prefix)
        response = self._table.query(KeyConditionExpression=condition)
        return response.get("Items", [])

    @with_aws_retry()
    def _scan_pk_prefix(self, pk_prefix: str) -> list[dict]:
        from boto3.dynamodb.conditions import Attr

        items: list[dict] = []
        kwargs = {"FilterExpression": Attr("pk").begins_with(pk_prefix)}
        while True:
            response = self._table.scan(**kwargs)
            items.extend(response.get("Items", []))
            last = response.get("LastEvaluatedKey")
            if not last:
                break
            kwargs["ExclusiveStartKey"] = last
        return items

    def get_idempotent(self, key: str | None) -> dict | None:
        if not key:
            return None
        item = self._get(_PK_IDEM + key, _SK_IDEM)
        if item is None:
            return None
        return item.get("payload")

    def put_idempotent(self, key: str, payload: dict) -> None:
        expires_at = int((self.now() + timedelta(seconds=self._idempotency_ttl_seconds)).timestamp())
        self._put(
            {
                "pk": _PK_IDEM + key,
                "sk": _SK_IDEM,
                "payload": payload,
                "expires_at": expires_at,
            }
        )

    def append_org_record(
        self,
        tenant: str,
        kind: str,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        if kind not in _ORG_KINDS:
            raise ValueError(f"unknown org kind: {kind}")
        item = self._get(_PK_ORG + tenant, "STRUCT") or {
            "pk": _PK_ORG + tenant,
            "sk": "STRUCT",
            **_empty_org_structure(),
        }
        item.setdefault(kind, [])
        record: dict[str, Any] = {"name": name, "created_at": self.now().isoformat()}
        if attributes:
            for key, value in attributes.items():
                if key in {"name", "created_at"}:
                    continue
                record[key] = value
        item[kind].append(record)
        self._put(item)

    def get_organization(self, tenant: str) -> dict:
        item = self._get(_PK_ORG + tenant, "STRUCT")
        if not item:
            return {}
        return {kind: item.get(kind, []) for kind in _ORG_KINDS}

    def init_service(self, construct: str) -> None:
        existing = self._get(_PK_SVC + construct, _SK_SVC_META)
        if existing:
            return
        self._put(
            {
                "pk": _PK_SVC + construct,
                "sk": _SK_SVC_META,
                "config": {},
                "created_at": self.now().isoformat(),
            }
        )

    def get_service(self, construct: str) -> dict | None:
        meta = self._get(_PK_SVC + construct, _SK_SVC_META)
        if not meta:
            return None
        deployments = [
            {"image_tag": item["image_tag"], "at": item["at"]}
            for item in self._query(_PK_SVC + construct, _SK_SVC_DEPLOY_PREFIX)
        ]
        deployments.sort(key=lambda d: d["at"])
        return {
            "deployments": deployments,
            "config": meta.get("config", {}),
            "created_at": meta.get("created_at"),
        }

    def append_service_deployment(self, construct: str, deployment: dict) -> None:
        self.init_service(construct)
        self._put(
            {
                "pk": _PK_SVC + construct,
                "sk": _SK_SVC_DEPLOY_PREFIX + deployment["at"],
                "image_tag": deployment["image_tag"],
                "at": deployment["at"],
            }
        )

    def update_service_config(self, construct: str, params: dict[str, str]) -> None:
        self.init_service(construct)
        meta = self._get(_PK_SVC + construct, _SK_SVC_META) or {
            "pk": _PK_SVC + construct,
            "sk": _SK_SVC_META,
            "config": {},
            "created_at": self.now().isoformat(),
        }
        config = dict(meta.get("config", {}))
        config.update(params)
        meta["config"] = config
        self._put(meta)

    def record_group_action(self, group: str, action: str, user_arn: str) -> None:
        self._put(
            {
                "pk": _PK_GROUP + group,
                "sk": _SK_GROUP_ACTION_PREFIX + f"{action}:{user_arn}",
                "action": action,
                "user_arn": user_arn,
                "at": self.now().isoformat(),
            }
        )

    def list_group_actions(self, group: str) -> list[str]:
        items = self._query(_PK_GROUP + group, _SK_GROUP_ACTION_PREFIX)
        return sorted(f"{i['action']}:{i['user_arn']}" for i in items)

    def put_product(self, key: str, record: dict) -> None:
        self._put({"pk": _PK_PRODUCT + key, "sk": _SK_PRODUCT, "record": record})

    def get_product(self, key: str) -> dict | None:
        item = self._get(_PK_PRODUCT + key, _SK_PRODUCT)
        if not item:
            return None
        return item.get("record")

    def list_products(self) -> list[dict]:
        items = self._scan_pk_prefix(_PK_PRODUCT)
        return [item["record"] for item in items if "record" in item]

    # ----- Product-catalog deployment records (#103) ----------------------
    #
    # PK layout:
    #   - PRODDEP#{product_id} / DEPLOY#{deployment_id}    -> full record
    #   - PRODDEP_IDEM#{idem_key} / PAYLOAD                -> cached payload
    #
    # The PRODDEP# rows are queryable by product_id for the inventory
    # surface (list_product_deployments). The PRODDEP_IDEM# rows give
    # O(1) replay lookup without a GSI; we store the full payload there
    # so the replay path can return the exact dict the caller saw on
    # the first invocation.

    def record_product_deployment(
        self,
        *,
        product_id: str,
        construct_address: str,
        deployment_id: str,
        idempotency_key: str | None,
        payload: dict,
        created_at: str,
    ) -> None:
        record = {
            "product_id": product_id,
            "construct_address": construct_address,
            "deployment_id": deployment_id,
            "idempotency_key": idempotency_key,
            "payload": payload,
            "created_at": created_at,
        }
        self._put(
            {
                "pk": _PK_PRODUCT_DEPLOY_PREFIX + product_id,
                "sk": _SK_PRODUCT_DEPLOY_PREFIX + deployment_id,
                "record": record,
            }
        )
        if idempotency_key:
            self._put(
                {
                    "pk": _PK_PRODUCT_DEPLOY_IDEM_PREFIX + idempotency_key,
                    "sk": _SK_PRODUCT_DEPLOY_IDEM,
                    "payload": payload,
                }
            )

    def get_product_deployment(self, deployment_id: str) -> dict | None:
        # Without a GSI we can't query by deployment_id alone; this is a
        # scan over PRODDEP# rows. Fine for the rare get-by-id path; the
        # hot replay path goes through get_product_deployment_by_idem_key
        # which is O(1).
        for item in self._scan_pk_prefix(_PK_PRODUCT_DEPLOY_PREFIX):
            record = item.get("record")
            if record and record.get("deployment_id") == deployment_id:
                return record
        return None

    def get_product_deployment_by_idem_key(
        self, idempotency_key: str
    ) -> dict | None:
        item = self._get(
            _PK_PRODUCT_DEPLOY_IDEM_PREFIX + idempotency_key,
            _SK_PRODUCT_DEPLOY_IDEM,
        )
        if not item:
            return None
        return item.get("payload")

    def list_product_deployments(self, product_id: str) -> list[dict]:
        items = self._query(
            _PK_PRODUCT_DEPLOY_PREFIX + product_id, _SK_PRODUCT_DEPLOY_PREFIX
        )
        return [item["record"] for item in items if "record" in item]

    @with_aws_retry()
    def clear(self) -> None:  # pragma: no cover - destructive helper for tests only
        items = self._table.scan().get("Items", [])
        for item in items:
            self._table.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})


_repo_singleton: Repository | None = None


def get_repository() -> Repository:
    """Return the process-wide repository, initialising on first call.

    Resolution order:

    1. ``CATALYST_REPOSITORY=memory`` -> :class:`InMemoryRepository`
    2. ``CATALYST_REPOSITORY=dynamodb`` (or any other value) -> resolve table
       name via :func:`catalyst.settings.get_settings` and return
       :class:`DynamoDBRepository`.

    The default mode is ``memory`` so unit tests and local development do
    not need AWS credentials.
    """

    global _repo_singleton
    if _repo_singleton is not None:
        return _repo_singleton

    from .settings import get_settings

    settings = get_settings()
    if settings.repository_backend == "dynamodb":
        if not settings.dynamodb_table_name:
            raise RuntimeError(
                "DynamoDB repository requested but no table name resolved; "
                "set CATALYST_DYNAMODB_TABLE or CATALYST_DYNAMODB_TABLE_PARAMETER"
            )
        _repo_singleton = DynamoDBRepository(settings.dynamodb_table_name)
    else:
        _repo_singleton = InMemoryRepository()
    return _repo_singleton


def set_repository(repository: Repository) -> None:
    """Override the process-wide repository (test seam)."""

    global _repo_singleton
    _repo_singleton = repository


def reset_repository() -> None:
    """Drop the cached repository so the next ``get_repository`` re-resolves."""

    global _repo_singleton
    _repo_singleton = None


# Backwards-compatible module-level handle. Existing imports (`from
# .repository import repo`) keep working; tests can call ``repo.clear()``
# on the in-memory default.
repo: Repository = get_repository()
