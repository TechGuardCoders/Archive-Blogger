# Archive Blogger

An automatic multi-agent Blogger created by **Tech Guard** ([techguard.io](https://techguard.io)).
It plans, validates, and writes polished technical blog posts covering company
achievements, milestones, and accomplishments, plus industry knowledge sharing.

Built as a multi-agent graph: a root Conductor agent delegates to two self-healing
loop agents (Planner and Writer), each paired with a binary validation checker
that retries up to 3 times until the output passes.

## Architecture

```
Blogger (Root Agent / Conductor)
 |-- planner_tool -> robust_blog_planner   [BlogPlanner -> OutlineValidationChecker, <=3]
 |-- writer_tool  -> robust_blog_writer    [BlogWriter  -> BlogPostValidationChecker, <=3]

Shared state keys:
  blog_outline       (BlogPlanner)
  validation_result  (both checkers)
  blog_post          (BlogWriter)
```

Flow: `topic -> validated outline -> validated full post -> 3 alternate titles + 2 X hooks`

## Agents

| Agent | Type | Role | output_key |
|---|---|---|---|
| Blogger | Root (LLM) | Conductor: calls planner then writer tools | - |
| robust_blog_planner | LoopAgent | BlogPlanner -> checker, max 3 iterations | - |
| BlogPlanner | LLM agent | Topic -> structured Markdown outline | blog_outline |
| OutlineValidationChecker | LLM agent | Binary gate: ok / retry | validation_result |
| robust_blog_writer | LoopAgent | BlogWriter -> checker, max 3 iterations | - |
| BlogWriter | LLM agent | Outline -> full Markdown post | blog_post |
| BlogPostValidationChecker | LLM agent | Binary gate: ok / retry | validation_result |

## Setup

Requires Python 3.10+.

```bash
pip install google-adk
export GOOGLE_API_KEY=your_key_here   # or configure your model provider
adk run archive_blogger               # CLI
# or
adk web                               # dev UI at http://localhost:8501
```

## Usage

Give the root agent a topic, e.g.:

> "How zero-trust access control protects hybrid cloud environments"

It will produce a validated outline, a validated full Markdown draft,
3 alternate titles, and 2 tweet-length hooks for X.

## Team

- Maintained by [TechGuardCoders](https://github.com/TechGuardCoders)
- Created by [@wsajafridi](https://github.com/wsajafridi)

## License

MIT
