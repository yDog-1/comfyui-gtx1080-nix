"""Lifecycle tests with fake installers; no GPU, network, or user data required."""

import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPTS = Path(__file__).parent


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="comfyui-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = self.root / "data with spaces"
        self.runtime = self.root / "runtime"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        (self.runtime / "app").mkdir(parents=True)
        (self.runtime / "app" / "main.py").touch()
        (self.runtime / "check-gpu.py").touch()
        (self.runtime / "constraints.txt").write_text("torch==2.10.0+cu126\n")
        (self.runtime / "requirements.lock").write_text("locked\n")
        (self.runtime / "uv/bin").mkdir(parents=True)
        (self.runtime / "uv/bin/uv").symlink_to(self.bin / "uv")
        self.log = self.root / "events"
        self.environment = os.environ | {
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "data_dir": str(self.data),
            "current": str(self.data / "current"),
            "managed_runtime": str(self.runtime),
            "environment_id": "test-id",
            "CUDA_CACHE_PATH": str(self.data / ".cache/cuda"),
            "HF_HOME": str(self.data / ".cache/huggingface"),
            "TORCH_HOME": str(self.data / ".cache/torch"),
            "EVENT_LOG": str(self.log),
        }
        self.executable("nix-store", '''
while [[ $# -gt 0 ]]; do
  if [[ "$1" == --add-root ]]; then
    ln -s "$managed_runtime" "$2"
    exit 0
  fi
  shift
done
exit 1
''')
        self.executable("uv", '''
printf '%s\\n' "$*" >>"$EVENT_LOG"
if [[ "$*" == *"pip compile"* ]]; then
  if [[ "${FAIL_COMPILE:-0}" == 1 ]]; then exit 1; fi
  while [[ "$1" != --output-file ]]; do shift; done
  printf 'new-lock\\n' >"$2"
elif [[ "$*" == *"pip sync"* ]]; then
  if [[ "${FAIL_SYNC:-0}" == 1 ]]; then exit 1; fi
  while [[ "$1" != --python ]]; do shift; done
  # Manager depends on PyPI uv, whose bundled executable cannot run on NixOS.
  printf '#!/bin/sh\nexit 127\n' >"$(dirname "$2")/uv"
  chmod +x "$(dirname "$2")/uv"
elif [[ "$*" == *"pip install"* ]]; then
  printf '%s\\n' "$@" >"$EVENT_LOG.uv-args"
  printf '%s\\n' "$VIRTUAL_ENV" "$UV_PYTHON" "$PIP_CONSTRAINT" "$UV_CONSTRAINT" >"$EVENT_LOG.env"
  if [[ "${FAIL_INSTALL:-0}" == 1 ]]; then exit 23; fi
elif [[ "$*" == *venv* ]]; then
  destination="${!#}"
  mkdir -p "$destination/bin"
  cat >"$destination/bin/python" <<'PYTHON'
#!/usr/bin/env bash
printf '%s\\n' "$@" >>"$EVENT_LOG"
printf '%s\\n' "${VIRTUAL_ENV:-}" "${UV_PYTHON:-}" >"$EVENT_LOG.env"
if [[ "$1" == *check-gpu.py && "${FAIL_GPU:-0}" == 1 ]]; then exit 1; fi
if [[ "$*" == *--quick-test-for-ci* && "${FAIL_STARTUP:-0}" == 1 ]]; then exit 1; fi
if [[ "$*" == *--quick-test-for-ci* && "$*" == *--enable-manager* ]]; then
  while [[ "$1" != --base-directory ]]; do shift; done
  test -d "$2/custom_nodes"
fi
PYTHON
  chmod +x "$destination/bin/python"
else
  exit 99
fi
''')

    def executable(self, name, contents):
        path = self.bin / name
        shebang = f"#!{shutil.which('bash')}"
        path.write_text(
            shebang + "\nset -euo pipefail\n"
            + contents.replace("#!/usr/bin/env bash", shebang)
        )
        path.chmod(0o755)

    def run_script(self, script="setup.sh", *args, **environment):
        return subprocess.run(
            ["bash", "-euo", "pipefail", str(SCRIPTS / script), *args],
            env=self.environment | environment,
            text=True,
            capture_output=True,
        )

    def setup_ok(self, *args, **environment):
        result = self.run_script("setup.sh", *args, **environment)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return (self.data / "current").resolve()

    def test_setup_reuses_locked_environment_and_preserves_legacy(self):
        (self.data / "app").mkdir(parents=True)
        legacy = self.data / "app" / "local-node.py"
        legacy.write_text("user code")
        active = self.setup_ok()
        self.assertEqual((active / "ready").read_text(), "test-id\n")
        self.assertEqual(self.setup_ok(), active)
        self.assertEqual(legacy.read_text(), "user code")
        log = self.log.read_text()
        self.assertEqual(log.count("pip sync"), 1)
        self.assertNotIn("pip compile", log)
        self.assertNotIn("--clear", log)
        self.assertIn("--require-hashes --strict", log)
        self.assertIn("--quick-test-for-ci", log)
        self.assertIn("--enable-manager", log)
        self.assertTrue((active / ".venv/bin/uv").is_symlink())
        self.assertEqual((active / ".venv/bin/uv").resolve(), self.bin / "uv")

    def test_rebuild_keeps_previous_and_shared_data(self):
        first = self.setup_ok()
        model = self.data / "models" / "keep.safetensors"
        model.write_text("model")
        second = self.setup_ok("--rebuild")
        self.assertNotEqual(first, second)
        self.assertEqual((self.data / "previous").resolve(), first)
        self.assertTrue((first / ".venv/bin/python").exists())
        self.assertEqual(model.read_text(), "model")

    def test_app_is_a_writable_copy_independent_of_runtime(self):
        source = self.runtime / "app"
        (source / "nested").mkdir()
        (source / "nested/config.json").write_text("original")
        (source / "main.py").chmod(0o444)
        (source / "nested/config.json").chmod(0o444)
        (source / "nested").chmod(0o555)
        self.addCleanup((source / "nested").chmod, 0o755)
        active = self.setup_ok()
        app = active / "app"
        self.assertFalse(app.is_symlink())
        self.assertTrue((app / "main.py").stat().st_mode & 0o200)
        self.assertTrue((app / "nested").stat().st_mode & 0o200)
        self.assertTrue((app / "nested/config.json").stat().st_mode & 0o200)
        (app / "web/extensions/pysssss").mkdir(parents=True)
        (app / "nested/config.json").write_text("changed by extension")
        self.assertEqual((source / "nested/config.json").read_text(), "original")
        self.assertFalse((source / "web").exists())
        self.assertEqual(self.setup_ok(), active)
        self.assertEqual((app / "nested/config.json").read_text(), "changed by extension")

    def test_setup_migrates_store_link_without_modifying_old_environment(self):
        first = self.setup_ok()
        if (first / "app").is_symlink():
            (first / "app").unlink()
        else:
            shutil.rmtree(first / "app")
        (first / "app").symlink_to("runtime/app")
        second = self.setup_ok()
        self.assertNotEqual(first, second)
        self.assertFalse((second / "app").is_symlink())
        self.assertTrue((first / "app").is_symlink())
        self.assertEqual((self.data / "previous").resolve(), first)

    def test_new_runtime_id_creates_candidate_without_overwriting_old_one(self):
        first = self.setup_ok()
        second = self.setup_ok(environment_id="updated-id")
        self.assertNotEqual(first, second)
        self.assertEqual((second / "ready").read_text(), "updated-id\n")
        self.assertEqual((self.data / "previous").resolve(), first)

    def test_failed_install_gpu_or_startup_never_switches_current(self):
        first = self.setup_ok()
        for failure in ("FAIL_SYNC", "FAIL_GPU", "FAIL_STARTUP"):
            with self.subTest(failure=failure):
                result = self.run_script("setup.sh", "--rebuild", **{failure: "1"})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((self.data / "current").resolve(), first)
                self.assertFalse((self.data / "previous").exists())

    def test_refuses_user_owned_current_directory(self):
        (self.data / "current").mkdir(parents=True)
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-symlink", result.stderr)
        self.assertFalse(self.log.exists())

    def test_rejects_concurrent_setup(self):
        self.data.mkdir()
        with (self.data / ".setup.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Another ComfyUI setup", result.stderr)

    def test_invalid_arguments_do_not_create_an_environment(self):
        for args in (("--unknown",), ("--rebuild", "extra")):
            result = self.run_script("setup.sh", *args)
            self.assertEqual(result.returncode, 2)
        self.assertFalse(self.data.exists())

    def test_launch_uses_active_snapshot_and_optional_flags_only(self):
        active = self.setup_ok()
        self.log.write_text("")
        result = self.run_script("launch.sh", "--lowvram")
        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.log.read_text().splitlines()
        self.assertEqual(args[0], str(active / "app/main.py"))
        self.assertEqual(args.count("--lowvram"), 1)
        self.assertNotIn("--disable-dynamic-vram", args)
        self.assertEqual(args[args.index("--listen") + 1], "0.0.0.0")
        self.assertIn(str(self.data / "output"), args)
        self.assertEqual(args.count("--enable-manager"), 1)
        self.assertEqual(
            Path(f"{self.log}.env").read_text().splitlines(),
            [str(active / ".venv"), str(active / ".venv/bin/python")],
        )

    def test_launch_preserves_legacy_until_setup_succeeds(self):
        legacy = self.data / "app"
        legacy.mkdir(parents=True)
        (legacy / "main.py").touch()
        (self.data / ".venv/bin").mkdir(parents=True)
        python = self.data / ".venv/bin/python"
        python.write_text(f"#!{shutil.which('bash')}\nprintf '%s\\n' \"$@\" >\"$EVENT_LOG\"\n")
        python.chmod(0o755)
        result = self.run_script("launch.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text().splitlines()[0], str(legacy / "main.py"))

    def test_failed_initial_setup_does_not_activate_candidate(self):
        result = self.run_script("setup.sh", FAIL_GPU="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.data / "current").is_symlink())
        self.assertTrue(list((self.data / "environments").iterdir()))

    def test_update_lock_is_explicit_and_failure_preserves_old_lock(self):
        output = self.root / "requirements.lock"
        output.write_text("old-lock\n")
        result = self.run_script("update-lock.sh", str(output), FAIL_COMPILE="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output.read_text(), "old-lock\n")
        result = self.run_script("update-lock.sh", str(output))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.read_text(), "new-lock\n")
        self.assertIn(str(self.runtime / "app/manager_requirements.txt"), self.log.read_text())
        self.assertEqual(self.run_script("update-lock.sh").returncode, 2)

    def extension_requirements(self, name, contents="example-package\n"):
        node = self.data / "custom_nodes" / name
        node.mkdir(parents=True)
        requirements = node / "requirements.txt"
        requirements.write_text(contents)
        return requirements

    def test_install_deps_resolves_extensions_together_in_active_venv(self):
        active = self.setup_ok()
        first = self.extension_requirements("first node")
        second = self.extension_requirements("second")
        self.extension_requirements("ignored.disabled")
        self.extension_requirements(".hidden")
        external = self.root / "external node"
        external.mkdir()
        (external / "requirements.txt").write_text("linked-package\n")
        (self.data / "custom_nodes/linked").symlink_to(external)
        self.log.write_text("")
        result = self.run_script("install-deps.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        args = Path(f"{self.log}.uv-args").read_text().splitlines()
        self.assertEqual(args[:3], ["--no-config", "pip", "install"])
        self.assertEqual(args[args.index("--python") + 1], str(active / ".venv/bin/python"))
        self.assertEqual(args[args.index("--constraint") + 1], str(active / "constraints.txt"))
        self.assertEqual(args[args.index("--torch-backend") + 1], "cu126")
        self.assertEqual(args.count("--requirement"), 3)
        self.assertIn(str(first), args)
        self.assertIn(str(second), args)
        self.assertIn(str(self.data / "custom_nodes/linked/requirements.txt"), args)
        self.assertNotIn("ignored.disabled/requirements.txt", "\n".join(args))
        self.assertNotIn(".hidden/requirements.txt", "\n".join(args))
        self.assertEqual(self.log.read_text().count("pip install"), 1)
        self.assertNotIn("pip sync", self.log.read_text())
        self.assertEqual(
            Path(f"{self.log}.env").read_text().splitlines(),
            [str(active / ".venv"), str(active / ".venv/bin/python"),
             str(active / "constraints.txt"), str(active / "constraints.txt")],
        )
        self.assertEqual((self.data / "current").resolve(), active)
        self.assertEqual((active / ".venv/bin/uv").resolve(), self.bin / "uv")

    def test_install_deps_dry_run_does_not_replace_venv_tools(self):
        active = self.setup_ok()
        self.extension_requirements("node")
        uv = active / ".venv/bin/uv"
        uv.unlink()
        uv.write_text("sentinel")
        result = self.run_script("install-deps.sh", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--dry-run", Path(f"{self.log}.uv-args").read_text().splitlines())
        self.assertEqual(uv.read_text(), "sentinel")
        self.assertIn("venv was not changed", result.stdout)

    def test_install_deps_no_requirements_is_a_noop(self):
        self.setup_ok()
        self.log.write_text("")
        result = self.run_script("install-deps.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Nothing to install", result.stdout)
        self.assertEqual(self.log.read_text(), "")

    def test_install_deps_propagates_failure_without_switching_current(self):
        active = self.setup_ok()
        self.extension_requirements("conflicting-node")
        result = self.run_script("install-deps.sh", FAIL_INSTALL="1")
        self.assertEqual(result.returncode, 23)
        self.assertNotIn("dependencies installed", result.stdout)
        self.assertEqual((self.data / "current").resolve(), active)

    def test_install_deps_rejects_setup_lock_and_incomplete_environment(self):
        active = self.setup_ok()
        with (self.data / ".setup.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_script("install-deps.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Another ComfyUI", result.stderr)
        (active / "constraints.txt").unlink()
        result = self.run_script("install-deps.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("incomplete", result.stderr)

    def test_install_deps_requires_setup_and_valid_arguments(self):
        result = self.run_script("install-deps.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("comfyui-setup first", result.stderr)
        for args in (("--unknown",), ("--dry-run", "extra")):
            result = self.run_script("install-deps.sh", *args)
            self.assertEqual(result.returncode, 2)
        self.assertFalse(self.data.exists())


if __name__ == "__main__":
    unittest.main()
