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

## How It Works

1. **You give a topic.** A subject line is enough: a company milestone, a project writeup, or an industry knowledge piece.
2. **The Planner loop runs.** `BlogPlanner` drafts a Markdown outline into shared state under `blog_outline`. `OutlineValidationChecker` gates it: if the outline is missing a title, intro, 4 to 6 sections, or a conclusion, the loop reruns the planner, up to 3 attempts.
3. **The Writer loop runs.** `BlogWriter` turns the validated outline into a full Markdown article under `blog_post`, written for a technical audience (software, AI, data, security, and cloud engineers) with practical insight rather than basics. `BlogPostValidationChecker` gates it for intro, section structure, conclusion, and technical clarity, again up to 3 attempts.
4. **You get the finished copy:** the full article, 3 alternate titles, and 2 tweet length hooks for X. Publish it wherever your blog lives.

Each loop is self healing: a failed validation automatically feeds its specific complaints back into the next attempt, so quality gates do the proofreading instead of you.

## Setup

Requires Python 3.10+.

### 1. Get the code

```bash
git clone https://github.com/TechGuardCoders/Archive-Blogger.git
cd Archive-Blogger
```

### 2. Install Python and dependencies

**Linux / macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Configure a model key

The agents run on any model the Google ADK supports. Export a key for your provider:

**Linux / macOS:**

```bash
export GOOGLE_API_KEY=your_key_here
```

**Windows (PowerShell):**

```powershell
$env:GOOGLE_API_KEY = "your_key_here"
```

(Or set `model=` in `archive_blogger/agent.py` to any provider string your ADK install supports, e.g. an Anthropic or OpenAI model via a compatible integration.)

### 4. Run

```bash
adk run archive_blogger        # terminal chat
# or
adk web                        # dev UI at http://localhost:8501
```

### 5. Adjust the writing rules (optional)

The Planner and Writer carry style instructions (audience, structure, validation criteria) in `archive_blogger/agent.py`. Edit that file to change tone, audience, or output format, then rerun. The graph is intentionally small; read it top to bottom in one sitting.

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
