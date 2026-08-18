"""The mem-cleaner runner.

Ships as source inside the extension, so it is installed by the same act that
installs the extension's Markdown and is updated by the same diff. That is the
whole reason it is standard-library only: nothing here can assume a package was
installed into the repository it lands in.

Modules:

    frontmatter  a restricted, non-guessing parser for definition front matter
    models       value types for providers, operations, pipelines and stages
    config       reads extensions_cleaner_* out of MEM.config.md
    registry     loads provider definitions, resolves capability + role
    pipeline     loads pipeline definitions and refuses invalid ones
    cli          the command line entry point

The engine -- registry and pipeline -- contains no provider id. Resolution goes
through tables built from data on disk, which makes the rule testable rather
than aspirational.
"""

VERSION = "0.1.0"
