{
  description = "Nix-managed ComfyUI environment for the NVIDIA GeForce GTX 1080";

  inputs.nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";

  outputs = {nixpkgs, ...}: let
    system = "x86_64-linux";
    pkgs = import nixpkgs {inherit system;};
    package = import ./package.nix {inherit pkgs;};
    formatter = pkgs.treefmt.withConfig {
      runtimeInputs = [pkgs.alejandra pkgs.ruff pkgs.shfmt pkgs.prettier];

      settings = {
        tree-root-file = "flake.nix";
        excludes = [".gitignore" "comfyui/requirements.lock"];
        formatter = {
          alejandra = {
            command = "alejandra";
            includes = ["*.nix"];
          };
          ruff = {
            command = "ruff";
            options = ["format"];
            includes = ["*.py"];
          };
          shfmt = {
            command = "shfmt";
            options = ["-w" "-i" "2" "-ln" "bash"];
            includes = ["*.sh"];
          };
          prettier = {
            command = "prettier";
            options = ["--write"];
            includes = ["*.md" "*.yml" "*.yaml"];
          };
          json = {
            command = "prettier";
            options = ["--write" "--parser" "json"];
            includes = ["*.json" "flake.lock"];
          };
        };
      };
    };
    source = pkgs.lib.cleanSource ./.;
  in {
    homeModules.default = ./module.nix;

    packages.${system}.default = package;

    checks.${system} = {
      commands = package;
      formatting = formatter.check source;
      secrets =
        pkgs.runCommand "gitleaks" {
          nativeBuildInputs = [pkgs.gitleaks];
        } ''
          gitleaks dir ${source} --redact=100 --no-banner --exit-code 1
          touch "$out"
        '';
      nix-lint =
        pkgs.runCommand "nix-lint" {
          nativeBuildInputs = [pkgs.deadnix pkgs.statix];
        } ''
          cd ${source}
          deadnix --fail .
          statix check .
          touch "$out"
        '';
      python-lint =
        pkgs.runCommand "python-lint" {
          nativeBuildInputs = [pkgs.ruff];
        } ''
          cd ${source}
          ruff check --no-cache .
          touch "$out"
        '';
      actionlint =
        pkgs.runCommand "actionlint" {
          nativeBuildInputs = [pkgs.actionlint pkgs.shellcheck];
        } ''
          cd ${source}
          actionlint .github/workflows/*.yml
          touch "$out"
        '';
      comfyui-setup =
        pkgs.runCommand "comfyui-setup-tests" {
          nativeBuildInputs = [pkgs.python312 pkgs.util-linux];
        } ''
          export PYTHONDONTWRITEBYTECODE=1
          python ${./comfyui}/test_setup.py -v
          touch "$out"
        '';
    };

    formatter.${system} = formatter;
  };
}
