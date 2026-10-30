# Resolve once so a concurrent setup cannot mix the old interpreter and new app.
if [[ -L "$current" && -f "$current/ready" ]]; then
  active=$(readlink -f "$current")
elif [[ ! -e "$current" && ! -L "$current" && -x "$data_dir/.venv/bin/python" ]]; then
  # Keep the legacy installation usable until the first managed setup succeeds.
  active="$data_dir"
else
  echo "ComfyUI is not initialized. Run comfyui-setup first." >&2
  exit 1
fi
if [[ ! -x "$active/.venv/bin/python" || ! -f "$active/app/main.py" ]]; then
  echo "ComfyUI environment is incomplete. Run comfyui-repair." >&2
  exit 1
fi
export PIP_CONSTRAINT="$active/constraints.txt"
export UV_CONSTRAINT="$active/constraints.txt"
export VIRTUAL_ENV="$active/.venv"
export UV_PYTHON="$active/.venv/bin/python"
mkdir -p "$data_dir"/{custom_nodes,input,models,output,user} \
  "$CUDA_CACHE_PATH" "$HF_HOME" "$TORCH_HOME"
exec "$active/.venv/bin/python" "$active/app/main.py" \
  --base-directory "$data_dir" \
  --input-directory "$data_dir/input" \
  --output-directory "$data_dir/output" \
  --user-directory "$data_dir/user" \
  --database-url "sqlite:///$data_dir/user/comfyui.db" \
  --listen 0.0.0.0 \
  --enable-manager \
  "$@"
