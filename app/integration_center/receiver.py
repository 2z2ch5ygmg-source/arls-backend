from __future__ import annotations

from typing import Any, Callable

from .feature_flags import SOC_INTEGRATION_ENABLED


class SocEventReceiver:
    def __init__(
        self,
        *,
        idempotency_store,
        feature_flags,
        hr_domain_applier,
        audit_log,
        tenant_resolver: Callable[[str], dict[str, Any] | None],
    ):
        self.idempotency_store = idempotency_store
        self.feature_flags = feature_flags
        self.hr_domain_applier = hr_domain_applier
        self.audit_log = audit_log
        self.tenant_resolver = tenant_resolver

    def _run_hr_apply_with_savepoint(self, *, tenant, payload, event_type: str) -> tuple[dict[str, Any], str | None]:
        """
        Keep ingest transaction alive even if domain SQL fails.
        We isolate apply() in a SAVEPOINT and roll back only that scope on error.
        """
        conn = getattr(self.idempotency_store, "conn", None)
        if conn is None:
            try:
                return self.hr_domain_applier.apply(
                    tenant=tenant,
                    payload=payload,
                    event_type=event_type,
                ), None
            except Exception as exc:  # pragma: no cover - defensive
                return {}, str(exc)

        with conn.cursor() as cur:
            cur.execute("SAVEPOINT soc_event_apply")
        try:
            applied = self.hr_domain_applier.apply(
                tenant=tenant,
                payload=payload,
                event_type=event_type,
            )
            with conn.cursor() as cur:
                cur.execute("RELEASE SAVEPOINT soc_event_apply")
            return applied, None
        except Exception as exc:
            with conn.cursor() as cur:
                cur.execute("ROLLBACK TO SAVEPOINT soc_event_apply")
                cur.execute("RELEASE SAVEPOINT soc_event_apply")
            return {}, str(exc)

    def receive(
        self,
        *,
        payload,
        event_uid: str,
        event_type: str,
        tenant_code: str,
        signature_valid: bool,
    ) -> dict[str, Any]:
        duplicate, existing_row = self.idempotency_store.ingest_received(
            event_uid=event_uid,
            tenant_code=tenant_code,
            event_type=event_type,
            payload=payload.model_dump(),
            signature_valid=signature_valid,
        )
        if duplicate:
            return {"duplicate": True, "row": existing_row, "tenant": None}

        tenant = self.tenant_resolver(tenant_code)
        status_text = "processed"
        error_text = None
        applied_changes: dict[str, Any] = {}

        if not tenant or not bool(tenant.get("is_active", True)):
            status_text = "failed"
            error_text = "tenant not found or inactive"
        elif not self.feature_flags.is_enabled(tenant["id"], SOC_INTEGRATION_ENABLED):
            status_text = "skipped"
            error_text = "soc integration disabled by feature flag"
        else:
            applied_changes, apply_error = self._run_hr_apply_with_savepoint(
                tenant=tenant,
                payload=payload,
                event_type=event_type,
            )
            if apply_error:
                status_text = "failed"
                error_text = apply_error

        row = self.idempotency_store.finalize(
            event_uid=event_uid,
            tenant_id=tenant["id"] if tenant else None,
            tenant_code=tenant_code,
            status_text=status_text,
            error_text=error_text,
            applied_changes=applied_changes,
        )

        if tenant:
            self.audit_log.write(
                tenant_id=tenant["id"],
                action_type="soc_event_ingested" if status_text == "processed" else "soc_event_failed",
                source="soc",
                actor_user_id=None,
                actor_role="soc_system",
                target_type="soc_event",
                target_id=event_uid,
                detail={
                    "event_type": event_type,
                    "status": status_text,
                    "error": error_text,
                    "applied_changes": applied_changes,
                },
            )

        return {
            "duplicate": False,
            "row": row,
            "tenant": tenant,
            "status_text": status_text,
            "error_text": error_text,
            "applied_changes": applied_changes,
        }
