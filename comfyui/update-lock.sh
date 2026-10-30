if [[ $# -ne 1 ]]; then
  echo "Usage: comfyui-update-lock OUTPUT_FILE" >&2
  echo "Review and commit the generated lock; setup never resolves dependencies." >&2
  exit 2
fi
output=$(realpath -m "$1")
temporary=$(mktemp "$(dirname "$output")/.comfyui-lock.XXXXXXXX")
trap 'rm -f -- "$temporary"' EXIT
uv --no-config pip compile "$managed_runtime/app/requirements.txt" \
  "$managed_runtime/app/manager_requirements.txt" \
  --constraint "$managed_runtime/constraints.txt" \
  --python "$managed_runtime/python/bin/python" \
  --python-platform x86_64-manylinux_2_28 \
  --default-index https://pypi.org/simple \
  --torch-backend cu126 --only-binary :all: \
  --generate-hashes --no-annotate --no-header \
  --output-file "$temporary" --quiet
mv -f "$temporary" "$output"
echo "Generated $output. Review the diff before committing it."
