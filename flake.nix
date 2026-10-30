{
  description = "Nix-managed ComfyUI environment for the NVIDIA GeForce GTX 1080";

  inputs.nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";

  outputs = {nixpkgs, ...}: let
    system = "x86_64-linux";
    pkgs = import nixpkgs {inherit system;};
    package = import ./package.nix {inherit pkgs;};
  in {
    homeModules.default = ./module.nix;

    packages.${system}.default = package;

    checks.${system} = {
      commands = package;
      comfyui-setup =
        pkgs.runCommand "comfyui-setup-tests" {
          nativeBuildInputs = [pkgs.python312 pkgs.util-linux];
        } ''
          export PYTHONDONTWRITEBYTECODE=1
          python ${./comfyui}/test_setup.py -v
          touch "$out"
        '';
    };

    formatter.${system} = pkgs.alejandra;
  };
}
