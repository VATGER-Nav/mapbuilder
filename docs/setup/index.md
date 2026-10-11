---
icon: lucide/rocket
---

# Installation and usage

mapbuilder is a command-line tool. It reads a source directory with a `mapbuilder.toml` and your map
templates, and writes the finished GRP and TopSky files into a target directory.

## Running mapbuilder

=== "GitHub Action"

    The easiest way to build maps for a repository is the GitHub Action. It runs mapbuilder in a
    container and keeps downloaded data in a cache between runs:

    ```yaml title=".github/workflows/maps.yml"
    jobs:
      build-maps:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - name: Restore cached sources
            uses: actions/cache/restore@v4
            with:
              path: .cache
              key: sources
          - name: Run mapbuilder
            uses: vatger-nav/mapbuilder@main
            with:
              target-path: '.'          # where the map files are written (default)
              source-path: 'mapdata'    # directory with mapbuilder.toml (default)
          - name: Store cached sources
            uses: actions/cache/save@v4
            with:
              path: .cache
              key: sources
    ```

    Both paths are relative to the repository root.

=== "uv"

    With [uv](https://docs.astral.sh/uv/) installed, run mapbuilder directly from the repository:

    ```sh
    uvx --from git+https://github.com/VATGER-Nav/mapbuilder@v2 mapbuilder
    ```

    or install it as a tool:

    ```sh
    uv tool install git+https://github.com/VATGER-Nav/mapbuilder@v2
    mapbuilder
    ```

    mapbuilder needs Python 3.11 or newer.

=== "Nix"

    The repository is a Nix flake with a `mapbuilder` package and a development shell:

    ```sh
    nix shell github:VATGER-Nav/mapbuilder/v2#mapbuilder -c mapbuilder
    ```

=== "Docker"

    ```sh
    docker run --rm -v "$PWD:/work" ghcr.io/vatger-nav/mapbuilder:v2 -s /work/mapdata /work
    ```

## Command line

```text
mapbuilder [options] [target_dir]
```

| Option | Default | Description |
|---|---|---|
| `target_dir` | current directory | Where the map files are written. The `target` paths in `mapbuilder.toml` are relative to it. |
| `-s`, `--source` | `./mapdata` | Source directory containing `mapbuilder.toml` and the `maps/` directory. |
| `-c`, `--cache` | `<target_dir>/.cache` | Where downloaded data is cached. |
| `--debug` | off | Log details about every file that is processed. |

A typical repository runs mapbuilder from its root, with the sources in `mapdata/` and the generated
files committed next to it:

```sh
mapbuilder            # reads ./mapdata/mapbuilder.toml, writes into the current directory
```

mapbuilder logs one line per generated file and warnings about anything in the data or templates
that could not be rendered. Check the warnings after changing templates or data.

## Downloaded data and the cache

Data sources can point to files in the source directory, to URLs or to DFS datasets (see
[Data sources](configuration.md#data-sources)). Downloads are stored in the cache directory and reused
for 96 hours; ZIP files are unpacked automatically. Delete the cache directory to force a fresh
download.

The cache directory also stores fragments of templates that use `{% cache %}` blocks.

## Next steps

- [Project layout](project.md): how the source directory and map directories are organised.
- [Configuration](configuration.md): all settings in `mapbuilder.toml`.
- [Writing map templates](../authoring/index.md): how to draw maps from your data.
