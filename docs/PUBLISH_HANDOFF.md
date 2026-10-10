# Publish handoff (for the 10:08 build sprint)

Launch one Cursor cloud agent on `bicrick/personal-website` (branch `master`) with the brief below. Open a PR only; never merge (merging deploys publicly on Vercel, and Patrick decides).

## Brief for the cloud agent
Add a project page for the case study "Same model, better harness" to bicrick.com.

- Source text and figures: `publish/context-shaping/index.md` and `publish/context-shaping/figures/*.png` on `main` of the private repo `bicrick/context-shaping`. If you can't read that repo, stop and report; don't invent content. Every number must be copied exactly from index.md.
- Match the site's existing project pages: a component `src/projects/ContextShaping.js` using `<ProjectDetail title date backHref abstract>`, lowercase `/ section` `<h2>` headings, plain `<p>` prose, tables as simple HTML tables, the per-task `<details>` block kept collapsible. Reference pages: `src/projects/AgentResearchLoops.js`, `src/projects/Tracebench.js`.
- Figures go in `public/images/context-shaping/`; register the project in `src/constants/projects.js` (title, description, timelineDescription, image = headline.png, blogLink `/projects/context-shaping`, date Oct 2026, ranks consistent with neighbours) and add the route in `src/App.js`. Generate an OG card with `scripts/generate-og-images.py` if that's how other projects do it.
- Keep the article's voice (first person, plain). Don't add claims, marketing copy, or links that aren't in index.md. The "Reproduce it" section links to the context-shaping repo, which is private until Patrick decides; leave the commands but note in the PR description that the repo link needs the visibility decision.
- Success: `npm run build` passes, the page renders at `/projects/context-shaping` with all 10 figures, and the PR description lists every file changed plus the open repo-visibility question.

## Before launching
- Confirm the 9:53 editor pass committed and `make figures` (or the audit/report/article/publish_bundle chain) is clean; push `main` so the agent sees the latest bundle.
- After launch: wake the parent with the PR link for the "case study ready" milestone (article finished + PR open for Patrick to review/merge, repo visibility decision).
