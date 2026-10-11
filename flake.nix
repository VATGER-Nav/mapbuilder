{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    flake-parts.url = "github:hercules-ci/flake-parts";
    pyproject-nix = {
      url = "github:nix-community/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:adisbladis/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs = {
        pyproject-nix.follows = "pyproject-nix";
        uv2nix.follows = "uv2nix";
        nixpkgs.follows = "nixpkgs";
      };
    };
  };

  outputs =
    inputs@{ flake-parts, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } (
      { inputs, ... }:
      {
        systems = [
          "x86_64-linux"
          "aarch64-linux"
        ];

        perSystem =
          {
            pkgs,
            lib,
            self',
            ...
          }:
          let
            workspace = inputs.uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };
            overlay = workspace.mkPyprojectOverlay {
              sourcePreference = "wheel";
            };

            python = pkgs.python314;

            pythonSet =
              (pkgs.callPackage inputs.pyproject-nix.build.packages {
                inherit python;
              }).overrideScope
                (
                  lib.composeManyExtensions [
                    inputs.pyproject-build-systems.overlays.default
                    overlay
                    (final: prev: {
                      fiona = prev.fiona.overrideAttrs (old: {
                        nativeBuildInputs = old.nativeBuildInputs ++ [
                          pkgs.gdal
                          (final.resolveBuildSystem {
                            setuptools = [ ];
                            cython = [ ];
                          })
                        ];
                      });
                    })
                  ]
                );
          in
          {
            packages = {
              mapbuilder = (pythonSet.mkVirtualEnv "mapbuilder-env" workspace.deps.default);

              docker = pkgs.dockerTools.buildLayeredImage {
                name = "ghcr.io/vatger-nav/mapbuilder";
                tag = "latest";

                contents = [
                  pkgs.cacert
                  pkgs.tzdata
                  self'.packages.mapbuilder
                ];

                config = {
                  Env = [
                    "SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt"
                    "PYTHONDONTWRITEBYTECODE=1"
                    "PYTHONUNBUFFERED=1"
                  ];
                  WorkingDir = "/bin";
                  Entrypoint = [ "mapbuilder" ];
                };
              };
            };

            devShells =
              let
                editableOverlay = workspace.mkEditablePyprojectOverlay {
                  root = "$REPO_ROOT";
                };
                editablePythonSet = pythonSet.overrideScope (
                  lib.composeManyExtensions [
                    editableOverlay
                    (final: prev: {
                      mapbuilder = prev.mapbuilder.overrideAttrs (old: {
                        # Hatchling (our build system) has a dependency on the `editables` package when building editables.
                        #
                        # In normal Python flows this dependency is dynamically handled, and doesn't need to be explicitly declared.
                        # This behaviour is documented in PEP-660.
                        #
                        # With Nix the dependency needs to be explicitly declared.
                        nativeBuildInputs =
                          old.nativeBuildInputs
                          ++ final.resolveBuildSystem {
                            editables = [ ];
                          };
                      });
                    })
                  ]
                );
                virtualenv = editablePythonSet.mkVirtualEnv "mapbuilder-dev-env" workspace.deps.all;
                commonPackages = [
                  virtualenv
                  pkgs.uv
                ];
              in
              {
                default = pkgs.mkShell {
                  packages = commonPackages;
                  shellHook = ''
                    export REPO_ROOT=$(git rev-parse --show-toplevel)
                    # Stable interpreter path for editors (VS Code etc.)
                    ln -sfn ${virtualenv} "$REPO_ROOT/.venv"
                  '';
                  env = {
                    # Don't create venv using uv
                    UV_NO_SYNC = "1";

                    # Force uv to use Python interpreter from venv
                    UV_PYTHON = "${virtualenv}/bin/python";

                    # Prevent uv from downloading managed Python's
                    UV_PYTHON_DOWNLOADS = "never";

                    PYTHONPATH = ".:${virtualenv}/${python.sitePackages}";
                  };
                };
              };

            formatter = pkgs.nixfmt;
          };
      }
    );
}
