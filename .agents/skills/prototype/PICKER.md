# The Picker

The picker's appearance is **not a design decision** — it is this spec. Follow
it exactly; the only things that vary per run are the variant names and count.
It stays identical across every project so it always reads as harness chrome,
never as part of the design being judged. Do not restyle it with the project's
tokens, fonts, or colors.

It is a floating dark glass pill, bottom-center. Dark glass reads as chrome on
top of any page — light or dark — which is why it is not theme-aware.

## Using the shared picker module

If `/lib/variant-switcher.js` is available in the project root, use it:

```html
<div id="stage"></div>
<script src="/lib/variant-switcher.js"></script>
<script>
  VariantSwitcher.init({
    stage: document.getElementById('stage'),
    hasMotion: true,          // set false for static comparisons
    position: 'bottom',       // 'top' if variants use the bottom of the screen
    variants: [
      { name: 'Quiet',     render: () => `<div class="v-quiet">…</div>` },
      { name: 'Editorial', render: () => `<div class="v-editorial">…</div>` },
      { name: 'Playful',   render: () => `<div class="v-playful">…</div>` },
    ],
  });
</script>
```

`render()` returns an HTML string or DOM Node. It is called inside
`requestAnimationFrame` so entrance animations re-run on every mount and replay.

## Standalone HTML (no project)

When building a self-contained HTML file, embed the picker CSS and JS inline.
The exact markup, styles, and wiring follow.

### Markup

Sliding highlight span first, one button per variant, a hairline divider, then
the replay button (only when at least one variant has motion worth re-triggering):

```html
<nav class="proto-picker" aria-label="Prototype variants">
  <span class="proto-picker-hl" aria-hidden="true"></span>
  <button class="proto-picker-btn" data-active aria-current="true">Quiet</button>
  <button class="proto-picker-btn">Editorial</button>
  <button class="proto-picker-btn">Playful</button>
  <span class="proto-picker-divider" aria-hidden="true"></span>
  <button class="proto-picker-btn proto-picker-replay" aria-label="Replay animation (R)">↻</button>
</nav>
```

### Styles

```css
.proto-picker {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 2147483647;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px;
  border-radius: 999px;
  background: rgba(10, 10, 10, 0.82);
  -webkit-backdrop-filter: blur(12px) saturate(1.4);
  backdrop-filter: blur(12px) saturate(1.4);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.08) inset,
    0 8px 24px rgba(0, 0, 0, 0.24),
    0 2px  6px rgba(0, 0, 0, 0.12);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 13px;
  line-height: 1;
  -webkit-font-smoothing: antialiased;
  user-select: none;
  -webkit-user-select: none;
}

.proto-picker-hl {
  position: absolute;
  top: 4px;
  left: 0;
  height: 28px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
  will-change: transform;
}

/* Slide enabled only after first paint so load doesn't animate. */
.proto-picker[data-ready] .proto-picker-hl {
  transition:
    transform 250ms cubic-bezier(0.23, 1, 0.32, 1),
    width     250ms cubic-bezier(0.23, 1, 0.32, 1);
}

@media (prefers-reduced-motion: reduce) {
  .proto-picker[data-ready] .proto-picker-hl { transition: none; }
}

.proto-picker-btn {
  position: relative;
  display: flex;
  align-items: center;
  height: 28px;
  padding: 0 12px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: rgba(255, 255, 255, 0.55);
  font: inherit;
  cursor: pointer;
  transition: color 150ms ease-out;
}
.proto-picker-btn:hover         { color: rgba(255, 255, 255, 0.85); }
.proto-picker-btn:active        { transform: scale(0.97); }
.proto-picker-btn:focus-visible { outline: 2px solid rgba(255,255,255,.4); outline-offset: 2px; }
.proto-picker-btn[data-active]  { color: #fff; }

.proto-picker-divider {
  width: 1px;
  height: 16px;
  margin: 0 4px;
  background: rgba(255, 255, 255, 0.12);
}
.proto-picker-replay { padding: 0 10px; font-size: 14px; }

.proto-picker[data-pos="top"] { bottom: auto; top: 24px; }
```

### Wiring (standalone JS)

```js
// `variants` — array of { name, render } in picker order.
// `render()` returns an HTML string.
// `stage` — the element where variants are mounted.
// `hasMotion` — whether to show the replay button.

const stage = document.getElementById('stage');
const picker = document.querySelector('.proto-picker');
const hl = picker.querySelector('.proto-picker-hl');
const btns = [...picker.querySelectorAll('.proto-picker-btn:not(.proto-picker-replay)')];
const replayBtn = picker.querySelector('.proto-picker-replay');
let current = 0;

function slide() {
  const el = btns[current];
  hl.style.width = el.offsetWidth + 'px';
  hl.style.transform = `translateX(${el.offsetLeft}px)`;
}

function mount(i) {
  stage.innerHTML = '';
  requestAnimationFrame(() => { stage.innerHTML = variants[i].render(); });
}

function activate(i) {
  if (i < 0 || i >= variants.length) return;
  current = i;
  btns.forEach((b, j) => {
    b.toggleAttribute('data-active', j === i);
    b.setAttribute('aria-current', j === i ? 'true' : 'false');
  });
  slide();
  const url = new URL(location.href);
  url.searchParams.set('v', i + 1);
  history.replaceState(null, '', url);
  mount(i);
}

btns.forEach((b, i) => b.addEventListener('click', () => activate(i)));
replayBtn?.addEventListener('click', () => mount(current));
window.addEventListener('resize', slide);

document.addEventListener('keydown', e => {
  if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable) return;
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const n = parseInt(e.key, 10);
  if (n >= 1 && n <= variants.length) { activate(n - 1); return; }
  if (e.key === 'ArrowRight') { activate((current + 1) % variants.length); return; }
  if (e.key === 'ArrowLeft')  { activate((current - 1 + variants.length) % variants.length); return; }
  if ((e.key === 'r' || e.key === 'R') && hasMotion) mount(current);
});

// Init from URL param; enable slide after first paint.
const startIdx = Math.min(
  Math.max((parseInt(new URLSearchParams(location.search).get('v'), 10) || 1) - 1, 0),
  variants.length - 1
);
activate(startIdx);
requestAnimationFrame(() => requestAnimationFrame(() => picker.setAttribute('data-ready', '')));
```

## Rules

- **Verbatim.** No project fonts, brand colors, theme switching, or extra decoration.
- **The highlight slides; the variant swap is instant.** The active pill animates
  between buttons (250ms, strong ease-out) as spatial feedback on the picker
  itself. The content switches with no transition.
- **One allowed modification:** if a variant occupies the bottom-center of the
  screen (a toast stack, bottom sheet, dock), add `data-pos="top"` to `.proto-picker`
  so the picker never covers the work. Nothing else moves or changes.
- **Replay is conditional.** Render the replay button and its divider only when
  at least one variant has an entrance or state animation worth re-triggering.
  A static comparison gets a shorter pill without the divider or replay button.

## Behavior contract

- `1`–`N` and `←`/`→` switch variants; `R` replays. Key events ignored when
  focus is in a form element or when a modifier is held.
- Exactly one button carries `data-active` and `aria-current="true"` at all
  times; the highlight slides to it.
- Selection persists across reload via `?v=N` (1-indexed); falls back to
  variant 1.
- Switching re-mounts the variant (entrance animations re-run). Replay re-mounts
  without switching.
