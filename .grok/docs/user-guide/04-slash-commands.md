# Slash Commands

Type `/` in the prompt to access commands. Each command runs an action immediately and autocompletes as you type.

Slash commands come from two sources:

- **Shell builtins** -- handled by the agent backend (xai-grok-shell)
- **Pager builtins** -- handled by the TUI frontend (xai-grok-pager)

Both sets are available in the autocomplete menu. Skills installed via SKILL.md files also appear as slash commands.

---

## Session Management

### `/new`

Start a new session, clearing the current conversation.

```
/new
```

Aliases: `/clear`

### `/resume`

Open the session picker to load a previous session from disk.

```
/resume
```

### `/compact [context]`

Compress conversation history to save context window space. Optionally specify what to preserve.

```
/compact
/compact keep the auth implementation details
```

When the context window fills up, Grok auto-compacts at 85% usage (configurable via `[session] auto_compact_threshold_percent` in config.toml).

### `/context`

Show context window usage and session stats.

```
/context
```

### `/session-info`

Show session details including model, turn count, and context usage.

```
/session-info
```

### `/sessions`

Open the active-sessions switcher to switch, rename, or close running sessions.
On the agent dashboard the command is a no-op (sessions are already listed there);
from an agent session it opens the switcher.

```
/sessions
```

### `/fork`

Branch the current session into a new agent, preserving history up to this point.

```
/fork
```

### `/rewind`

Rewind the conversation to an earlier turn, discarding everything after it.

```
/rewind
```

### `/copy`

Copy the most recent response to the clipboard. Pass a number to copy the Nth-latest response.

```
/copy
/copy 2
```

### `/export`

Export the current conversation to a file or the clipboard.

```
/export
```

### `/quit`

Quit the application.

```
/quit
```

Aliases: `/exit`

### `/home`

Exit the current session and return to the welcome screen.

```
/home
```

Aliases: `/welcome`

### `/rename`

Rename the current session.

```
/rename new session title
```

Aliases: `/title`

---

## Model and Mode

### `/model <name>`

Switch to a different model. Accepts model IDs or display names (case-insensitive). For reasoning models you can also pass an effort level as a second argument:

```
/model grok-build
/model Grok Build
/model Reasoning X high
```

Aliases: `/m`

### `/effort <level>`

Set reasoning effort on the **current** model without re-selecting it. Levels: `low`, `medium`, `high`, `xhigh`. Only works when the active model supports reasoning effort.

```
/effort high
/effort low
```

### `/always-approve`

Toggle always-approve mode, which skips all permission prompts for tool executions. Run `/always-approve` again to turn the mode off.

```
/always-approve
/yolo off
```

Related: `/yolo` sets the same mode explicitly -- a bare `/yolo` turns it on, and `/yolo off` turns it off.

### `/multiline`

Toggle multiline input mode. When enabled, `Enter` inserts a newline and `Shift+Enter` (or `Alt+Enter`) sends the message.

```
/multiline
```

Aliases: `/ml`

### `/compact-mode`

Toggle compact display mode. Reduces padding and visual spacing for denser output.

```
/compact-mode
```

### `/vim-mode`

Toggle vim-style scrollback keybindings (j/k, h/l, g/G, y/Y, …). When off
(default), bare-letter and `Shift+letter` keys in the scrollback focus the
prompt and type the character. Persists to `[ui].vim_mode` in `config.toml`.

```
/vim-mode
```

### `/plan`

Enter plan mode.

```
/plan [description]
```

### `/view-plan`

Open the current saved plan preview. Aliases: `/show-plan`, `/plan-view`.

```
/view-plan
```

---

## Memory

The `/flush`, `/dream`, and `/memory` commands require `--experimental-memory` or `GROK_MEMORY=1`. `/remember` is always available.

### `/memory`

Browse, view, and manage your saved memories. Pass `on` or `off` to enable or disable memory.

```
/memory
/memory off
```

Aliases: `/mem`

### `/flush`

Save current session knowledge to memory immediately. Triggers an LLM-generated summary of the session's most important content.

```
/flush
```

Use this when you want to preserve important context before compaction or at any point in a session.

### `/dream`

Run memory consolidation -- merge session logs into organized topics.

```
/dream
```

### `/remember`

Save a note to memory immediately, without waiting for an automatic summary.

```
/remember the staging deploy uses the eu-west cluster
```

---

## Hooks and Plugins

The `/hooks`, `/plugins`, `/marketplace`, and `/skills` commands open the same extensions modal on different tabs.

### `/hooks`

Open the extensions modal on the Hooks tab. From the modal you can view loaded hooks, add or remove custom hooks, and enable or disable them individually. The modal does not grant project trust -- see [10-hooks.md](10-hooks.md) for the trust model.

```
/hooks
```

**Note:** The shell advertises individual `/hooks-list`, `/hooks-trust`, `/hooks-add`, `/hooks-remove`,
and `/hooks-untrust` commands. In the TUI pager, these are consolidated into the `/hooks` modal.

### `/plugins`

Open the extensions modal on the Plugins tab. From the modal you can view installed plugins, install new ones from the marketplace, and manage trust.

```
/plugins
```

The shell also supports subcommands (`/plugins list`, `/plugins install <source>`,
`/plugins uninstall <name>`, `/plugins update`). In the TUI, the `/plugins` modal
provides the same functionality with a visual interface.

### `/marketplace`

Open the extensions modal on the Marketplace tab to browse and install plugins.

```
/marketplace
```

### `/skills`

Open the extensions modal on the Skills tab to view installed skills.

```
/skills
```

---

## Media Generation

### `/imagine <description>`

Generate an image from a text description.

```
/imagine a golden sunset over a calm ocean with silhouetted palm trees
```

### `/imagine-video <description>`

Generate a video from an image or text description. Plans shots, generates source images, and animates them with `image_to_video`.

```
/imagine-video a cat playing piano in a jazz club
```

---

## Scheduling

### `/loop [interval] <prompt>`

Run a prompt on a recurring interval. Specify the interval as `30m`, `1 hour`, or `every 2 days`. If you omit it, Grok prompts you.

```
/loop 30m check deploy status
/loop check deploy status every hour
```

Interval format: `Ns` (seconds, min 60), `Nm` (minutes), `Nh` (hours), `Nd` (days). Intervals under 60 seconds are raised to the 60-second minimum.

Recurring tasks auto-expire after 7 days. Cancel with `scheduler_delete` (the job ID is provided when the loop is created).

---

## Other

### `/goal`

Set, manage, or check an autonomous goal. Grok works toward the objective across turns and reports progress.

```
/goal Migrate the auth module to the new API
/goal status
```

Arguments: `<objective>`, `status`, `pause`, `resume`, or `clear`. **Availability:** appears only when the goal feature is enabled and the `update_goal` tool is in the session toolset.

### `/theme`

Switch the TUI color theme.

```
/theme
```

Aliases: `/t`

### `/feedback [message]`

Report an issue or send feedback.

```
/feedback Something isn't working correctly
```

### `/btw`

Send an aside to the agent without interrupting the current task.

```
/btw also check the error handling
```

### `/mcps`

Open the MCP servers management modal.

```
/mcps
```

### `/terminal-setup`

Show terminal capability detection and setup info.

```
/terminal-setup
```

Aliases: `/terminal-check`, `/terminal-info`

### `/release-notes`

View release notes for the current version.

```
/release-notes
```

Aliases: `/changelog`

### `/docs`

Browse in-TUI How-to Guides, open online Build docs, or jump to a guide by title.

```
/docs
/docs web
/docs Getting Started
```

- Bare `/docs` (or `/docs how-to`) opens the How-to Guides picker
- `/docs web` opens https://docs.x.ai/build/overview in the browser
- `/docs <title>` opens a specific guide (case-insensitive title match)

Aliases: `/howto`, `/guides`

### `/import-claude`

Open the Claude settings import modal to bring over `~/.claude` settings: permissions, environment variables, MCP servers, hooks, and paths.

```
/import-claude
```

---

## Agents and Personas

### `/config-agents`

Open the agents modal to view and manage agent definitions, set the default agent, and switch the active one.

```
/config-agents
```

Aliases: `/agents`

### `/personas`

Manage personas -- create, edit, and delete personas. A subagent can apply a persona to shape its behavior.

```
/personas
```

---

## Account and Billing

### `/login`

Log in or re-authenticate with your account without leaving the session.

```
/login
```

### `/logout`

Log out and return to the login screen.

```
/logout
```

### `/usage`

View credit usage or manage billing.

```
/usage
```

### `/privacy`

Show or toggle privacy and data-retention status.

```
/privacy
```

---

## Configuration and UI

### `/settings`

Open the settings modal to view and change configuration interactively.

```
/settings
```

Aliases: `/config`, `/preferences`, `/prefs`

### `/timestamps`

Toggle message timestamps on or off.

```
/timestamps
```

---

## Skills as Slash Commands

Any enabled skill with `user-invocable: true` in its SKILL.md frontmatter appears as a slash command. (A skill turned off via `/skills` is not advertised.) For example, if you have a skill at `~/.grok/skills/commit/SKILL.md`, you can invoke it with:

```
/commit fix typo in README
```

Skills from plugins also appear as slash commands. When multiple skills share the same name (across scopes), use the qualified form:

```
/local:commit      # Project-scoped skill
/user:commit       # User-scoped skill
```

Built-in slash commands always take priority over skills with the same name. If you name a skill "compact", typing `/compact` will run the built-in compact command, but `/local:compact` will invoke the skill.

---

## Autocomplete

The slash command menu supports fuzzy search. Start typing after `/` to filter available commands. The menu shows:

- Command name
- Description
- Argument hint (if the command accepts arguments)
- Source (builtin, skill scope, plugin name)

Press `Tab` or `Enter` to select a command from the autocomplete menu.

---

Copyright xAI. All rights reserved.
