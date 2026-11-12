{
  description = "Development environment for the Kaggle knowledge graph";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs, ... }:
    let
      supportedSystems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
    in
    {
      devShells = forAllSystems (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          linuxRuntimeLibs = with pkgs; [
            stdenv.cc.cc.lib
            zlib
          ];
        in
        {
          default = pkgs.mkShell {
            packages = with pkgs;
              [
                python314
                uv
                gnumake
                git
                pre-commit
                duckdb
                pkg-config
              ]
              ++ pkgs.lib.optionals pkgs.stdenv.hostPlatform.isLinux linuxRuntimeLibs;

            shellHook =
              pkgs.lib.optionalString pkgs.stdenv.hostPlatform.isLinux ''
                export LD_LIBRARY_PATH="${pkgs.lib.makeLibraryPath linuxRuntimeLibs}:''${LD_LIBRARY_PATH:-}"
              ''
              + ''
                export UV_PYTHON="${pkgs.python314}/bin/python3"
                export PATH="$PWD/bin:$PATH"

                echo "Kaggle Knowledge Graph dev shell"
                echo "Python: $(${pkgs.python314}/bin/python3 --version)"
                echo "uv: $(${pkgs.uv}/bin/uv --version)"
                echo ""
                echo "Common commands:"
                echo "  make install     # Install Python dependencies"
                echo "  make test        # Run tests"
                echo "  make format      # Format code"
                echo "  make lint        # Run linter checks"
                echo "  make typecheck   # Typecheck code"
                echo "  make graph-kc    # Build the Kaggle knowledge graph"
                echo "  make comp-cli    # Open Kaggle knowledge graph in IssunDB CLI"
                echo "  make help        # Show all available targets"
              '';
          };
        }
      );

      formatter = forAllSystems (system: nixpkgs.legacyPackages.${system}.nixpkgs-fmt);
    };
}
