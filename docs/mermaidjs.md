https://www.mermaid.ai/play

```
---
title: Sample Git flow
---
gitGraph
    commit id: "start"
    branch release
    branch dev
    commit id: "start dev"

    checkout dev
    branch feature-X

    checkout feature-X
    commit
    commit
    checkout dev
    merge feature-X tag: "merge X"

    checkout release
    merge dev tag: "Release X"
    checkout main
    merge release tag: "Marge after release X"

    %% checkout dev
    %% branch feature-Y
    %% commit
    %% commit
    %% commit
    %% checkout dev
    %% merge feature-Y tag: "merge Y"

    %% checkout release
    %% merge dev tag: "Release Y"
    %% checkout main
    %% merge release tag: "Marge after release Y"
```