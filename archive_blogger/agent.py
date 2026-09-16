"""Archive Blogger - multi-agent blog pipeline (Google ADK).

Root agent "Blogger" delegates to two loop agents:
  planner_tool -> robust_blog_planner  (BlogPlanner + OutlineValidationChecker)
  writer_tool  -> robust_blog_writer   (BlogWriter + BlogPostValidationChecker)
"""

import datetime

from google.adk.agents import Agent, LlmAgent
from google.adk.agents.loop_agent import LoopAgent
from google.adk.tools import agent_tool

# ---------------------------------------------------------------------------
# Leaf agents
# ---------------------------------------------------------------------------

blog_planner = LlmAgent(
    name="BlogPlanner",
    model="gemini-2.0-flash",
    description="Creates a practical skimmable outline in Markdown.",
    instruction=(
        "You are a technical content strategist. Produce a clear Markdown "
        "outline with: Title, Short Intro, 4-6 main sections (each with "
        "2-3 bullets), and a Conclusion. Never use em dashes or hyphens "
        "in the outline text; rephrase instead."
    ),
    output_key="blog_outline",
)

outline_validator = LlmAgent(
    name="OutlineValidationChecker",
    model="gemini-2.0-flash",
    description="Validates that the outline is usable.",
    instruction=(
        "Check the outline in state 'blog_outline'. If it has a title, "
        "intro, 4-6 sections, and a conclusion, respond exactly 'ok'. "
        "Otherwise respond exactly 'retry' and list the missing pieces."
    ),
    output_key="validation_result",
)

blog_writer = LlmAgent(
    name="BlogWriter",
    model="gemini-2.0-flash",
    description="Writes a technical blog post from the outline.",
    instruction=(
        "Write a complete Markdown article from the outline in "
        "'blog_outline'. Guidelines: Audience: software engineers, AI "
        "engineers, data engineers, data security analysts, cloud "
        "engineers; skip basics and focus on practical insight. Explain "
        "both the 'how' and the 'why'. Include concise code snippets when "
        "helpful. Follow the outline's structure (H2/H3). Never use em "
        "dashes or hyphens in prose; rephrase instead (hyphens are "
        "allowed only inside code blocks, URLs, and file names). Output "
        "only the final article in Markdown (no fence around the whole "
        "post)."
    ),
    output_key="blog_post",
)

post_validator = LlmAgent(
    name="BlogPostValidationChecker",
    model="gemini-2.0-flash",
    description="Validates the final post.",
    instruction=(
        "Check 'blog_post' for: intro, clear sections matching the "
        "outline, conclusion, and technical clarity. If it passes, "
        "respond exactly 'ok'. Else respond exactly 'retry' with "
        "specific fixes."
    ),
    output_key="validation_result",
)

# ---------------------------------------------------------------------------
# Loop agents (plan + validate, write + validate; each up to 3 iterations)
# ---------------------------------------------------------------------------

robust_blog_planner = LoopAgent(
    name="robust_blog_planner",
    description="Plans an outline and validates it, retrying up to 3 times.",
    sub_agents=[blog_planner, outline_validator],
    max_iterations=3,
)

robust_blog_writer = LoopAgent(
    name="robust_blog_writer",
    description="Writes the post and validates it, retrying up to 3 times.",
    sub_agents=[blog_writer, post_validator],
    max_iterations=3,
)

# ---------------------------------------------------------------------------
# Expose loops as tools for the root agent
# ---------------------------------------------------------------------------

planner_tool = agent_tool.AgentTool(agent=robust_blog_planner)
writer_tool = agent_tool.AgentTool(agent=robust_blog_writer)

# ---------------------------------------------------------------------------
# Root agent
# ---------------------------------------------------------------------------

root_agent = Agent(
    name="Blogger",
    model="gemini-2.0-flash",
    description="Minimal multi-agent blogger that plans and writes.",
    instruction=f"""If the user gives a topic:
1) Call the planner tool to generate the outline.
2) Call the writer tool to produce the full draft.
3) End with 3 alternate titles and 2 tweet-length hooks for X.
Date: {datetime.datetime.now().strftime("%Y-%m-%d")}""",
    tools=[planner_tool, writer_tool],
)
