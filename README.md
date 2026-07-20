## Kaggle Knowledge Graph

[![Tests](https://img.shields.io/github/actions/workflow/status/IssunDB/kaggle-knowledge-graph/tests.yml?label=tests&style=flat&labelColor=333333&logo=github&logoColor=white)](https://github.com/IssunDB/kaggle-knowledge-graph/actions/workflows/tests.yml)
[![Code Coverage](https://img.shields.io/codecov/c/github/IssunDB/kaggle-knowledge-graph?style=flat&label=coverage&labelColor=333333&logo=codecov&logoColor=white)](https://codecov.io/gh/IssunDB/kaggle-knowledge-graph)
[![License](https://img.shields.io/badge/license-MIT-00acc1?style=flat&labelColor=333333&logo=open-source-initiative&logoColor=white)](https://github.com/IssunDB/kaggle-knowledge-graph/blob/main/LICENSE)

---

This repository contains code for building a knowledge graph from the [Meta Kaggle](https://www.kaggle.com/datasets/kaggle/meta-kaggle) dataset
(and loading it into [IssunDB](https://github.com/IssunDB/issun-db) which provides CLI and MCP interfaces for querying the data).

### Quickstart

#### Data

##### 1. Download Dataset

```bash
curl -L -o /path/to/meta-kaggle.zip\
https://www.kaggle.com/api/v1/datasets/download/kaggle/meta-kaggle
```

##### 2. Configure Environment Variables

```bash
export META_KAGGLE_DIR="/path/to/meta-kaggle"
```

Alternatively, specify variables directly when executing build commands:

```bash
META_KAGGLE_DIR="/path/to/meta-kaggle" make graph-kc
```

#### Build and Launch

Build the competition knowledge graph and launch interactive or MCP interfaces:

- `make graph-kc` builds the competition knowledge graph.
- `make comp-cli` opens the competition knowledge graph in the IssunDB CLI.
- `make comp-mcp` runs the IssunDB MCP server for the competition knowledge graph.
- `make help` lists all available Makefile targets.

#### MCP Server Configuration

To connect external AI assistants or IDEs to the IssunDB MCP server, use the configuration template at `examples/mcp_config.json`:

```json
{
    "mcpServers": {
        "kaggle-comp-kg": {
            "command": "/path/to/kaggle-knowledge-graph/bin/issundb-mcp",
            "args": [
                "--db-path",
                "/path/to/kaggle-knowledge-graph/databases/comp-kg",
                "--map-size-gb",
                "8"
            ]
        }
    }
}
```

Replace `/path/to/kaggle-knowledge-graph` with the absolute path to your repository root directory.

---

### Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to make a contribution.

### License

This project is licensed under the MIT License (see [LICENSE](LICENSE)) except the knowledge graph data (built by the code in this repository), which
is subject to the [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) license.
