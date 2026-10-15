# Independent shared-host recovery and Windows access

On 15 October, the original shared workspace's saved tunnel returned the
provider's offline-host error. The existing provider computer controls restored
access without an agent message, model quota or a new credential. The Windows
client's protected administrator profile then authenticated independently.

The existing operator channel remains necessary to wake that remote computer.
This exercise does not implement the product-managed host directory or delegated
recovery requested under A06 and A12.

## Guarded server upgrade

The reviewed operator bridge planned and applied **4.3.2 → 4.4.0**, pinned to
published source `8d5995989a3ecbc5c9ec25e04553fcca90fdd5d1`. Its plan contained
no additional database migrations and required matching model generations and a
verified backup before changing processes. The apply receipt reported success,
no pending recovery and unchanged connector configuration. No database backup
was restored over the live database.

Fresh installed-runtime inspection reported the API, worker and updater running,
service and supervisor readiness true, and automatic updates enabled. The
enrolled connector retained its earlier launcher and executed its scan using
the newly active **4.4.0** runtime; the observation caught that scan in progress.
It is not a completed-scan or provider-delivery acceptance claim.

The public desktop distribution advanced to 4.6.0 during this work. The shared
server remains on the separately reviewed 4.4.0 target. The patch-only updater
policy on that host still needs one operator upgrade to the compatible-minor
policy introduced in the 4.7.1 source.

## Actual Windows read-only comparison

The installed Windows credential helper opened the existing protected human
profile. Fresh identity and workspace observations retained the same principal,
tenant and administrator access. The profile was unchanged after the exercise.
No access grants or model configuration were modified.

Three reported queries each compared the default ranking policy with pure
relevance at the same reference time on **4.4.0**. All six recall requests
completed, returning 30 candidates each. Together with identity, accessible-space
and OAuth-configuration reads, this was **nine read-only requests**, **zero memory
writes** and **zero cloud-model calls**. An operator-side model attestation
confirmed the installed local CPU multilingual E5 profile; the guarded upgrade
preserved its generation.

For the two task-identifier cases, the default policy changed the top candidate
and shared three of the top five results with pure relevance. The prose case
remained classified as semantic-only and retained the same top candidate. The
six service-reported query times ranged from **4.85 to 7.40 seconds**. These are
single sequential observations on the actual host, not a saturation benchmark,
answer-correctness score or a controlled before/after version comparison.

Private receipts retain the case details and operator observations without
publishing memory content, personal paths, host addresses or credentials.
Retrieval quality and recency issues remain open pending content-level acceptance.
The host's MCP endpoint is enabled, but hosted OAuth is disabled; this does not
prove a completed hosted-agent sign-in or native provider integration.
