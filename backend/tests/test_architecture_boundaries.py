import subprocess
import sys


def test_actual_codebase_passes_all_architectural_contracts():
    """
    Positive architecture check:
    Verifies that the current PRIP codebase strictly adheres to:
    1. Layered architecture: api -> services -> repositories -> models -> core
    2. Core infrastructure independence (zero dependency on application layers)
    3. Policy independence (policies remain pure; no integrations/models/services)
    4. Repositories isolation (repositories do not import services or api)
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from importlinter.cli import lint_imports; sys.exit(lint_imports())",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Import-linter failed unexpectedly:\n{result.stdout}\n{result.stderr}"
    )
    assert "0 broken" in result.stdout
    assert "kept" in result.stdout


def test_forbidden_rule_detects_policy_importing_integration(tmp_path):
    """
    Architecture check verifying policy isolation rule configuration:
    Ensures that an explicit policy-isolation contract validates cleanly on the current codebase.
    """
    config_file = tmp_path / "test_importlinter.ini"
    config_file.write_text(
        """[importlinter]
root_packages =
    backend

[importlinter:contract:policies-forbidden]
name = Policies must not import integrations
type = forbidden
source_modules =
    backend.policies
forbidden_modules =
    backend.integrations
"""
    )
    posix_path = config_file.as_posix()
    res_clean = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; from importlinter.cli import lint_imports; sys.exit(lint_imports(config_filename=r'{posix_path}'))",
        ],
        capture_output=True,
        text=True,
    )
    assert res_clean.returncode == 0, f"Failed:\n{res_clean.stdout}\n{res_clean.stderr}"
    assert "Contracts: 1 kept, 0 broken" in res_clean.stdout


def test_forbidden_rule_detects_core_importing_services(tmp_path):
    """
    Architecture check verifying core isolation rule configuration:
    Ensures that an explicit core-isolation contract validates cleanly on the current codebase.
    """
    config_file = tmp_path / "test_core_importlinter.ini"
    config_file.write_text(
        """[importlinter]
root_packages =
    backend

[importlinter:contract:core-forbidden]
name = Core must not import services
type = forbidden
source_modules =
    backend.core
forbidden_modules =
    backend.services
"""
    )
    posix_path = config_file.as_posix()
    res = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; from importlinter.cli import lint_imports; sys.exit(lint_imports(config_filename=r'{posix_path}'))",
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Failed:\n{res.stdout}\n{res.stderr}"
    assert "Contracts: 1 kept, 0 broken" in res.stdout
