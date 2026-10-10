# Continue (open source)

Code pinned at continuedev/continue@5522c6f.

- **Repo map as context provider and tool:** `RepoMapContextProvider` and a `viewRepoMap` tool — https://github.com/continuedev/continue/blob/5522c6f44ca0ac3528b37244818fbfa39b5af470/core/context/providers/RepoMapContextProvider.ts, https://github.com/continuedev/continue/blob/5522c6f44ca0ac3528b37244818fbfa39b5af470/core/tools/definitions/viewRepoMap.ts. So the skeleton is offered on demand rather than always-on.
- **Token-budget pruning helpers** (prune lines from start/end to fit `maxTokens`) — https://github.com/continuedev/continue/blob/5522c6f44ca0ac3528b37244818fbfa39b5af470/core/llm/countTokens.ts#L284-L340.
- **Uncertain:** default indexing/embedding behavior in current versions not re-verified this pass.
