"""Host-side deployment of one task, with explicit stages and local timings."""

from datetime import datetime
from enum import Enum
import json
from pathlib import Path
import shlex
import time

from retrolibx.core.android import android_path
from retrolibx.errors import RetroLibXError, ValidationError

from frontend_devices.adb import plan_device_upload
from .publication import AdbPublisher, plan_publication


class DeploymentStage(str, Enum):
    UPLOAD = "upload"
    COPY = "copy"
    PUBLISH = "publish"
    ALL = "all"


def plan_deployment(
    task: Path, remote: str, stage: DeploymentStage = DeploymentStage.ALL,
    skip_platform_config: bool = False,
) -> dict:
    """Local preview only; resource audits are not part of deployment."""
    publication = plan_publication(task, skip_platform_config)
    source = task / "apply.sh"
    target = android_path(remote)
    if target.suffix != ".sh":
        raise ValidationError("Deployment remote must be the complete .sh filename")
    # Generated task scripts are always UTF-8/LF. Refuse an altered task rather
    # than silently repairing or uploading it during execution.
    try:
        raw = source.read_bytes()
        raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValidationError(f"Cannot read task apply.sh: {exc}") from exc
    if not raw.startswith(b"#!/system/bin/sh\nset -e\n") or b"\r" in raw:
        raise ValidationError("Task apply.sh must use UTF-8/LF; regenerate the task")
    steps = [DeploymentStage.UPLOAD, DeploymentStage.COPY, DeploymentStage.PUBLISH] if stage == DeploymentStage.ALL else [stage]
    return {
        "task": str(task.resolve()), "remote": str(target), "applied": False, "steps": [step.value for step in steps],
        "upload": plan_device_upload(source, remote), "copy_command": "sh " + shlex.quote(str(target)),
        "publication": publication, "resource_audits": [],
    }


def deploy_task(
    client: AdbPublisher, task: Path, remote: str,
    stage: DeploymentStage = DeploymentStage.ALL, skip_platform_config: bool = False,
) -> dict:
    result = plan_deployment(task, remote, stage, skip_platform_config)
    result.update(serial=client.serial, applied=True, status="running", phases=[])
    task = task.resolve()
    receipt = task / "deployment-result.json"
    if receipt.exists():
        previous = json.loads(receipt.read_text(encoding="utf-8"))
        if previous.get("remote") != result["remote"] or previous.get("serial") != client.serial:
            raise ValidationError("Existing deployment record belongs to another device/remote; use a new task")
        result["phases"] = previous["phases"]

    def save() -> None:
        # One result and one short brief replace per-phase scripts and log files.
        (task / "deployment-result.json").write_bytes(
            (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        )
        rows = ["# Deployment result", "", "Status: " + result["status"],
                "Device: " + client.serial, "Requested stages: " + ", ".join(result["steps"]),
                "", "| Stage | Status | Seconds |", "|---|---|---:|"]
        rows += [f"| {phase['stage']} | {phase['status']} | {phase['seconds']:.2f} |" for phase in result["phases"]]
        rows += ["", "Resource audits and actual game launches were not performed."]
        (task / "deployment-brief.md").write_bytes(("\n".join(rows) + "\n").encode("utf-8"))

    for step in result["steps"]:
        phase = {"stage": step, "started_at": datetime.now().astimezone().isoformat(timespec="seconds")}
        started = time.monotonic()
        try:
            if step == DeploymentStage.UPLOAD:
                phase["result"] = client.upload(task / "apply.sh", remote)
            elif step == DeploymentStage.COPY:
                phase["output"] = client.read(result["copy_command"], timeout=3600).decode("utf-8", errors="replace")
            else:
                phase["result"] = client.publish(task, skip_platform_config)
            phase["status"] = "completed"
        except (RetroLibXError, OSError) as exc:
            phase.update(status="failed", error=str(exc))
            result["status"] = "failed"
            raise
        finally:
            phase.update(finished_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                         seconds=time.monotonic() - started)
            result["phases"].append(phase)
            save()
    result["status"] = "completed"
    save()
    return result
