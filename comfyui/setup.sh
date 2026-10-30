rebuild=false
case "${1:-}" in
  "") ;;
  --rebuild) rebuild=true; shift ;;
  *) echo "Usage: comfyui-setup [--rebuild]" >&2; exit 2 ;;
esac
if [[ $# -ne 0 ]]; then
  echo "Usage: comfyui-setup [--rebuild]" >&2
  exit 2
fi

mkdir -p "$data_dir"/{environments,custom_nodes,input,models,output,user} \
  "$CUDA_CACHE_PATH" "$HF_HOME" "$TORCH_HOME"
# Serialize setup/repair; neither may modify the currently running environment.
exec 9>"$data_dir/.setup.lock"
flock -n 9 || { echo "Another ComfyUI setup is running." >&2; exit 1; }
for pointer in current previous; do
  if [[ -e "$data_dir/$pointer" && ! -L "$data_dir/$pointer" ]]; then
    echo "Refusing to replace non-symlink: $data_dir/$pointer" >&2
    exit 1
  fi
done

if ! "$rebuild" && [[ -f "$current/ready" ]] && \
  [[ "$(cat "$current/ready")" == "$environment_id" ]] && \
  [[ -d "$current/app" && ! -L "$current/app" && -w "$current/app" ]] && \
  [[ -x "$current/.venv/bin/python" ]]; then
  "$current/.venv/bin/python" "$current/runtime/check-gpu.py"
  echo "ComfyUI is already prepared. Start it with: comfyui"
  exit 0
fi

candidate=$(mktemp -d "$data_dir/environments/$environment_id.XXXXXXXX")
next_link="$data_dir/.current.$$"
previous_link="$data_dir/.previous.$$"
trap 'rm -f -- "$next_link" "$previous_link"' EXIT
echo "Preparing candidate: $candidate"
echo "On failure the current environment is unchanged; the candidate is kept for inspection."

nix-store --realise "$managed_runtime" --add-root "$candidate/runtime" --indirect >/dev/null
# Extensions may write beside server.py (for example web/extensions). Keep the
# pinned source rooted, but never run directly from its read-only store path.
cp -R --no-preserve=mode "$candidate/runtime/app/." "$candidate/app"
chmod -R u+w "$candidate/app"
ln -s runtime/constraints.txt "$candidate/constraints.txt"
uv --no-config venv --python "$candidate/runtime/python/bin/python" \
  --no-managed-python "$candidate/.venv"
uv --no-config pip sync "$candidate/runtime/requirements.lock" \
  --python "$candidate/.venv/bin/python" \
  --default-index https://pypi.org/simple \
  --torch-backend cu126 --only-binary :all: --require-hashes --strict

# Manager prepends the venv bin directory and also tries `python -m uv`.
# Both must use Nix's executable, not the generic Linux binary from the wheel.
ln -sfn "$candidate/runtime/uv/bin/uv" "$candidate/.venv/bin/uv"
ln -sfn "$candidate/runtime/uv/bin/uvx" "$candidate/.venv/bin/uvx"
export VIRTUAL_ENV="$candidate/.venv"
export UV_PYTHON="$candidate/.venv/bin/python"

"$candidate/.venv/bin/python" "$candidate/runtime/check-gpu.py"
# Exercise core imports/startup without touching the user's DB or custom nodes.
mkdir -p "$candidate/startup-check/custom_nodes"
"$candidate/.venv/bin/python" "$candidate/app/main.py" \
  --base-directory "$candidate/startup-check" \
  --enable-manager --disable-all-custom-nodes --disable-partner-nodes --quick-test-for-ci
printf '%s\n' "$environment_id" >"$candidate/ready"

if [[ -L "$current" ]] && [[ -d "$current" ]]; then
  ln -s "$(readlink -f "$current")" "$previous_link"
  mv -Tf "$previous_link" "$data_dir/previous"
fi
ln -s "$candidate" "$next_link"
mv -Tf "$next_link" "$current"
echo "ComfyUI is ready. Start it with: comfyui"
echo "Previous environments and the legacy app/.venv have not been deleted."
