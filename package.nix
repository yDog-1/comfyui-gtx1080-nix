{pkgs, ...}: let
  pin = import ./comfyui/source.nix;
  source = pkgs.fetchFromGitHub {
    owner = "Comfy-Org";
    repo = "ComfyUI";
    inherit (pin) rev hash;
  };
  # Each installed environment roots its runtime so Nix GC cannot break rollback.
  runtime = pkgs.linkFarm "comfyui-${pin.version}-runtime" [
    {
      name = "app";
      path = source;
    }
    {
      name = "python";
      path = pkgs.python312;
    }
    {
      name = "uv";
      path = pkgs.uv;
    }
    {
      name = "requirements.lock";
      path = ./comfyui/requirements.lock;
    }
    {
      name = "constraints.txt";
      path = ./comfyui/constraints.txt;
    }
    {
      name = "check-gpu.py";
      path = ./comfyui/check-gpu.py;
    }
  ];
  environmentId = builtins.substring 0 16 (builtins.hashString "sha256" (toString runtime));
  runtimeEnvironment = ''
    data_dir="''${XDG_DATA_HOME:-$HOME/.local/share}/ComfyUI"
    export current="$data_dir/current"
    export managed_runtime=${runtime}
    export environment_id=${environmentId}

    export CUDA_CACHE_PATH="$data_dir/.cache/cuda"
    export HF_HOME="$data_dir/.cache/huggingface"
    export TORCH_HOME="$data_dir/.cache/torch"
    export PYTHONPYCACHEPREFIX="$data_dir/.cache/pycache"
    export PYTHONNOUSERSITE=1
    export UV_PYTHON_DOWNLOADS=never
    # CUDA/cuDNN come from the locked wheels, never nixpkgs' newer cuDNN.
    export LD_LIBRARY_PATH="/run/opengl-driver/lib:${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.libx11}/lib"
    unset PYTHONPATH PYTHONHOME PIP_CONSTRAINT UV_CONSTRAINT
  '';
  command = name: inputs: script:
    pkgs.writeShellApplication {
      inherit name;
      runtimeInputs = [pkgs.coreutils] ++ inputs;
      text = runtimeEnvironment + script;
    };
  setup = command "comfyui-setup" [pkgs.nix pkgs.uv pkgs.util-linux pkgs.git] (builtins.readFile ./comfyui/setup.sh);
  launch = command "comfyui" [pkgs.ffmpeg pkgs.uv pkgs.git] (builtins.readFile ./comfyui/launch.sh);
  repair = command "comfyui-repair" [] ''
    exec ${setup}/bin/comfyui-setup --rebuild "$@"
  '';
  check = command "comfyui-check" [] ''
    if [[ ! -f "$current/ready" || ! -x "$current/.venv/bin/python" ]]; then
      echo "No managed environment. Run comfyui-setup first." >&2
      exit 1
    fi
    active=$(readlink -f "$current")
    exec "$active/.venv/bin/python" "$active/runtime/check-gpu.py" "$@"
  '';
  updateLock = command "comfyui-update-lock" [pkgs.uv] (builtins.readFile ./comfyui/update-lock.sh);
  installDeps = command "comfyui-install-deps" [pkgs.uv pkgs.util-linux pkgs.git] (builtins.readFile ./comfyui/install-deps.sh);
in
  pkgs.buildEnv {
    name = "comfyui-gtx1080-nix";
    paths = [launch setup repair check updateLock installDeps];
  }
