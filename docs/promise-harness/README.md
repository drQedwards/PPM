# Promise harness (Q)

Ancestral walk lineage with `parentPtr` + `lastImprovedPtr`.
Uses npm `q@1.5.1`. Run from a checkout that can see
`/workspace/siphon-walk/graph.json` and `/workspace/btc-puzzle/patterns/export.csv`
(or pass the same files as `graph.json` / `export.csv` symlinks in the work dir).

```
npm install
nice -n 19 node run.js
```

See `RESULTS.md` for measured numbers. Does not touch keyhunt or Cowcraft.
