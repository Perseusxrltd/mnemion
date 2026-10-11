# Live memory map

From **4.0.10**, use **Memory map & wiki → Live memory map**. It is part of the same Studio frontend in the
browser and desktop app. Published 4.0.9 still has the earlier evidence graph.

Use the map to follow subjects and ideas into actual memories and their sources.
It reads the existing permission-filtered knowledge API. It does not send your
memory to a visualization service or require a GPU, model download or paid API.
The desktop remains a client of the selected workspace; the browser view is
available at that workspace's Studio address when its host is reachable.

## Explore and inspect

- **Orbit:** drag the 3D canvas, or focus it and use the arrow keys. Use the
  plus/minus buttons or keyboard `+` / `-` to zoom; `0` resets the camera.
- **Expand map:** enter a full-screen view where supported. Use **Exit full
  screen** or the browser/OS escape control to return.
- **2D:** flatten the view. Reduced-motion preferences select this mode initially.
- **Find a connection:** match words in node labels and include their direct
  recorded connections. **Show** selects a node type.
- **Created by:** filter the original creator. Where organization administrator
  access permits directory lookup, show the person/app name and kind; otherwise
  show the creator's abbreviated identity ID. This does not claim that the
  original creator made every subsequent edit.
- **Changed:** filter the included memories by their recorded update time.
- **Select a point:** inspect review status, revision, current evidence and
  links to memory history and original sources. **Focus connections** narrows
  to that point and its immediate neighborhood.
- **Browse connections as a list:** select the same visible nodes with a
  keyboard, screen reader or browser without canvas support.

**Scope, subject & history** controls the server-side selection: current space
or all accessible spaces, a literal subject filter and optional historical
claims. The wiki, earlier column-based evidence graph, curation suggestions,
Markdown download and Obsidian workflows remain available.

## What a connection means

| Point or line | Meaning |
| --- | --- |
| Gold space | A space you can access. |
| Blue subject/idea | A recorded subject or explicit entity metadata. |
| Green memory | A currently included memory revision. |
| Violet source | The source revision cited by a memory. |
| `about` | The memory explicitly names that subject or entity. |
| `cites` | The memory cites that source revision. |
| `in_space` | The memory belongs to that space. |

The 3D positions are a stable visual arrangement, not similarity, confidence or
truth scores. Nearby points need not be related; only displayed edges indicate
recorded relationships. No decorative particle is presented as a memory or live
agent action. Labels avoid overlapping; the node list retains labels omitted
from the canvas for readability. Identical names in different spaces remain
separate identities and subjects.

## Live changes and agent activity

Visible maps check for a new authorized snapshot every **20 seconds**. Hidden
tabs do not poll in the background. **Pause live updates** stops periodic
knowledge/activity checks; **Refresh** explicitly checks again. This first
implementation uses bounded snapshots, not a sub-second event stream.

**Work behind the map** shows real creation, revision and review events for
visible memories in the currently selected space. It requires reviewer access
and considers the latest 40 activity events, showing up to eight matching
changes. No matching event in that window does not prove that no work happened.
Use the memory history and Activity screen for further investigation. A person
or application can perform a recorded action; the app does not infer model
reasoning or fabricate an explanation for it.

Deleted, quarantined or inaccessible memories cannot be reintroduced through a
stale selected node. The graph is removed if refreshing its authorization fails.
A paused view is a previously authorized snapshot; refresh to recheck its access.

## Resource and bandwidth limits

Choose **Compact** (60 memories, at most 120 nodes), **Balanced** (120 memories,
at most 300 nodes), or **Detailed** (250 memories, at most 600 nodes). Hardware
hints select Compact initially on smaller computers. This is the view's record
budget, separate from the local engine's RAM policy. Rendering stops when idle;
the map has no permanent animation loop. Pixel density is bounded at 1.5×.

Truncation is visible. A node/edge omitted by the current filter or budget is not
evidence that the relationship does not exist. A live refresh still transfers a
knowledge snapshot; pause or use Compact on limited connections. Read-only map
filters do not count as unsaved memory drafts for desktop update safety. Actual
unsaved drafts continue to block unattended restarts.

## Remaining work

Large-workspace clustering, incremental/delta subscriptions, time replay,
multi-space activity aggregation, richer permission-filtered collaborator labels
and provider-specific capture coverage remain on the
[requirements checklist](../PRODUCT_REQUIREMENTS.md), V03–V05 and C08. This view
does not make an offline workspace host reachable; use the
[connection and recovery guide](connection-diagnostics.md) for that.
