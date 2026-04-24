#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import datetime as dt
import json
import platform
import re
import shutil
import socket
import subprocess
import sys
import textwrap
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
OPS_DIR = ROOT / "ops"
STATE_DIR = OPS_DIR / "state"
BACKUPS_DIR = ROOT / "backups"
MANIFEST_PATH = OPS_DIR / "stack.manifest.json"
DASHBOARD_CONFIG_PATH = OPS_DIR / "dashboard.config.json"
EXTENSIONS_PATH = OPS_DIR / "extensions.catalog.json"
VERSION_PATH = ROOT / "VERSION"
SELF_CHECK_PATH = ROOT / "SELF_CHECK.txt"
DASHBOARD_OUTPUT_PATH = ROOT / "dashboards" / "index.html"

REPORT_PATHS = {
    "doctor": STATE_DIR / "doctor-last.json",
    "status": STATE_DIR / "status-last.json",
    "smoke": STATE_DIR / "smoke-last.json",
    "validate": STATE_DIR / "validate-last.json",
}

SECRETS = {
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "OPENROUTER_API_KEY",
    "LITELLM_KEY",
    "WEBUI_SECRET_KEY",
    "POSTGRES_PASSWORD",
    "DATABASE_PASSWORD",
    "DATABASE_URL",
    "WEBUI_ADMIN_PASSWORD",
}

MODULE_ALIASES = {
    "hot": "core",
    "warm": "ui",
    "aider": "coding",
}

MODULE_TO_PROFILE = {
    "core": "hot",
    "ui": "warm",
    "coding": "aider",
}


class CommandError(RuntimeError):
    pass


def now_local() -> dt.datetime:
    return dt.datetime.now().astimezone()


def iso_now() -> str:
    return now_local().isoformat(timespec="seconds")


def ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_state_dir()
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return load_json(path)


def read_version() -> str:
    if not VERSION_PATH.exists():
        return "0.0.0"
    return VERSION_PATH.read_text(encoding="utf-8").strip()


def env_file_path() -> Path:
    return ROOT / ".env"


def template_env_path() -> Path:
    return ROOT / ".env.template"


def read_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()

    # On Windows, try to augment missing secrets from the Windows secret store
    try:
        if platform.system().lower().startswith("windows"):
            helper = ROOT / "scripts" / "get-secret.ps1"
            if helper.exists():
                for key in SECRETS:
                    val = data.get(key)
                    if not is_set(val):
                        try:
                            proc = subprocess.run([
                                "powershell",
                                "-NoProfile",
                                "-ExecutionPolicy",
                                "Bypass",
                                "-File",
                                str(helper),
                                "-Name",
                                key,
                            ], capture_output=True, text=True)
                            if proc.returncode == 0:
                                out = proc.stdout.strip()
                                if out:
                                    data[key] = out
                                    # export into process environment so docker subprocesses see it
                                    os.environ[key] = out
                        except Exception:
                            # ignore retrieval failures per-key
                            pass
    except Exception:
        pass

    return data


def mask_value(key: str, value: str) -> str:
    if not value:
        return ""
    if key in SECRETS:
        return "<set>"
    return value


def is_set(value: str | None) -> bool:
    if value is None:
        return False
    cleaned = value.strip()
    return bool(cleaned) and not cleaned.startswith("CHANGE_ME")


def run(
    args: list[str],
    *,
    check: bool = True,
    capture_output: bool = True,
    stdin: Any = None,
    stdout: Any = None,
) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {
        "args": args,
        "cwd": ROOT,
        "check": False,
        "text": True,
        "input": None,
        "stdin": stdin,
    }
    if capture_output:
        if stdout is not None:
            raise ValueError("stdout cannot be provided when capture_output=True")
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    else:
        if stdout is not None:
            kwargs["stdout"] = stdout

    result = subprocess.run(**kwargs)
    if check and result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else ""
        stdout_text = result.stdout.strip() if result.stdout else ""
        details = stderr or stdout_text or f"command failed with exit code {result.returncode}"
        raise CommandError(f"{' '.join(args)}: {details}")
    return result


def docker_compose_args(*extra: str) -> list[str]:
    return ["docker", "compose", *extra]


def docker_compose_config(profile: str) -> dict[str, Any]:
    result = run(docker_compose_args("--profile", profile, "config", "--format", "json"))
    return json.loads(result.stdout)


def docker_compose_profiles() -> list[str]:
    result = run(docker_compose_args("config", "--profiles"))
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def docker_compose_ps() -> list[dict[str, Any]]:
    result = run(docker_compose_args("ps", "--format", "json"))
    rows = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        rows.append(json.loads(stripped))
    return rows


def service_status_map() -> dict[str, dict[str, Any]]:
    return {row["Service"]: row for row in docker_compose_ps()}


def tool_exists(name: str) -> bool:
    return shutil.which(name) is not None


def http_check(url: str, *, headers: dict[str, str] | None = None, timeout: int = 5) -> tuple[bool, int | None, str]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            code = getattr(response, "status", response.getcode())
            return 200 <= code < 400, int(code), ""
    except urllib.error.HTTPError as exc:
        return False, exc.code, str(exc)
    except Exception as exc:  # noqa: BLE001
        return False, None, str(exc)


def port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def add_check(checks: list[dict[str, Any]], name: str, status: str, message: str, details: dict[str, Any] | None = None) -> None:
    checks.append(
        {
            "name": name,
            "status": status,
            "message": message,
            "details": details or {},
        }
    )


def overall_status(checks: list[dict[str, Any]]) -> str:
    statuses = {check["status"] for check in checks}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"


def print_checks(title: str, checks: list[dict[str, Any]]) -> None:
    print(title)
    for check in checks:
        print(f"- {check['status'].upper():4} {check['name']}: {check['message']}")


def latest_report(name: str) -> dict[str, Any] | None:
    return read_json_if_exists(REPORT_PATHS[name])


def normalize_module(name: str) -> str:
    lowered = name.lower()
    return MODULE_ALIASES.get(lowered, lowered)


def module_services(manifest: dict[str, Any], module: str) -> list[str]:
    return list(manifest["logical_modules"][module]["services"])


def current_runtime_status(manifest: dict[str, Any]) -> dict[str, Any]:
    services = manifest["services"]
    compose_rows = service_status_map()
    smoke_report = latest_report("smoke") or {}
    endpoint_checks = {
        item["service"]: item
        for item in smoke_report.get("endpoints", [])
        if item.get("service")
    }

    service_rows: list[dict[str, Any]] = []
    for service_id, service in services.items():
        if service["kind"] == "compose":
            compose_row = compose_rows.get(service_id)
            if compose_row:
                runtime = compose_row.get("State", "unknown")
                health = compose_row.get("Health") or "n/a"
            else:
                runtime = "stopped"
                health = "n/a"
        else:
            runtime = "running" if port_is_open(service["ports"][0]) else "stopped"
            health = "reachable" if runtime == "running" else "n/a"

        endpoint = endpoint_checks.get(service_id)
        service_rows.append(
            {
                "service": service_id,
                "module": service["module"],
                "kind": service["kind"],
                "runtime_state": runtime,
                "health": endpoint["status"] if endpoint else health,
                "status_text": compose_rows.get(service_id, {}).get("Status", runtime),
                "endpoint": service["endpoint"],
                "ports": service["ports"],
                "notes": service["notes"],
            }
        )

    module_rows: list[dict[str, Any]] = []
    for module_name, module in manifest["logical_modules"].items():
        rows = [row for row in service_rows if row["module"] == module_name and row["service"] != "ollama"]
        if module_name == "coding":
            ready = any(row["service"] == "litellm" and row["runtime_state"] == "running" for row in service_rows)
            status = "ready" if ready else "blocked"
            summary = "On-demand helper available through `aider.sh` / `aider.bat`." if ready else "Requires the core module to be running."
        else:
            unhealthy = [row for row in rows if row["runtime_state"] != "running"]
            status = "running" if rows and not unhealthy else ("idle" if module_name == "ui" and unhealthy else "degraded")
            if module_name == "ui" and all(row["runtime_state"] == "stopped" for row in rows):
                summary = "Optional UI module is not running."
            else:
                summary = f"{len(rows) - len(unhealthy)}/{len(rows)} services running."
        module_rows.append(
            {
                "module": module_name,
                "compose_profile": module["compose_profile"],
                "status": status,
                "summary": summary,
                "services": module["services"],
            }
        )

    return {
        "generated_at": iso_now(),
        "version": read_version(),
        "services": service_rows,
        "modules": module_rows,
    }


def save_report(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    write_json(REPORT_PATHS[name], payload)
    return payload


def collect_doctor() -> dict[str, Any]:
    manifest = load_json(MANIFEST_PATH)
    env = read_env(env_file_path())
    checks: list[dict[str, Any]] = []

    add_check(
        checks,
        "python",
        "pass" if sys.version_info >= (3, 11) else "fail",
        f"Python {platform.python_version()}",
    )
    add_check(
        checks,
        "docker-cli",
        "pass" if tool_exists("docker") else "fail",
        "Docker CLI available." if tool_exists("docker") else "Docker CLI not found.",
    )

    docker_ready = False
    try:
        run(["docker", "info"])
        docker_ready = True
        add_check(checks, "docker-daemon", "pass", "Docker daemon is reachable.")
    except CommandError as exc:
        add_check(checks, "docker-daemon", "fail", str(exc))

    if docker_ready:
        try:
            profiles = docker_compose_profiles()
            expected = sorted(manifest["compose_profiles"].keys())
            if sorted(profiles) == expected:
                add_check(checks, "compose-profiles", "pass", f"Compose profiles match: {', '.join(expected)}.")
            else:
                add_check(checks, "compose-profiles", "fail", f"Expected {expected}, got {profiles}.")
        except CommandError as exc:
            add_check(checks, "compose-profiles", "fail", str(exc))

        for profile in manifest["compose_profiles"].keys():
            try:
                docker_compose_config(profile)
                add_check(checks, f"compose-{profile}", "pass", f"`docker compose --profile {profile} config` passed.")
            except CommandError as exc:
                add_check(checks, f"compose-{profile}", "fail", str(exc))

    env_exists = env_file_path().exists()
    add_check(
        checks,
        ".env",
        "pass" if env_exists else "fail",
        ".env present." if env_exists else ".env missing. Run install.sh or install-windows.ps1 first.",
    )
    if env_exists:
        missing_required = [key for key in manifest["required_env_keys"] if not is_set(env.get(key))]
        placeholders = [key for key, value in env.items() if value.startswith("CHANGE_ME")]
        if missing_required:
            add_check(checks, "env-required", "fail", f"Missing required env keys: {', '.join(missing_required)}.")
        else:
            add_check(checks, "env-required", "pass", "Required local env keys are populated.")
        if placeholders:
            add_check(checks, "env-placeholders", "fail", f"Placeholder values left in .env: {', '.join(placeholders)}.")
        else:
            add_check(checks, "env-placeholders", "pass", "No placeholder env values detected.")

        provider_summary = {
            key: ("set" if is_set(env.get(key)) else "missing")
            for key in manifest["optional_env_keys"]
            if key.endswith("_API_KEY")
        }
        missing_cloud = [key for key, value in provider_summary.items() if value == "missing"]
        if missing_cloud:
            add_check(
                checks,
                "provider-keys",
                "warn",
                f"Some optional cloud provider keys are missing: {', '.join(missing_cloud)}.",
                provider_summary,
            )
        else:
            add_check(checks, "provider-keys", "pass", "All optional cloud provider keys are populated.", provider_summary)

    service_rows = service_status_map() if docker_ready else {}
    for service_id, service in manifest["services"].items():
        port = service["ports"][0] if service["ports"] else None
        if port is None:
            continue
        open_now = port_is_open(port)
        if service["kind"] == "compose":
            compose_row = service_rows.get(service_id)
            if compose_row:
                add_check(
                    checks,
                    f"port-{port}",
                    "pass" if open_now else "warn",
                    f"{service_id} publishes localhost:{port} and runtime state is {compose_row.get('Status', 'running')}.",
                )
            else:
                status = "warn" if open_now else "pass"
                message = (
                    f"Port {port} is listening but {service_id} is not running via Compose."
                    if open_now
                    else f"Port {port} is currently free while {service_id} is stopped."
                )
                add_check(checks, f"port-{port}", status, message)
        else:
            if open_now:
                add_check(checks, f"host-{service_id}", "pass", f"{service_id} endpoint port {port} is reachable.")
            else:
                add_check(checks, f"host-{service_id}", "warn", f"{service_id} host dependency is not reachable on port {port}.")

    ollama_cli = tool_exists("ollama")
    add_check(
        checks,
        "ollama-cli",
        "pass" if ollama_cli else "warn",
        "Ollama CLI available." if ollama_cli else "Ollama CLI not found; local model alias will stay unavailable.",
    )
    ok, code, error = http_check("http://localhost:11434/api/tags", timeout=3)
    add_check(
        checks,
        "ollama-endpoint",
        "pass" if ok else "warn",
        f"Ollama endpoint reachable (HTTP {code})." if ok else f"Ollama endpoint unavailable: {error or 'connection failed'}.",
    )

    payload = {
        "generated_at": iso_now(),
        "version": read_version(),
        "overall_status": overall_status(checks),
        "checks": checks,
        "env_presence": {key: ("set" if is_set(value) else "missing") for key, value in env.items() if key.endswith("_API_KEY")},
    }
    return save_report("doctor", payload)


def collect_smoke() -> dict[str, Any]:
    manifest = load_json(MANIFEST_PATH)
    env = read_env(env_file_path())
    checks: list[dict[str, Any]] = []
    endpoints: list[dict[str, Any]] = []

    if not env_file_path().exists():
        add_check(checks, ".env", "fail", ".env missing.")
        payload = {
            "generated_at": iso_now(),
            "version": read_version(),
            "overall_status": overall_status(checks),
            "checks": checks,
            "endpoints": endpoints,
        }
        return save_report("smoke", payload)

    for profile in manifest["compose_profiles"].keys():
        try:
            docker_compose_config(profile)
            add_check(checks, f"compose-{profile}", "pass", f"Profile `{profile}` resolves.")
        except CommandError as exc:
            add_check(checks, f"compose-{profile}", "fail", str(exc))

    runtime = service_status_map()
    if "postgres" in runtime:
        add_check(checks, "postgres-runtime", "pass", runtime["postgres"].get("Status", "running"))
    else:
        add_check(checks, "postgres-runtime", "fail", "postgres is not running.")

    litellm_headers = {}
    if is_set(env.get("LITELLM_KEY")):
        litellm_headers["Authorization"] = f"Bearer {env['LITELLM_KEY']}"

    for service_id in ("litellm", "open-webui", "ollama"):
        service = manifest["services"][service_id]
        should_check = service_id != "open-webui" or "open-webui" in runtime
        if not should_check:
            endpoints.append(
                {
                    "service": service_id,
                    "status": "skipped",
                    "message": "Open WebUI is not running.",
                    "checked_at": iso_now(),
                }
            )
            continue
        headers = litellm_headers if service_id == "litellm" else None
        ok, code, error = http_check(service["endpoint"], headers=headers, timeout=5)
        status = "pass" if ok else ("warn" if service_id == "ollama" else "fail")
        message = f"HTTP {code}" if ok else error or "connection failed"
        endpoints.append(
            {
                "service": service_id,
                "status": status,
                "message": message,
                "checked_at": iso_now(),
            }
        )
        add_check(checks, f"{service_id}-endpoint", status, f"{service['endpoint']} -> {message}")

    payload = {
        "generated_at": iso_now(),
        "version": read_version(),
        "overall_status": overall_status(checks),
        "checks": checks,
        "endpoints": endpoints,
    }
    return save_report("smoke", payload)


def collect_status() -> dict[str, Any]:
    manifest = load_json(MANIFEST_PATH)
    payload = current_runtime_status(manifest)
    return save_report("status", payload)


def markdown_links(text: str) -> list[str]:
    return re.findall(r"\[[^\]]+\]\(([^)]+)\)", text)


def resolve_doc_target(target: str, source: Path) -> Path | None:
    raw = target.strip()
    if raw.startswith(("http://", "https://", "mailto:")):
        return None
    raw = raw.split("#", 1)[0]
    if not raw:
        return None
    if raw.startswith("C:/") or raw.startswith("C:\\"):
        return Path(raw)
    return (source.parent / raw).resolve()


def collect_validate() -> dict[str, Any]:
    manifest = load_json(MANIFEST_PATH)
    dashboard = load_json(DASHBOARD_CONFIG_PATH)
    env = read_env(env_file_path())
    template_env = read_env(template_env_path())
    checks: list[dict[str, Any]] = []

    for rel_path in manifest["source_of_truth_files"]:
        full = ROOT / rel_path
        add_check(
            checks,
            f"file:{rel_path}",
            "pass" if full.exists() else "fail",
            f"{rel_path} exists." if full.exists() else f"{rel_path} is missing.",
        )

    profiles = docker_compose_profiles()
    expected_profiles = sorted(manifest["compose_profiles"].keys())
    add_check(
        checks,
        "compose-profile-set",
        "pass" if sorted(profiles) == expected_profiles else "fail",
        f"Manifest profiles {expected_profiles}; compose profiles {profiles}.",
    )

    service_union: set[str] = set()
    volume_union: set[str] = set()
    for profile in manifest["compose_profiles"].keys():
        config = docker_compose_config(profile)
        service_union.update(config.get("services", {}).keys())
        volume_union.update(config.get("volumes", {}).keys())
    manifest_services = {service_id for service_id, service in manifest["services"].items() if service["kind"] == "compose"}
    add_check(
        checks,
        "compose-service-set",
        "pass" if service_union == manifest_services else "fail",
        f"Manifest services {sorted(manifest_services)}; compose services {sorted(service_union)}.",
    )

    manifest_volumes = {
        volume
        for service in manifest["services"].values()
        if service["kind"] == "compose"
        for volume in service.get("volumes", [])
    }
    add_check(
        checks,
        "compose-volume-set",
        "pass" if volume_union == manifest_volumes else "warn",
        f"Manifest volumes {sorted(manifest_volumes)}; compose volumes {sorted(volume_union)}.",
    )

    missing_template = [key for key in manifest["required_env_keys"] if key not in template_env]
    add_check(
        checks,
        "env-template-required-keys",
        "pass" if not missing_template else "fail",
        "All required env keys exist in .env.template." if not missing_template else f".env.template is missing: {', '.join(missing_template)}.",
    )

    missing_env = [key for key in manifest["required_env_keys"] if key not in env]
    add_check(
        checks,
        "env-current-required-keys",
        "pass" if not missing_env else "fail",
        "All required env keys exist in .env." if not missing_env else f".env is missing: {', '.join(missing_env)}.",
    )

    for module_name, module in manifest["logical_modules"].items():
        profile = module["compose_profile"]
        status = "pass" if profile in manifest["compose_profiles"] else "fail"
        add_check(checks, f"module:{module_name}", status, f"{module_name} maps to compose profile `{profile}`.")

    docs_to_scan = [
        ROOT / "README.md",
        ROOT / "WINDOWS11_GUIDE.md",
        ROOT / "docs" / "index.md",
        ROOT / "docs" / "ARCHITECTURE.md",
        ROOT / "docs" / "OPERATIONS.md",
        ROOT / "docs" / "TROUBLESHOOTING.md",
        ROOT / "docs" / "KNOWN_LIMITATIONS.md",
        ROOT / "docs" / "EXTENSIBILITY.md",
        ROOT / "docs" / "RELEASE.md",
    ]
    broken_links: list[str] = []
    for doc in docs_to_scan:
        if not doc.exists():
            broken_links.append(str(doc.relative_to(ROOT)))
            continue
        for target in markdown_links(read_text(doc)):
            resolved = resolve_doc_target(target, doc)
            if resolved is None:
                continue
            if not resolved.exists():
                broken_links.append(f"{doc.relative_to(ROOT)} -> {target}")
    add_check(
        checks,
        "docs-links",
        "pass" if not broken_links else "fail",
        "All local markdown links resolve." if not broken_links else f"Broken links: {', '.join(broken_links)}.",
    )

    generated_outputs = {str((ROOT / path).resolve()) for path in dashboard["generated_outputs"]}
    dashboard_dir = ROOT / "dashboards"
    unexpected_dashboards = sorted(
        str(path.relative_to(ROOT))
        for path in dashboard_dir.glob("*.html")
        if str(path.resolve()) not in generated_outputs
    )
    add_check(
        checks,
        "dashboard-files",
        "pass" if not unexpected_dashboards else "warn",
        "Only configured dashboard outputs are present." if not unexpected_dashboards else f"Unexpected dashboard files: {', '.join(unexpected_dashboards)}.",
    )

    missing_dashboard_links = [
        item["path"]
        for item in dashboard["docs_links"]
        if not (ROOT / item["path"]).exists()
    ]
    add_check(
        checks,
        "dashboard-doc-links",
        "pass" if not missing_dashboard_links else "fail",
        "Dashboard documentation links resolve." if not missing_dashboard_links else f"Dashboard docs missing: {', '.join(missing_dashboard_links)}.",
    )

    payload = {
        "generated_at": iso_now(),
        "version": read_version(),
        "overall_status": overall_status(checks),
        "checks": checks,
    }
    return save_report("validate", payload)


def print_status_table(status_report: dict[str, Any]) -> None:
    print("Modules")
    for module in status_report["modules"]:
        print(f"- {module['module']}: {module['status']} ({module['summary']})")
    print("")
    print("Services")
    for row in status_report["services"]:
        print(
            f"- {row['service']}: state={row['runtime_state']}, health={row['health']}, "
            f"ports={','.join(str(port) for port in row['ports'])}"
        )


def css_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "unknown"


def render_dashboard() -> Path:
    manifest = load_json(MANIFEST_PATH)
    dashboard = load_json(DASHBOARD_CONFIG_PATH)
    doctor = latest_report("doctor")
    smoke = latest_report("smoke")
    status_report = latest_report("status")
    validate = latest_report("validate")
    if status_report is None:
        status_report = current_runtime_status(manifest)

    smoke_map = {
        item["service"]: item
        for item in (smoke or {}).get("endpoints", [])
        if item.get("service")
    }

    service_cards = []
    for service in status_report["services"]:
        endpoint_status = smoke_map.get(service["service"])
        badge = endpoint_status["status"] if endpoint_status else service["health"]
        endpoint_message = endpoint_status["message"] if endpoint_status else "No endpoint check recorded yet."
        service_cards.append(
            f"""
            <article class="service-card">
              <div class="service-head">
                <div>
                  <h3>{service['service']}</h3>
                  <p>{service['notes']}</p>
                </div>
                <span class="badge badge-{css_slug(badge)}">{badge}</span>
              </div>
              <dl>
                <div><dt>Module</dt><dd>{service['module']}</dd></div>
                <div><dt>Runtime</dt><dd>{service['status_text']}</dd></div>
                <div><dt>Ports</dt><dd>{', '.join(str(port) for port in service['ports'])}</dd></div>
                <div><dt>Endpoint</dt><dd>{service['endpoint'] or 'Container health only'}</dd></div>
              </dl>
              <div class="service-foot">{endpoint_message}</div>
            </article>
            """
        )

    docs_links = "\n".join(
        f'<li><a href="../{item["path"]}">{item["label"]}</a></li>'
        for item in dashboard["docs_links"]
    )
    action_buttons = "\n".join(
        f'<button type="button" data-copy="{item["command"]}">{item["label"]}</button>'
        for item in dashboard["quick_actions"]
    )
    module_rows = "\n".join(
        f"<tr><td>{module['module']}</td><td>{module['compose_profile']}</td><td>{module['status']}</td><td>{module['summary']}</td></tr>"
        for module in status_report["modules"]
    )

    empty_state = ""
    if not any(latest_report(name) for name in ("doctor", "smoke", "validate")):
        empty_state = (
            '<div class="empty-state"><strong>No generated checks yet.</strong> '
            'Run <code>.\\stack.ps1 refresh</code> or <code>./stack.sh refresh</code> to embed a fresh snapshot.</div>'
        )

    def report_stamp(report: dict[str, Any] | None) -> str:
        return report["generated_at"] if report else "not generated"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{dashboard['title']}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0b1220;
      --bg-2: #101a2f;
      --panel: rgba(11, 18, 32, 0.84);
      --line: rgba(148, 163, 184, 0.18);
      --text: #edf2ff;
      --muted: #99a9c3;
      --accent: #f97316;
      --accent-soft: rgba(249, 115, 22, 0.14);
      --ok: #22c55e;
      --warn: #f59e0b;
      --fail: #ef4444;
      --info: #38bdf8;
      --shadow: 0 24px 80px rgba(0, 0, 0, 0.32);
    }}

    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(249, 115, 22, 0.18), transparent 28%),
        radial-gradient(circle at top right, rgba(56, 189, 248, 0.14), transparent 22%),
        linear-gradient(180deg, var(--bg) 0%, var(--bg-2) 100%);
      color: var(--text);
      min-height: 100vh;
    }}

    .wrap {{
      width: min(1240px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 44px;
    }}

    .hero, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 26px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(14px);
    }}

    .hero {{
      padding: 28px;
      margin-bottom: 18px;
    }}

    .eyebrow {{
      display: inline-flex;
      gap: 8px;
      align-items: center;
      padding: 6px 12px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: #fed7aa;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 12px;
    }}

    h1, h2, h3, p {{ margin: 0; }}

    h1 {{
      font-size: clamp(34px, 5vw, 58px);
      line-height: 0.98;
      max-width: 880px;
      margin-top: 18px;
    }}

    .hero-copy {{
      margin-top: 16px;
      color: var(--muted);
      max-width: 820px;
      line-height: 1.6;
    }}

    .meta-grid, .grid, .service-grid {{
      display: grid;
      gap: 16px;
    }}

    .meta-grid {{
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      margin-top: 22px;
    }}

    .meta-card {{
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px;
      background: rgba(9, 14, 25, 0.55);
    }}

    .meta-card strong {{
      display: block;
      font-size: 22px;
      margin-bottom: 6px;
    }}

    .button-row {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 20px;
    }}

    button {{
      font: inherit;
      border: 1px solid rgba(249, 115, 22, 0.34);
      background: rgba(249, 115, 22, 0.12);
      color: #ffedd5;
      border-radius: 12px;
      padding: 10px 14px;
      cursor: pointer;
    }}

    .status-strip {{
      margin-top: 18px;
      padding: 14px 16px;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(9, 14, 25, 0.55);
      color: var(--muted);
    }}

    .grid {{
      grid-template-columns: 1.8fr 1fr;
      align-items: start;
    }}

    .panel {{
      padding: 22px;
    }}

    .service-grid {{
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      margin-top: 18px;
    }}

    .service-card {{
      border: 1px solid var(--line);
      border-radius: 20px;
      padding: 16px;
      background: rgba(9, 14, 25, 0.54);
    }}

    .service-head {{
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }}

    .service-head p {{
      color: var(--muted);
      margin-top: 6px;
      line-height: 1.5;
    }}

    .badge {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 12px;
      border: 1px solid var(--line);
      text-transform: uppercase;
      letter-spacing: 0.04em;
      white-space: nowrap;
    }}

    .badge-pass, .badge-running, .badge-healthy, .badge-reachable {{
      color: #bbf7d0;
      background: rgba(34, 197, 94, 0.14);
    }}

    .badge-warn, .badge-idle, .badge-skipped, .badge-n-a {{
      color: #fde68a;
      background: rgba(245, 158, 11, 0.14);
    }}

    .badge-fail, .badge-blocked {{
      color: #fecaca;
      background: rgba(239, 68, 68, 0.14);
    }}

    .badge-ready, .badge-degraded {{
      color: #bfdbfe;
      background: rgba(56, 189, 248, 0.14);
    }}

    dl {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px 16px;
      margin: 0;
    }}

    dt {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #fbbf24;
    }}

    dd {{
      margin: 6px 0 0;
      color: var(--text);
      line-height: 1.5;
    }}

    .service-foot {{
      margin-top: 14px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      line-height: 1.5;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 14px;
    }}

    th, td {{
      padding: 10px 0;
      text-align: left;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
      color: var(--muted);
    }}

    th {{
      color: var(--text);
      font-weight: 600;
    }}

    .docs-list, .facts {{
      margin: 16px 0 0;
      padding-left: 18px;
      color: var(--muted);
      line-height: 1.7;
    }}

    .facts strong {{
      color: var(--text);
    }}

    code {{
      font-family: Consolas, "Cascadia Code", monospace;
      color: #fde68a;
    }}

    a {{
      color: #fdba74;
    }}

    .empty-state {{
      margin-top: 16px;
      padding: 16px;
      border-radius: 16px;
      border: 1px dashed rgba(148, 163, 184, 0.28);
      color: var(--muted);
    }}

    @media (max-width: 960px) {{
      .grid {{
        grid-template-columns: 1fr;
      }}
      dl {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <span class="eyebrow">AI Stack {read_version()} · Honest Dashboard 2.0</span>
      <h1>{dashboard['title']}</h1>
      <p class="hero-copy">{dashboard['tagline']}</p>
      <div class="meta-grid">
        <div class="meta-card">
          <strong>{read_version()}</strong>
          <span>Repo version from <code>VERSION</code>.</span>
        </div>
        <div class="meta-card">
          <strong>{report_stamp(status_report)}</strong>
          <span>Latest runtime snapshot.</span>
        </div>
        <div class="meta-card">
          <strong>{report_stamp(validate)}</strong>
          <span>Latest consistency validation.</span>
        </div>
        <div class="meta-card">
          <strong>{report_stamp(smoke)}</strong>
          <span>Latest endpoint smoke pass.</span>
        </div>
      </div>
      <div class="button-row">
        {action_buttons}
      </div>
      <div class="status-strip" id="copyStatus">
        Generated at {iso_now()}. This file is a snapshot, not a live control plane.
      </div>
      {empty_state}
    </section>

    <div class="grid">
      <div class="panel">
        <h2>Real Services</h2>
        <p class="hero-copy">Only services that actually exist in the current architecture appear here.</p>
        <div class="service-grid">
          {''.join(service_cards)}
        </div>
      </div>

      <div class="panel">
        <h2>Module Status</h2>
        <table>
          <thead>
            <tr>
              <th>Module</th>
              <th>Compose</th>
              <th>Status</th>
              <th>Summary</th>
            </tr>
          </thead>
          <tbody>
            {module_rows}
          </tbody>
        </table>

        <h2 style="margin-top: 22px;">Check Timestamps</h2>
        <ul class="facts">
          <li><strong>Doctor:</strong> {report_stamp(doctor)}</li>
          <li><strong>Smoke:</strong> {report_stamp(smoke)}</li>
          <li><strong>Validate:</strong> {report_stamp(validate)}</li>
        </ul>

        <h2 style="margin-top: 22px;">Docs</h2>
        <ul class="docs-list">
          {docs_links}
        </ul>

        <h2 style="margin-top: 22px;">Architecture Facts</h2>
        <ul class="facts">
          <li><strong>Compose profiles:</strong> {', '.join(manifest['compose_profiles'].keys())}</li>
          <li><strong>Logical modules:</strong> {', '.join(manifest['logical_modules'].keys())}</li>
          <li><strong>Host dependency:</strong> Ollama on <code>localhost:11434</code></li>
          <li><strong>Self-check artifact:</strong> <code>{manifest['project']['self_check_output']}</code></li>
        </ul>
      </div>
    </div>
  </div>

  <script>
    const status = document.getElementById("copyStatus");
    document.querySelectorAll("[data-copy]").forEach((button) => {{
      button.addEventListener("click", async () => {{
        const value = button.getAttribute("data-copy");
        try {{
          await navigator.clipboard.writeText(value);
          status.textContent = "Copied: " + value;
        }} catch (error) {{
          status.textContent = "Clipboard unavailable. Copy manually: " + value;
        }}
      }});
    }});
  </script>
</body>
</html>
"""
    DASHBOARD_OUTPUT_PATH.write_text(html, encoding="utf-8")
    return DASHBOARD_OUTPUT_PATH


def write_self_check() -> Path:
    manifest = load_json(MANIFEST_PATH)
    doctor = latest_report("doctor")
    status_report = latest_report("status")
    smoke = latest_report("smoke")
    validate = latest_report("validate")

    lines = [
        f"SELF-CHECK REPORT - {manifest['project']['name']}",
        f"Date: {now_local().date().isoformat()}",
        f"Generated at: {iso_now()}",
        f"Project path: {ROOT}",
        f"Version: {read_version()}",
        "",
        "1. Doctor",
        f"- Overall: {(doctor or {}).get('overall_status', 'not generated')}",
    ]
    for check in (doctor or {}).get("checks", []):
        lines.append(f"- {check['status'].upper()}: {check['name']} - {check['message']}")

    lines.extend(
        [
            "",
            "2. Runtime status",
            f"- Snapshot: {(status_report or {}).get('generated_at', 'not generated')}",
        ]
    )
    for row in (status_report or {}).get("services", []):
        lines.append(
            f"- {row['service']}: state={row['runtime_state']}, health={row['health']}, ports={','.join(str(port) for port in row['ports'])}"
        )

    lines.extend(
        [
            "",
            "3. Smoke",
            f"- Overall: {(smoke or {}).get('overall_status', 'not generated')}",
        ]
    )
    for check in (smoke or {}).get("checks", []):
        lines.append(f"- {check['status'].upper()}: {check['name']} - {check['message']}")

    lines.extend(
        [
            "",
            "4. Consistency validation",
            f"- Overall: {(validate or {}).get('overall_status', 'not generated')}",
        ]
    )
    for check in (validate or {}).get("checks", []):
        lines.append(f"- {check['status'].upper()}: {check['name']} - {check['message']}")

    lines.extend(
        [
            "",
            "5. Known limitations",
        ]
    )
    for item in manifest["limitations"]:
        lines.append(f"- {item}")

    SELF_CHECK_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return SELF_CHECK_PATH


def backup_volume_to_tar(volume_name: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["docker", "run", "--rm", "-v", f"{volume_name}:/data", "alpine:3.20", "tar", "-czf", "-", "-C", "/data", "."]
    with destination.open("wb") as handle:
        result = subprocess.run(cmd, cwd=ROOT, check=False, stdout=handle, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise CommandError(result.stderr.decode("utf-8", errors="ignore"))


def restore_tar_to_volume(source: Path, volume_name: str) -> None:
    run(["docker", "volume", "rm", "-f", volume_name], capture_output=True, check=False)
    run(["docker", "volume", "create", volume_name], capture_output=True)
    cmd = [
        "docker",
        "run",
        "--rm",
        "-i",
        "-v",
        f"{volume_name}:/data",
        "alpine:3.20",
        "sh",
        "-lc",
        "rm -rf /data/* /data/.[!.]* /data/..?* 2>/dev/null || true; tar -xzf - -C /data",
    ]
    with source.open("rb") as handle:
        result = subprocess.run(cmd, cwd=ROOT, check=False, stdin=handle, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise CommandError(result.stderr.decode("utf-8", errors="ignore"))


def backup_snapshot(label: str | None = None) -> Path:
    manifest = load_json(MANIFEST_PATH)
    env = read_env(env_file_path())
    timestamp = now_local().strftime("%Y%m%d-%H%M%S")
    slug = label or timestamp
    target = BACKUPS_DIR / slug
    target.mkdir(parents=True, exist_ok=True)

    started_postgres = False
    runtime = service_status_map()
    if "postgres" not in runtime:
        run(docker_compose_args("--profile", "hot", "up", "-d", "postgres"), capture_output=True)
        started_postgres = True

    files_to_copy = [
        ".env",
        "docker-compose.yml",
        "litellm-config.yaml",
        "continue.config.yaml",
        "VERSION",
        "ops/stack.manifest.json",
        "ops/dashboard.config.json",
        "ops/extensions.catalog.json",
    ]
    for rel_path in files_to_copy:
        source = ROOT / rel_path
        if source.exists():
            dest = target / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)

    with (target / "postgres.dump").open("wb") as handle:
        dump_cmd = [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "sh",
            "-lc",
            'export PGPASSWORD="$POSTGRES_PASSWORD"; pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc',
        ]
        result = subprocess.run(dump_cmd, cwd=ROOT, check=False, stdout=handle, stderr=subprocess.PIPE)
        if result.returncode != 0:
            raise CommandError(result.stderr.decode("utf-8", errors="ignore"))

    open_webui_volume = docker_compose_config("warm").get("volumes", {}).get("open_webui_data", {}).get("name")
    if open_webui_volume:
        backup_volume_to_tar(open_webui_volume, target / "open-webui-data.tgz")

    metadata = {
        "created_at": iso_now(),
        "version": read_version(),
        "label": slug,
        "started_postgres_for_backup": started_postgres,
        "logical_modules": list(manifest["logical_modules"].keys()),
        "cloud_keys": {key: ("set" if is_set(value) else "missing") for key, value in env.items() if key.endswith("_API_KEY")},
    }
    (target / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    if started_postgres:
        run(docker_compose_args("stop", "postgres"), capture_output=True, check=False)

    return target


def restore_snapshot(snapshot_path: Path, *, restore_env: bool) -> None:
    if not snapshot_path.exists():
        raise CommandError(f"Backup snapshot not found: {snapshot_path}")

    run(docker_compose_args("stop", "open-webui"), capture_output=True, check=False)
    run(docker_compose_args("--profile", "hot", "up", "-d", "postgres"), capture_output=True)

    dump_path = snapshot_path / "postgres.dump"
    if dump_path.exists():
        with dump_path.open("rb") as handle:
            cmd = [
                "docker",
                "compose",
                "exec",
                "-T",
                "postgres",
                "sh",
                "-lc",
                'export PGPASSWORD="$POSTGRES_PASSWORD"; pg_restore --clean --if-exists -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
            ]
            result = subprocess.run(cmd, cwd=ROOT, check=False, stdin=handle, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode != 0:
                raise CommandError(result.stderr.decode("utf-8", errors="ignore"))

    volume_name = docker_compose_config("warm").get("volumes", {}).get("open_webui_data", {}).get("name")
    open_webui_backup = snapshot_path / "open-webui-data.tgz"
    if volume_name and open_webui_backup.exists():
        restore_tar_to_volume(open_webui_backup, volume_name)

    if restore_env:
        backup_env = snapshot_path / ".env"
        if backup_env.exists():
            shutil.copy2(backup_env, env_file_path())


def cmd_start(args: argparse.Namespace) -> int:
    manifest = load_json(MANIFEST_PATH)
    module = normalize_module(args.target)
    if module not in manifest["logical_modules"]:
        raise CommandError(f"Unknown start target: {args.target}")
    profile = manifest["logical_modules"][module]["compose_profile"]
    if module == "coding":
        run(docker_compose_args("--profile", "hot", "up", "-d"), capture_output=False)
        print("Coding module is on-demand. Core runtime started; use `aider.sh` or `aider.bat` to run Aider.")
        return 0
    run(docker_compose_args("--profile", profile, "up", "-d"), capture_output=False)
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    module = normalize_module(args.target)
    if module == "all":
        run(docker_compose_args("down"), capture_output=False)
        return 0
    if module == "core":
        run(docker_compose_args("stop", "litellm", "postgres"), capture_output=False)
        return 0
    if module == "ui":
        run(docker_compose_args("stop", "open-webui"), capture_output=False)
        return 0
    if module == "coding":
        run(docker_compose_args("stop", "aider"), capture_output=False, check=False)
        return 0
    raise CommandError(f"Unknown stop target: {args.target}")


def cmd_restart(args: argparse.Namespace) -> int:
    target = normalize_module(args.target)
    cmd_stop(argparse.Namespace(target=target))
    return cmd_start(argparse.Namespace(target=target))


def cmd_doctor(_: argparse.Namespace) -> int:
    report = collect_doctor()
    print_checks("Environment Doctor", report["checks"])
    return 1 if report["overall_status"] == "fail" else 0


def cmd_smoke(_: argparse.Namespace) -> int:
    report = collect_smoke()
    print_checks("Smoke Checks", report["checks"])
    return 1 if report["overall_status"] == "fail" else 0


def cmd_status(args: argparse.Namespace) -> int:
    report = collect_status()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_status_table(report)
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    run(docker_compose_args("logs", "-f", args.service), capture_output=False)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    if args.write_artifacts:
        render_dashboard()
    report = collect_validate()
    print_checks("Validation", report["checks"])
    if args.write_artifacts:
        write_self_check()
        print("")
        print(f"Generated {DASHBOARD_OUTPUT_PATH} and {SELF_CHECK_PATH}.")
    return 1 if report["overall_status"] == "fail" else 0


def cmd_backup(args: argparse.Namespace) -> int:
    target = backup_snapshot(args.label)
    print(f"Backup written to {target}")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    restore_snapshot(Path(args.snapshot).resolve(), restore_env=args.restore_env)
    print(f"Restore finished from {Path(args.snapshot).resolve()}")
    return 0


def cmd_render(_: argparse.Namespace) -> int:
    path = render_dashboard()
    print(f"Dashboard generated at {path}")
    return 0


def cmd_refresh(_: argparse.Namespace) -> int:
    doctor = collect_doctor()
    status_report = collect_status()
    smoke = collect_smoke()
    render_dashboard()
    validate = collect_validate()
    write_self_check()

    print_checks("Doctor", doctor["checks"])
    print("")
    print_status_table(status_report)
    print("")
    print_checks("Smoke", smoke["checks"])
    print("")
    print_checks("Validate", validate["checks"])
    print("")
    print(f"Artifacts regenerated: {DASHBOARD_OUTPUT_PATH} and {SELF_CHECK_PATH}")

    overall = overall_status(
        doctor["checks"] + smoke["checks"] + validate["checks"]
    )
    return 1 if overall == "fail" else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Truth-driven operations CLI for the local AI Stack.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Common flows:
              python ops/ai_stack.py start core
              python ops/ai_stack.py doctor
              python ops/ai_stack.py smoke
              python ops/ai_stack.py validate --write-artifacts
              python ops/ai_stack.py backup
            """
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Start a logical module.")
    start.add_argument("target", nargs="?", default="core")
    start.set_defaults(func=cmd_start)

    stop = subparsers.add_parser("stop", help="Stop a logical module or all services.")
    stop.add_argument("target", nargs="?", default="all")
    stop.set_defaults(func=cmd_stop)

    restart = subparsers.add_parser("restart", help="Restart a logical module or all services.")
    restart.add_argument("target", nargs="?", default="core")
    restart.set_defaults(func=cmd_restart)

    doctor = subparsers.add_parser("doctor", help="Diagnose the local environment.")
    doctor.set_defaults(func=cmd_doctor)

    smoke = subparsers.add_parser("smoke", help="Run runtime smoke checks.")
    smoke.set_defaults(func=cmd_smoke)

    status = subparsers.add_parser("status", help="Show current runtime status.")
    status.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    status.set_defaults(func=cmd_status)

    logs = subparsers.add_parser("logs", help="Tail logs for a compose service.")
    logs.add_argument("service")
    logs.set_defaults(func=cmd_logs)

    validate = subparsers.add_parser("validate", help="Check docs, files, compose, and env consistency.")
    validate.add_argument("--write-artifacts", action="store_true", help="Also regenerate the dashboard and self-check artifacts.")
    validate.set_defaults(func=cmd_validate)

    backup = subparsers.add_parser("backup", help="Create a backup snapshot.")
    backup.add_argument("--label", help="Optional human-readable backup folder label.")
    backup.set_defaults(func=cmd_backup)

    restore = subparsers.add_parser("restore", help="Restore a backup snapshot.")
    restore.add_argument("snapshot", help="Path to the backup folder.")
    restore.add_argument("--restore-env", action="store_true", help="Also restore the backed-up .env file.")
    restore.set_defaults(func=cmd_restore)

    render = subparsers.add_parser("render-dashboard", help="Regenerate the static dashboard from the latest reports.")
    render.set_defaults(func=cmd_render)

    refresh = subparsers.add_parser("refresh", help="Run doctor, status, smoke, validate, and regenerate artifacts.")
    refresh.set_defaults(func=cmd_refresh)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except CommandError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
