---
name: images
description: Generate, QA and pick the guide's illustrations with the Higgsfield MCP (cover first, then every slot), recording everything in images.yaml.
argument-hint: <guide-id>
disable-model-invocation: true
---

# /images $ARGUMENTS

## 0. Is Higgsfield connected?
Check for `mcp__Higgsfield__*` tools. If they're missing:
1. Tell MYKO: `claude mcp add --transport http higgsfield https://mcp.higgsfield.ai/mcp`, then authenticate with `/mcp`.
2. Still run step 1 below so the prompts are ready in `images.yaml`.
3. Build with placeholder boxes (`guidekit build $ARGUMENTS`) and stop.

## 1. Slots and prompts
Every `image:` referenced by a page (cover `image:`, `timeline_step.image`, `image.slot`) needs a slot in `images.yaml`:
```yaml
- id: dead-hang
  scene: "a simple pull-up bar anchored in a bright home gym doorway"
  action: "hanging from the bar with straight arms, overhand grip, shoulders slightly engaged, feet off the floor"
  view: "Side view"
  checks: ["overhand grip", "bar anchored", "straight arms", "feet off the floor"]
```
- Illustrations only. Use the generic character from `guide.character`, never modelled on the creator's face. Keep the face small or turned away.
- Never use "every image", "series" or "set" in a prompt; they produced grids in v2. `guidekit images` rejects them.
- `checks` are the technique points that decide pass or fail for this slot.

Run `guidekit images $ARGUMENTS prompts`. This writes the final prompt into each slot using the proven v2 template and STYLE_LOCK.

## 2. Generate, in this order
1. **Cover, 3 variants**, with the cover prompt (no reference image).
2. Pick the cover (QA below). It becomes the **image reference for every other image**: upload it once and pass it as the reference.
3. **Every other slot, 2 variants**, using the reference.

Download each result and record the job in one step:
`guidekit images $ARGUMENTS fetch --slot <slot> --job <job-id> --url <result_url> --variant <n> --credits <n>`
This saves to `images/raw/<slot>-<n>.png`, which is gitignored. If the download host is blocked (sandboxed cloud sessions), record the job without a file (`job --slot … --job …`), tell MYKO, and build with placeholders.

Check the balance before starting and report credits used at the end.

## 3. QA every image (any fail → reject and regenerate)
1. `guidekit images $ARGUMENTS sheet --slot <slot>` builds a contact sheet of the batch. Read the JPG.
2. Crop hands and equipment for a close check: `guidekit images $ARGUMENTS crop --file <png> --box x,y,w,h` (fractions 0 to 1). Read the crop.
3. Pass only if all of these hold:
   - Technique is correct per the slot's `checks` (grip, anchoring, straight arms in hangs, band looped with a foot in the loop, …).
   - Correct hands, fingers and limbs: two arms, two hands, five fingers each.
   - No text, letters, numbers or logos.
   - Same character, outfit and palette as the cover.
   - One single image, not a grid or panels.
4. Record the verdict:
   - `guidekit images $ARGUMENTS reject --slot <slot> --job <id> --reason "<which check failed>"`
   - `guidekit images $ARGUMENTS pick --slot <slot> --job <id>` copies the file to `images/<slot>.png` and marks it picked.

## 4. Resolution
Build (`guidekit build $ARGUMENTS`). The QA flags `needs-upscale` when native width is under 1.5× the displayed width. Upscale only those slots, then re-pick.

Arrows and labels go in HTML/SVG overlays in the page YAML, never inside the image.

## Report
Per slot: picked job, rejects with reasons. Then total credits used and slots still pending.
