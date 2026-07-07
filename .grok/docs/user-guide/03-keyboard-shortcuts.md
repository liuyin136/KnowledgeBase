# Keyboard Shortcuts

Reference for key bindings in the Grok Build TUI. Bindings are built in and cannot currently be remapped.

---

## Input Modes

Grok has two input modes that control how you navigate the scrollback:

- **Simple mode** (default): Arrow keys for navigation, `Shift+Arrow` for turn navigation, `Space` to focus the prompt, and any letter key auto-focuses the prompt.
- **Vim mode** (opt-in): `j`/`k` for navigation, `H`/`L` for turn navigation, `J`/`K` for response navigation, `h`/`l` for fold, `e`/`E` for expand/collapse, and `i`/`Tab`/`Space` to focus the prompt.

Simple mode is active by default. To switch to Vim mode, set `vim_mode = true` under `[ui]` in `~/.grok/config.toml`, or toggle it at runtime with `/vim-mode`. See [Configuration](05-configuration.md) for details.

The tables below document bindings for both modes. The "Key" column shows the Vim-mode binding, and the "Alt Key" column shows the equivalent in simple mode (arrow keys, etc.).

> **Vim-mode required**: Single-letter and `Shift+letter` bindings in the
> **Scrollback** context (`j/k`, `h/l`, `g/G`, `L/H`, `y/Y`, `o/O`, `r`,
> `x`, `e/E`, and the `i` insert-mode alt) require `[ui].vim_mode = true`
> in `~/.grok/config.toml` (or `/vim-mode` to toggle). Arrow keys, `Tab`,
> `Esc`, `Space`, `PageUp/Down`, and every `Ctrl+letter` shortcut work in
> both modes.

---

## Navigation (Scrollback Focused)

Move through conversation entries in the scrollback pane.

| Key | Alt Key | Action |
|-----|---------|--------|
| `j` | `Down` | Select next entry |
| `k` | `Up` | Select previous entry |
| `⇧L` | `Shift+Right` | Jump to next turn (user prompt) |
| `⇧H` | `Shift+Left` | Jump to previous turn (user prompt) |
| `⇧J` | | Jump to next assistant response |
| `⇧K` | | Jump to previous assistant response |
| `g` | | Go to top of scrollback |
| `⇧G` | | Go to bottom of scrollback |
| `Ctrl+K` | | Scroll up one line (without changing selection) |
| `Ctrl+J` | | Scroll down one line (without changing selection) |
| `PageUp` | | Scroll up one page |
| `PageDown` | | Scroll down one page |
| `Ctrl+U` | | Scroll up half page |
| `Ctrl+D` (`Shift+D` in VSCode) | | Scroll down half page |

---

## View (Scrollback Focused)

Control how entries are displayed in the scrollback.

| Key | Alt Key | Action |
|-----|---------|--------|
| `h` | `Left` | Collapse selected entry |
| `l` | `Right` | Expand selected entry |
| `e` | | Toggle fold on selected entry |
| `⇧E` | | Expand all / collapse all entries |
| `Ctrl+E` | | Expand/collapse all thinking blocks |
| `r` | | Toggle raw markdown on selected entry |

Setting `respect_manual_folds = true` under `[scrollback.scroll]` in
`pager.toml` (opt-in, off by default — see
[Configuration](05-configuration.md)) makes a hand-folded block pinned:
streaming updates and finish events (for example a thinking block ending)
leave it alone instead of resetting it, and expanding a block while
auto-scroll is following the tail stops following so you can read; resume
with `⇧G`, `j` at the last entry, scrolling past the bottom, or sending a new
prompt. `⇧E` clears all pins, and `Ctrl+E` clears pins on thinking blocks.

### Block Content

| Key | Action |
|-----|--------|
| `y` | Copy block content to clipboard |
| `⇧Y` | Copy block metadata (e.g., the shell command) to clipboard |
| `Enter` | Open block content in fullscreen viewer |
| `Ctrl+F` | Open block content in fullscreen viewer (alt binding) |

---

## Focus

Switch between the prompt input and scrollback pane.

| Key | Alt Key | Context | Action |
|-----|---------|---------|--------|
| `Tab` | `Space` (and `i` in vim mode) | Scrollback focused | Focus the prompt input |
| `Tab` | | Prompt focused | Focus the scrollback (both simple and vim scrollback modes) |
| `Enter` | | Prompt focused | Send the current prompt |

**Esc is not a focus key.** It follows cancel / clear / rewind semantics below, independent of `[ui].simple_mode` (prompt editor) and `[ui].vim_mode` (scrollback nav). Overlays, modals, slash/file dropdowns, voice, search, and selection still steal Esc first.

## Escape

| State | Gesture | Effect |
|--------|---------|--------|
| Turn running or cancelling | **1× `Esc`** | Cancel the turn immediately (`cancelTrigger: esc`), from prompt or scrollback, even with a non-empty draft. No second-press confirm. Pre-stream cancel may restore the prompt when cancel-rewind is enabled. |
| Idle + non-empty prompt (text or image chips), **prompt focused** | **2× `Esc` within 800ms** | Clear the prompt; non-empty text is saved to prompt history. First press shows “press again to clear”. |
| Idle + empty prompt + conversation messages, **prompt focused** | **2× `Esc` within 800ms** | Open the rewind picker (same as `/rewind`). First press is silent (no toast). |
| Idle + empty + no messages, **or scrollback focused** | `Esc` | Swallowed no-op (does not focus scrollback). Clear / rewind are prompt-pane only, so reading the scrollback never mutates your draft. |

**Steal-Esc (runs before cancel/clear/rewind):** overlays, modals, slash/file/completion dropdowns, history search, scrollback search, text selection, link highlight, voice, and **Bash / Remember / Feedback mode exit** when the prompt is empty (Esc leaves `!` / `#` / feedback mode and returns to the normal prompt — even while a turn is running, so you must exit the special mode or type a draft before Esc cancels).

**Ctrl+C is unchanged and asymmetric with Esc:** with a non-empty draft while a turn is running, Ctrl+C clears the draft and keeps the turn; Esc cancels the turn. Idle non-empty Ctrl+C clears in one press; Esc requires two presses within 800ms.

---

## Agent-Level

Actions that affect the agent session, available from the agent screen.

| Key | Context | Action |
|-----|---------|--------|
| `Ctrl+P` | Agent screen | Open the command palette |
| `?` (Shift+/) | Agent screen | Open the command palette (alt binding) |
| `Ctrl+M` | Agent screen | Open the model picker / switch model |
| `Ctrl+M` | Prompt focused | Toggle multiline input mode |
| `Ctrl+C` | Agent screen | Cancel the current turn (or clear non-empty draft first; see Escape table) |
| `Esc` | Prompt or scrollback focused (turn running) | Cancel the current turn immediately (see Escape table). From Todo/Queue/Tasks/Catalog panes, use `Ctrl+C`. |
| `Ctrl+O` | Agent screen | Toggle always-approve (YOLO) mode |
| `Ctrl+S` | Agent screen | Open the session picker (resume a previous session) |
| `Ctrl+;` (alt: `Ctrl+'`) | Agent screen | Toggle the prompt queue pane (when non-empty). **Local macOS** VS Code family only: primary **`Ctrl+4`** (`;` / `'` still alts). SSH and non-Mac keep **`Ctrl+;`** / **`Ctrl+'`**. |
| `Shift+Tab` | Prompt focused | Cycle mode (Normal → Plan → Always-approve) |
| `Ctrl+G` | Agent screen | Send the current task to the background |
| `Ctrl+T` | Agent screen | Toggle the todos pane |
| `Ctrl+B` | Agent screen | Toggle the tasks pane |
| `Ctrl+L` | Agent screen | Open the extensions modal (**non–VS Code family only**; on VS Code / Cursor / Windsurf / Zed, `Ctrl+L` is mid-turn **interject** and extensions open via `/plugins` / `/hooks`) |
| `Ctrl+R` | Prompt focused | Search prompt history |
| `!` | Prompt focused | Enter shell mode (type `!` on an empty prompt) |
| `Ctrl+.` (alt: `Ctrl+X`) | Agent screen | Open the keyboard shortcuts help |
| `F2` (alt: `Ctrl+,` / `Cmd+,`) | Agent screen | Open the settings modal |

**Note:** `Ctrl+M` is context-dependent. When the prompt is focused, it toggles multiline input mode. Otherwise, it opens the model picker.

**Note:** `Ctrl+'` is a Windows alt for `Ctrl+;` — some Windows consoles drop the `Ctrl` modifier on punctuation keys.

**Note:** `Ctrl+.` needs the Kitty keyboard protocol (or tmux `extended-keys on` so that protocol can pass through). On VS Code / Cursor / Windsurf / Zed integrated terminals, VTE, Apple Terminal, Windows Terminal, JetBrains, tmux with `extended-keys off`, screen, and similar no-KKP setups, Grok advertises **`Ctrl+X`** as the primary shortcuts-cheatsheet key instead. **`Ctrl+X` always works** as a classic control character even when `Ctrl+.` does not. Run `/terminal-setup` if modified keys misbehave in tmux.

---

## Image Paste & Drag-and-Drop

| Action | macOS | Linux | Windows |
|---|---|---|---|
| Drag image from file manager into the prompt | Finder ✓ | Files / Dolphin ✓ | Explorer ✓ |
| Copy a file in the file manager, then paste | `Cmd+V` | `Ctrl+V` | `Ctrl+V` |
| Screenshot or "Copy Image" in clipboard, then paste | `Cmd+V` | `Ctrl+V` | **`Alt+V`** |

Non-image files insert their absolute path as text instead of a chip.

> **`Alt+V` on Windows** is grok-specific. Windows Terminal's default `Ctrl+V` only pastes plain text and silently drops image clipboards; `Alt+V` bypasses the interceptor. To use `Ctrl+V` for images too, add `{ "command": null, "keys": "ctrl+v" }` to `actions` in your Windows Terminal `settings.json`.

---

## During an active turn (agent running)

While the agent is generating:

- **Plain `Enter`** (with text in the composer) **queues** a follow-up for later — it does not inject into the current turn.
- The **send now** chord (interject under the hood) merges into the **current** turn without cancelling it:
  - **Non-empty composer** → inject that text now.
  - **Empty composer** + a queued follow-up → force-send the **top** queued follow-up (the next one that would drain) from the prompt (no need to focus the queue pane). On the queue pane, the same chord (or the **[Send now]** button) force-sends the **selected** row.
  - **Idle**, or **empty composer with nothing queued** → no-op for that key.

| Terminal | Primary | Alternates | Action |
|----------|---------|------------|--------|
| Default | `Ctrl+Enter` | `Ctrl+I` | Send now (continues the current turn) |
| Apple Terminal | `Ctrl+O` | `Ctrl+Enter`, `Ctrl+I` | Send now |
| VS Code family (VS Code, Cursor, Windsurf, Zed) | **`Ctrl+L`** | *(none)* | Send now (`Ctrl+I` not used — Tab / host chat; plugins via `/plugins`) |

In `/multiline` mode, `Shift+Enter` (or `Alt+Enter`) sends while plain `Enter` inserts a newline. (`Ctrl+Enter` is send-now mid-turn when bound on non–VS Code family; it does not submit a new idle turn.)

> **WezTerm**: These modified Enter keys need `enable_kitty_keyboard = true` in your WezTerm config. Full steps and a one-line workaround are in the [terminal support guide](21-terminal-support.md#problem-ctrlenter-doesnt-interject-in-wezterm).

> **Windows (non–VS Code family)**: Some consoles drop the `Ctrl` modifier on `Ctrl+Enter` (it can collapse to bare `Enter` or `Ctrl+J`). Use `Ctrl+I` as the alt — letter-key Ctrl chords are stable everywhere. On VS Code family, use **`Ctrl+L`**.

> **VS Code family `Ctrl+L`**: Grok uses it for interject and leaves the extensions shortcut unbound (open plugins with `/plugins` or the command palette). If your terminal profile still maps **Clear** (or another command) to `Ctrl+L`, that host binding can steal the chord — rebind or remove it so the PTY receives form feed (`\x0c`).

---

## Global

Actions available from any screen.

| Key | Alt Key | Action | Confirmation |
|-----|---------|--------|-------------|
| `Ctrl+N` | | Create a new session (optionally in a git worktree) | Yes (double-press within 1000ms) |
| `Ctrl+Q` | `Ctrl+D` | Quit the application | Yes (double-press within 1000ms) |

**VS Code family terminal** (VS Code, Cursor, Windsurf, Zed integrated terminals): `Ctrl+Q` is captured by the host, so Grok makes **`Ctrl+D` the sole quit key** (`Ctrl+Q` is not bound). Half-page-down is rebound to bare **`Shift+D`**. Mid-turn interject uses **`Ctrl+L`** (no alternates) because `Ctrl+Enter` / `Ctrl+I` do not reliably reach the PTY; extensions are opened via `/plugins` instead of `Ctrl+L`.

> **Returning to the welcome screen has no key binding** — use the `/home` slash command (alias `/welcome`) from inside a session. See [Slash Commands](04-slash-commands.md).

### Destructive Action Confirmation

Actions marked with "Yes" in the confirmation column require a double-press within 1000ms. Press the key once to see a confirmation prompt, then press again to confirm. This prevents accidental session loss.

---

## Welcome Screen

Bindings that only fire on the welcome screen (before any agent session is open).

| Key | Action |
|-----|--------|
| `Ctrl+S` | Resume session (open the session picker) |
| `Ctrl+W` | Open the New Worktree dialog (only inside a git repository) |
| `Ctrl+I` | Import Claude settings (when available) |
| `Ctrl+Shift+I` | Dismiss the Claude import row (when available) |

`Ctrl+W`, `Ctrl+I`, and `Ctrl+Shift+I` are only active on the welcome screen. `Ctrl+S` opens the session picker on both the welcome screen and inside an agent session (where it opens as a modal overlay, same as the `/resume` command). `Ctrl+Q` is the same global Quit binding documented above, not a welcome-specific handler.

---

## Command Palette

Press `Ctrl+P` or `?` to open the command palette -- a searchable list of actions. The palette shows:

- All keyboard shortcuts with their current bindings
- All slash commands
- Available skills

Type to filter, then press `Enter` to execute the selected action.

---

## Shortcuts Bar

The bottom of the TUI displays a contextual shortcuts bar showing the most relevant key bindings for the current state. The hints change based on:

- Which pane is focused (scrollback vs. prompt)
- Whether the agent is currently running
- What type of entry is selected

---

## Mouse Support

The TUI supports mouse interaction:

- **Click** on a scrollback entry to select it
- **Scroll wheel** to scroll through the scrollback
- **Click** on the prompt area to focus it
- **Hover** over the prompt to see a highlight (configurable via `pager.toml`)

---

## Quick Reference Card

### When scrollback is focused (Simple mode — default)

```
Navigation:       Up/Down (prev/next entry)  Shift+Left/Right (prev/next turn)
Scrolling:        Ctrl+J/K (line)  PgUp/PgDn (page)  Ctrl+U/D (half page)
Focus prompt:     Space or any letter key (auto-focuses and types)
```

### When scrollback is focused (Vim mode)

```
Navigation:       j/k (up/down)  H/L (prev/next turn)  K/J (prev/next response)  g/G (top/bottom)
Scrolling:        Ctrl+J/K (line)  Ctrl+U/D (half page; D=Shift+D in VSCode)  PgUp/PgDn (page)
Folding:          h/l (collapse/expand)  e (toggle)  E (all)
Content:          y (copy)  Y (copy cmd)  Enter (fullscreen)
View:             r (raw markdown)  Ctrl+E (thinking)
Focus prompt:     i, Tab, or Space
```

### When prompt is focused

```
Send:             Enter
Newline:          Shift+Enter or Alt+Enter
Multiline:        Ctrl+M (toggle)
Paste:            Ctrl+V (text, files, screenshots on macOS/Linux)
Paste image:      Alt+V (Windows only — for screenshots / "Copy Image")
Select all:       Cmd+A (macOS, Ghostty only — see note below)
Leave:            Tab (back to scrollback)
Cancel (running): Esc (immediate; keeps draft, cancels turn)
Clear (idle):     Esc Esc within 800ms (non-empty prompt)
Rewind (idle):    Esc Esc within 800ms (empty prompt + messages)
```

> **Cmd+A is gated to Ghostty.** Grok's in-app `Cmd+A` handler is only
> wired up when the detected terminal is Ghostty. Other terminals
> either swallow `Cmd+A` at the terminal layer (Apple Terminal, default
> iTerm2) or apply their own in-terminal "Select All" behaviour (Kitty,
> WezTerm). On a non-Ghostty terminal, the binding does nothing and the
> key falls through to the terminal's native behaviour.
>
> On Ghostty, add the one-line unbind to `~/.config/ghostty/config` so
> the keystroke reaches the running TUI:
>
> ```ini
> keybind = cmd+a=unbind
> ```
>
> After Ghostty reloads (it watches the config file), `Cmd+A` in the
> prompt selects every character in the prompt buffer, including pasted
> image chips. Image chip placeholders carry the file path
> (`[Image #N: /path/to/file]`), so cutting the selection with `Ctrl+X`
> after `Cmd+A` preserves the path through the system clipboard.

### Always available

```
Command palette:  Ctrl+P or ?
Model picker:     Ctrl+M (from scrollback)
Cancel:           Esc (while turn running) or Ctrl+C (see Escape table)
Always-approve:   Ctrl+O (toggle YOLO)
New session:      Ctrl+N (press again, then choose normal/worktree)
Quit:             Ctrl+Q (or Ctrl+D in VSCode)
```

---

Copyright xAI. All rights reserved.
