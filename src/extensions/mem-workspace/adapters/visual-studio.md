# Adapter: Visual Studio

One dev solution in `private/` that shows every repository of the workspace and lets each be committed without
leaving the IDE.

## Two solutions, one per audience

- **`<public>/<project>.slnx`** — the product only. It never mentions another repository. This is what CI builds
  and what a contributor opens. A public repository with nothing to compile has none.
- **`private/<project>.Dev.slnx`** — everything: the dev project by local path, product projects through
  `../<public>/…`, documentation repositories through their container project. This is what you open daily.

Only the dev solution crosses repositories, and it does so by relative path: folder names and adjacency are
load-bearing, which is why `MEM WORKSPACE INIT` records them.

## Making a repository committable

Visual Studio activates a repository — lists it in Git Changes, lets you stage, commit and push — only when the
open solution contains **a project located inside it**. Files alone never do.

| Technique | Visible | Picks up new files | Committable from the IDE |
|---|---|---|---|
| Solution folder with `<File Path>` entries | yes | **no** — one entry per file, forever | **no** |
| Linked files, `<None Include="..\..\<wiki>\**\*.md" LinkBase="Wiki" />` | yes | yes | **no** |
| **Container project inside the repository** | yes | yes | **yes** |

For a repository with no project of its own — the knowledge base, a wiki — add a container project that holds
files and compiles nothing, at the root of **that** repository:

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
    <EnableDefaultItems>false</EnableDefaultItems>
    <IsPackable>false</IsPackable>
  </PropertyGroup>
  <ItemGroup>
    <None Include="**\*.md" Exclude=".git\**;bin\**;obj\**" />
  </ItemGroup>
</Project>
```

- It emits one empty assembly into `bin/`; `Microsoft.Build.NoTargets` emits none, at the cost of an external SDK.
- Do **not** set `NoBuild=true`: `dotnet build` then fails with `NETSDK1085`.
- Give that repository a `.gitignore` for `bin/`, `obj/` and `.vs/`.
- The project file is committed to that repository. For a wiki that is public: it does not become a page, but
  anyone cloning the wiki sees it.

Do not add one to a public repository whose contract is "no build": the cost there falls on every reader.
Commit it from the command line or a second IDE window instead.

## Check

Added to `MEM WORKSPACE CHECK` as check 14 when `custom/workspace.md` names this adapter:

- every `Path` in the dev solution file resolves, `<File Path>` entries included — error otherwise.
  `dotnet sln <dev solution> list` shows projects only, so read the file. A stale `<File Path>` is the usual
  finding: the list is static and a renamed file leaves its old entry behind;
- no tracked `.slnx`, `.sln`, `.csproj` or `.props` file in a public repository contains `../<private>/` — this is
  check 8 narrowed to build files, and it reports as error.
