"""Reviewed operation inventory and schemas for agent clients.

New public routes must be classified here before CI accepts them. Agents use
stable operation names, not arbitrary URLs, headers or process commands.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path


# Names are independent of FastAPI's generated operationId. Keep them stable.
_OPERATIONS = """
health.live GET /health/live
health.ready GET /health/ready
health.sources GET /v1/health/sources
capture.source.list GET /v1/connectors/{connector_id}/capture-sources
capture.source.configure PUT /v1/connectors/{connector_id}/capture-sources/{source_id}
capture.source.status GET /v1/connectors/{connector_id}/capture-sources/{source_id}
capture.source.revoke DELETE /v1/connectors/{connector_id}/capture-sources/{source_id}
capture.policy.review GET /v1/connectors/{connector_id}/capture-sources/{source_id}/policy-review
capture.policy.versions GET /v1/connectors/{connector_id}/capture-sources/{source_id}/policies
capture.policy.change PUT /v1/connectors/{connector_id}/capture-sources/{source_id}/policy-transitions/{transition_id}
capture.grant.configure PUT /v1/capture-sources/{source_id}/grants/{grant_id}
capture.grant.status GET /v1/capture-grants/{grant_id}
capture.index.progress GET /v1/capture-grants/{grant_id}/index-progress
capture.grant.revoke DELETE /v1/capture-grants/{grant_id}
capture.pages.accept POST /v1/capture-grants/{grant_id}/pages
capture.pages.receipt GET /v1/capture-grants/{grant_id}/pages/{page_id}
capture.fences GET /v1/capture-grants/{grant_id}/fences
identity.me GET /v1/me
recovery.directory GET /v1/recovery-directory
recovery.configure PUT /v1/recovery-directory
vault.status GET /v1/vault/status
vault.list GET /v1/vault/entries
vault.get GET /v1/vault/entries/{entry_id}
vault.put PUT /v1/vault/entries/{entry_id}
vault.grants GET /v1/vault/entries/{entry_id}/grants
vault.grant PUT /v1/vault/entries/{entry_id}/grants
vault.delete POST /v1/vault/entries/{entry_id}/delete
vault.export POST /v1/vault/export
vault.import POST /v1/vault/import
vault.keepass.preview POST /v1/vault/keepass/preview
vault.keepass.import POST /v1/vault/keepass/import
vault.keepass.export POST /v1/vault/keepass/export
vault.audit GET /v1/vault/audit
spaces.list GET /v1/spaces
spaces.create POST /v1/spaces
spaces.get GET /v1/spaces/{space_id}
journal.status GET /v1/spaces/{space_id}/writeback
journal.configure PUT /v1/spaces/{space_id}/writeback
journal.push POST /v1/spaces/{space_id}/writeback/push
journal.organize POST /v1/spaces/{space_id}/writeback/organize
journal.backfill.status GET /v1/spaces/{space_id}/writeback/backfill
journal.backfill.start POST /v1/spaces/{space_id}/writeback/backfill
journal.backfill.control POST /v1/spaces/{space_id}/writeback/backfill/control
memory.buffer.preview POST /v1/spaces/{space_id}/buffer-import/preview
memory.buffer.import POST /v1/spaces/{space_id}/buffer-import
memory.journal.preview POST /v1/spaces/{space_id}/journal-recovery/preview
memory.journal.restore POST /v1/spaces/{space_id}/journal-recovery
memory.journal.upload.begin POST /v1/spaces/{space_id}/journal-recovery/uploads
memory.journal.upload.list GET /v1/spaces/{space_id}/journal-recovery/uploads
memory.journal.upload.status GET /v1/spaces/{space_id}/journal-recovery/uploads/{upload_id}
memory.journal.upload.files GET /v1/spaces/{space_id}/journal-recovery/uploads/{upload_id}/files
memory.journal.upload.chunk PUT /v1/spaces/{space_id}/journal-recovery/uploads/{upload_id}/files/{file_index}
memory.journal.upload.decisions GET /v1/spaces/{space_id}/journal-recovery/uploads/{upload_id}/decisions
memory.journal.upload.advance POST /v1/spaces/{space_id}/journal-recovery/uploads/{upload_id}/advance
principals.list GET /v1/principals
principals.create POST /v1/principals
principals.disable POST /v1/principals/{principal_id}/disable
keys.list GET /v1/keys
keys.create POST /v1/principals/{principal_id}/keys
keys.revoke DELETE /v1/keys/{key_id}
oauth.bindings GET /v1/oauth/bindings
oauth.bind POST /v1/oauth/bindings
oauth.revoke DELETE /v1/oauth/bindings/{binding_id}
oauth.configuration GET /v1/oauth/configuration
agents.package POST /v1/oauth/agent-package
oauth.connections GET /v1/oauth/connections
oauth.disconnect POST /v1/oauth/connections/{session_id}/revoke
sign_in.configuration GET /v1/sign-in/configuration
sign_in.account GET /v1/sign-in/account
sign_in.set_password PUT /v1/sign-in/account
sign_in.login POST /v1/sign-in/login
sign_in.refresh POST /v1/sign-in/refresh
sign_in.logout POST /v1/sign-in/logout
sign_in.sessions GET /v1/sign-in/sessions
sign_in.revoke_session DELETE /v1/sign-in/sessions/{session_id}
sign_in.invitations GET /v1/sign-in/invitations
sign_in.create_invitation POST /v1/sign-in/invitations
sign_in.preview_invitation POST /v1/sign-in/invitations/preview
sign_in.accept_invitation POST /v1/sign-in/invitations/accept
sign_in.revoke_invitation DELETE /v1/sign-in/invitations/{invitation_id}
company.configuration GET /v1/sign-in/company/configuration
company.check_configuration POST /v1/sign-in/company/configuration
company.start POST /v1/sign-in/company/start
company.finish POST /v1/sign-in/company/finish
company.links GET /v1/sign-in/company/links
company.link POST /v1/sign-in/company/links
company.revoke DELETE /v1/sign-in/company/links/{link_id}
grants.list GET /v1/spaces/{space_id}/grants
grants.set PUT /v1/spaces/{space_id}/grants/{principal_id}
grants.revoke DELETE /v1/spaces/{space_id}/grants/{principal_id}
memories.list GET /v1/spaces/{space_id}/memories
memories.save POST /v1/spaces/{space_id}/memories
memories.get GET /v1/memories/{memory_id}
memories.resolve GET /v1/spaces/{space_id}/resolve
memories.history GET /v1/memories/{memory_id}/revisions
memories.revise POST /v1/memories/{memory_id}/revisions
memories.review PUT /v1/memories/{memory_id}/review
memories.forget DELETE /v1/memories/{memory_id}
sources.get GET /v1/sources/{source_revision_id}
sources.attachment GET /v1/sources/{source_revision_id}/attachments/{attachment_id}
retrieval.search POST /v1/recall
retrieval.context POST /v1/context
knowledge.map POST /v1/knowledge
blocks.list GET /v1/spaces/{space_id}/blocks
blocks.set PUT /v1/spaces/{space_id}/blocks/{key}
operations.get GET /v1/operations/{operation_id}
operations.list GET /v1/spaces/{space_id}/operations
operations.retry POST /v1/operations/{operation_id}/retry
operations.status GET /v1/spaces/{space_id}/status
operations.activity GET /v1/spaces/{space_id}/activity
insights.space GET /v1/spaces/{space_id}/insights
insights.runtime GET /v1/insights/runtime
obsidian.export POST /v1/exports
connectors.list GET /v1/connectors
connectors.create POST /v1/connectors
connectors.disable DELETE /v1/connectors/{connector_id}
connectors.enable POST /v1/connectors/{connector_id}/enable
connectors.sync_status GET /v1/connectors/{connector_id}/sync
connectors.sync_request POST /v1/connectors/{connector_id}/sync
connectors.sync_report POST /v1/connectors/{connector_id}/sync/report
connectors.bindings GET /v1/connectors/{connector_id}/bindings
connectors.bind PUT /v1/connectors/{connector_id}/bindings
connectors.unbind DELETE /v1/connectors/{connector_id}/bindings
connectors.scopes GET /v1/connectors/{connector_id}/scopes
connectors.refresh POST /v1/connectors/{connector_id}/scopes
connectors.suspend POST /v1/connector-scopes/{space_id}/suspend
connectors.resume POST /v1/connector-scopes/{space_id}/resume
connectors.begin POST /v1/connector-scopes/{space_id}/runs
connectors.page POST /v1/connector-scopes/{space_id}/runs/{run_id}/pages
connectors.finish POST /v1/connector-scopes/{space_id}/runs/{run_id}/finish
connectors.proposals GET /v1/spaces/{space_id}/connector-proposals
connectors.resolve POST /v1/memories/{memory_id}/connector-proposal
embedding.settings GET /v1/spaces/{space_id}/embedding
embedding.choices GET /v1/spaces/{space_id}/embedding/choices
embedding.reindex POST /v1/spaces/{space_id}/embedding/reindex
embedding.control POST /v1/spaces/{space_id}/embedding/reindex/{run_id}/{action}
embedding.resume POST /v1/spaces/{space_id}/embedding/resume
librarian.settings GET /v1/spaces/{space_id}/librarian
librarian.coverage GET /v1/spaces/{space_id}/librarian/coverage
librarian.configure PUT /v1/spaces/{space_id}/librarian
librarian.models GET /v1/spaces/{space_id}/librarian/models
librarian.runs GET /v1/spaces/{space_id}/librarian/runs
librarian.start POST /v1/spaces/{space_id}/librarian/runs
librarian.run GET /v1/spaces/{space_id}/librarian/runs/{run_id}
librarian.cancel POST /v1/spaces/{space_id}/librarian/runs/{run_id}/cancel
librarian.items GET /v1/spaces/{space_id}/librarian/runs/{run_id}/items
librarian.proposals GET /v1/spaces/{space_id}/librarian/proposals
librarian.decide POST /v1/spaces/{space_id}/librarian/proposals/{proposal_id}/decision
evaluations.datasets GET /v1/spaces/{space_id}/evaluations/datasets
evaluations.create_dataset POST /v1/spaces/{space_id}/evaluations/datasets
evaluations.dataset GET /v1/spaces/{space_id}/evaluations/datasets/{dataset_id}
evaluations.remove_dataset DELETE /v1/spaces/{space_id}/evaluations/datasets/{dataset_id}
evaluations.runs GET /v1/spaces/{space_id}/evaluations/runs
evaluations.start POST /v1/spaces/{space_id}/evaluations/runs
evaluations.run GET /v1/spaces/{space_id}/evaluations/runs/{run_id}
evaluations.cancel POST /v1/spaces/{space_id}/evaluations/runs/{run_id}/cancel
evaluations.results GET /v1/spaces/{space_id}/evaluations/runs/{run_id}/results
evaluations.assess PUT /v1/spaces/{space_id}/evaluations/runs/{run_id}/results/{position}/assessment
evaluations.compare POST /v1/spaces/{space_id}/evaluations/compare
evaluations.export GET /v1/spaces/{space_id}/evaluations/runs/{run_id}/export
"""

READ_POST = frozenset(
    {
        "agents.package",
        "memory.buffer.preview",
        "memory.journal.preview",
        "retrieval.search",
        "retrieval.context",
        "knowledge.map",
        "obsidian.export",
        "evaluations.compare",
        "sign_in.preview_invitation",
        "company.check_configuration",
        "vault.export",
        "vault.keepass.preview",
        "vault.keepass.export",
    }
)
DOWNLOADS = frozenset({"sources.attachment", "obsidian.export", "evaluations.export"})
PRIVATE_INPUTS = frozenset(
    {
        "capture.pages.accept",
        "memory.buffer.preview",
        "memory.buffer.import",
        "memory.journal.preview",
        "memory.journal.restore",
        "memory.journal.upload.begin",
        "memory.journal.upload.chunk",
        "sign_in.set_password",
        "sign_in.login",
        "sign_in.refresh",
        "sign_in.logout",
        "sign_in.preview_invitation",
        "sign_in.accept_invitation",
        "company.start",
        "company.finish",
        "vault.put",
        "vault.export",
        "vault.import",
        "vault.keepass.preview",
        "vault.keepass.import",
        "vault.keepass.export",
    }
)
# These operations prove identity with their private input, not another user's
# bearer credential. Every route remains reviewed; none is silently omitted.
PUBLIC_AUTH = frozenset(
    {
        "sign_in.configuration",
        "sign_in.login",
        "sign_in.refresh",
        "sign_in.logout",
        "sign_in.preview_invitation",
        "sign_in.accept_invitation",
        "company.configuration",
        "company.check_configuration",
        "company.start",
        "company.finish",
    }
)
PUBLIC_CONFIGURATION = frozenset(
    {"sign_in.configuration", "company.configuration", "company.check_configuration"}
)
CONTRACT_PATH = Path(__file__).with_name("agent_contract.json")
DISCOVERY = frozenset(
    {
        ("get", "/v1/agent/operations"),
        ("get", "/v1/agent/operations/{operation_name}"),
    }
)


def _standalone(schema: dict, definitions: dict) -> dict:
    """Copy only reachable definitions; no network references or full schema dump."""
    result = copy.deepcopy(schema)
    selected = {}

    def visit(value):
        if isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, dict):
            ref = value.get("$ref")
            if ref:
                prefix = "#/components/schemas/"
                if not ref.startswith(prefix):
                    raise ValueError("Agent schemas must use local component references")
                name = ref[len(prefix) :]
                value["$ref"] = "#/$defs/" + name
                if name not in selected:
                    selected[name] = copy.deepcopy(definitions[name])
                    visit(selected[name])
            for key, child in value.items():
                if key != "$ref":
                    visit(child)

    visit(result)
    if selected:
        result["$defs"] = selected
    return result


def build_contract(openapi: dict) -> dict:
    entries = [line.split() for line in _OPERATIONS.splitlines() if line.strip()]
    known = {(method.lower(), path) for _, method, path in entries}
    actual = {
        (method, path)
        for path, routes in openapi["paths"].items()
        for method in routes
        if method in {"get", "post", "put", "patch", "delete"} and (method, path) not in DISCOVERY
    }
    if (
        known != actual
        or len(known) != len(entries)
        or len({entry[0] for entry in entries}) != len(entries)
    ):
        raise ValueError("Every public operation needs a unique, reviewed agent classification")
    definitions = openapi["components"]["schemas"]
    operations = []
    for name, method, path in entries:
        operation = openapi["paths"][path][method.lower()]
        properties, required, parameters, locations = {}, [], {}, {}
        required_parameters = []
        for parameter in operation.get("parameters", []):
            key, location = parameter["name"], parameter["in"]
            if location == "header":
                if key.lower() != "idempotency-key":
                    raise ValueError("Review new agent request headers before exposing them")
                properties["idempotency_key"] = {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 200,
                    "pattern": r"^[\x21-\x7e]+$",
                }
                if parameter.get("required"):
                    required.append("idempotency_key")
            elif location in {"path", "query"}:
                parameters[key] = parameter["schema"]
                locations[key] = location
                if parameter.get("required"):
                    required_parameters.append(key)
            else:
                raise ValueError("Unsupported agent parameter location")
        if parameters:
            properties["parameters"] = {
                "type": "object",
                "properties": parameters,
                "additionalProperties": False,
            }
            if required_parameters:
                properties["parameters"]["required"] = required_parameters
                required.append("parameters")
        request = operation.get("requestBody")
        if request:
            properties["body"] = request["content"]["application/json"]["schema"]
            if request.get("required"):
                required.append("body")
        input_schema = {"type": "object", "properties": properties, "additionalProperties": False}
        if required:
            input_schema["required"] = required
        read = method == "GET" or name in READ_POST
        success = next(
            value for code, value in operation["responses"].items() if code.startswith("2")
        )
        response_schema = success.get("content", {}).get("application/json", {}).get("schema")
        operations.append(
            {
                "name": name,
                "group": operation["tags"][0].lower().replace(" ", "-"),
                "summary": operation.get("summary", name),
                "method": method,
                "path": path,
                "effect": "read" if read else "write",
                "retry": "read"
                if read
                else "idempotency_key"
                if "idempotency_key" in properties
                else "inspect_before_retry",
                "download": name in DOWNLOADS,
                "sensitive_input": name in PRIVATE_INPUTS,
                "sensitive_result": name in PRIVATE_INPUTS
                or name in {"keys.create", "sign_in.create_invitation", "vault.get"},
                "authentication": "body"
                if name in PUBLIC_AUTH - PUBLIC_CONFIGURATION
                else "none"
                if name in PUBLIC_CONFIGURATION
                else "bearer",
                "parameter_locations": locations,
                "input_schema": _standalone(input_schema, definitions),
                "output_schema": _standalone(response_schema, definitions)
                if response_schema
                else None,
            }
        )
    return {
        "schema_version": 1,
        "api_version": "v1",
        "operations": sorted(operations, key=lambda x: x["name"]),
    }


def write_contract(openapi: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_contract(openapi), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
