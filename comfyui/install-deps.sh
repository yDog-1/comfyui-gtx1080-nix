options=()
case "${1:-}" in
  "") ;;
  --dry-run) options+=(--dry-run); shift ;;
  *) echo "Usage: comfyui-install-deps [--dry-run]" >&2; exit 2 ;;
esac
if [[ $# -ne 0 ]]; then
  echo "Usage: comfyui-install-deps [--dry-run]" >&2
  exit 2
fi

if [[ ! -L "$current" || ! -f "$current/ready" ]]; then
  echo "No managed environment. Run comfyui-setup first." >&2
  exit 1
fi
# Share setup's lock so a concurrent rebuild cannot change the target midway.
exec 9>"$data_dir/.setup.lock"
flock -n 9 || { echo "Another ComfyUI setup or dependency install is running." >&2; exit 1; }
active=$(readlink -f "$current")
if [[ ! -f "$active/ready" || ! -x "$active/.venv/bin/python" || ! -f "$active/constraints.txt" ]]; then
  echo "ComfyUI environment is incomplete. Run comfyui-repair." >&2
  exit 1
fi

requirements=()
shopt -s nullglob
for node in "$data_dir/custom_nodes/"*; do
  [[ -d "$node" && "$node" != *.disabled && -f "$node/requirements.txt" ]] || continue
  echo "Requirements: $node/requirements.txt"
  requirements+=(--requirement "$node/requirements.txt")
done
if [[ ${#requirements[@]} -eq 0 ]]; then
  echo "No extension requirements.txt files found. Nothing to install."
  exit 0
fi

export VIRTUAL_ENV="$active/.venv"
export UV_PYTHON="$active/.venv/bin/python"
export PIP_CONSTRAINT="$active/constraints.txt"
export UV_CONSTRAINT="$active/constraints.txt"
echo "Target environment: $active"
echo "Stop ComfyUI and avoid Manager package operations before installing dependencies."
# Resolve all extensions together; never sync away unrelated installed packages.
uv --no-config pip install \
  --python "$active/.venv/bin/python" \
  --constraint "$active/constraints.txt" \
  --default-index https://pypi.org/simple \
  --torch-backend cu126 \
  "${options[@]}" "${requirements[@]}"
if [[ ${#options[@]} -ne 0 ]]; then
  echo "Dry run complete. The venv was not changed."
  exit 0
fi
# Requirements can include PyPI uv; retain the NixOS-compatible executables.
ln -sfn "$active/runtime/uv/bin/uv" "$active/.venv/bin/uv"
ln -sfn "$active/runtime/uv/bin/uvx" "$active/.venv/bin/uvx"
echo "Extension dependencies installed. Restart ComfyUI, then run comfyui-check."
