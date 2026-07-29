/**
 * variant-switcher.js — prototype picker harness
 *
 * A floating bottom-center pill that lets you flip between named UI variants
 * during agent-assisted prototyping. Selection persists in the URL (?v=N) so
 * any variant is shareable as a link.
 *
 * Usage (standalone HTML):
 *
 *   const stage = document.getElementById('stage');
 *
 *   VariantSwitcher.init({
 *     stage,                      // required: element where variants render
 *     hasMotion: true,            // show replay button (default false)
 *     position: 'bottom',         // 'bottom' | 'top'  (default 'bottom')
 *     variants: [
 *       {
 *         name: 'Quiet',
 *         render: () => `<div class="card quiet">...</div>`,
 *       },
 *       {
 *         name: 'Editorial',
 *         render: () => `<div class="card editorial">...</div>`,
 *       },
 *       {
 *         name: 'Playful',
 *         render: () => `<div class="card playful">...</div>`,
 *       },
 *     ],
 *   });
 *
 * Keyboard:
 *   1–N   → jump to variant N
 *   ←/→   → step through variants
 *   R     → replay current variant (re-mounts, re-runs entrance animations)
 *
 * URL: selection is written as ?v=1, ?v=2, … (1-indexed). Paste the URL
 * to send a colleague directly to the right variant.
 */

const VariantSwitcher = (() => {

  /* ---------- CSS --------------------------------------------------------- */
  const CSS = `
.vsp {
  position: fixed;
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
    0 0 0 1px rgba(255,255,255,.08) inset,
    0 8px 24px rgba(0,0,0,.24),
    0 2px  6px rgba(0,0,0,.12);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 13px;
  line-height: 1;
  -webkit-font-smoothing: antialiased;
  user-select: none;
  -webkit-user-select: none;
}
.vsp[data-pos="bottom"] { bottom: 24px; top: auto; }
.vsp[data-pos="top"]    { top: 24px;    bottom: auto; }

.vsp-hl {
  position: absolute;
  top: 4px;
  left: 0;
  height: 28px;
  border-radius: 999px;
  background: rgba(255,255,255,.12);
  will-change: transform;
}
.vsp[data-ready] .vsp-hl {
  transition:
    transform 250ms cubic-bezier(.23,1,.32,1),
    width     250ms cubic-bezier(.23,1,.32,1);
}
@media (prefers-reduced-motion: reduce) {
  .vsp[data-ready] .vsp-hl { transition: none; }
}

.vsp-btn {
  position: relative;
  display: flex;
  align-items: center;
  height: 28px;
  padding: 0 12px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: rgba(255,255,255,.55);
  font: inherit;
  cursor: pointer;
  transition: color 150ms ease-out;
}
.vsp-btn:hover            { color: rgba(255,255,255,.85); }
.vsp-btn:active           { transform: scale(.97); }
.vsp-btn:focus-visible    { outline: 2px solid rgba(255,255,255,.4); outline-offset: 2px; }
.vsp-btn[data-active]     { color: #fff; }

.vsp-divider {
  width: 1px;
  height: 16px;
  margin: 0 4px;
  background: rgba(255,255,255,.12);
}
.vsp-replay { padding: 0 10px; font-size: 14px; }
`;

  /* ---------- helpers ------------------------------------------------------ */
  function injectStyles() {
    if (document.getElementById('vsp-styles')) return;
    const el = document.createElement('style');
    el.id = 'vsp-styles';
    el.textContent = CSS;
    document.head.appendChild(el);
  }

  function readParam() {
    const v = parseInt(new URLSearchParams(location.search).get('v'), 10);
    return Number.isFinite(v) ? v - 1 : 0;          // 0-indexed internally
  }

  function writeParam(index) {
    const url = new URL(location.href);
    url.searchParams.set('v', index + 1);
    history.replaceState(null, '', url.toString());
  }

  /* ---------- init --------------------------------------------------------- */
  function init({ stage, variants, hasMotion = false, position = 'bottom' }) {
    if (!stage || !variants || !variants.length) {
      console.warn('[VariantSwitcher] `stage` element and at least one variant are required.');
      return;
    }

    injectStyles();

    /* --- build picker DOM --- */
    const nav = document.createElement('nav');
    nav.className = 'vsp';
    nav.setAttribute('aria-label', 'Prototype variants');
    nav.dataset.pos = position;

    const hl = document.createElement('span');
    hl.className = 'vsp-hl';
    hl.setAttribute('aria-hidden', 'true');
    nav.appendChild(hl);

    const btns = variants.map(({ name }, i) => {
      const btn = document.createElement('button');
      btn.className = 'vsp-btn';
      btn.textContent = name;
      btn.addEventListener('click', () => setActive(i));
      nav.appendChild(btn);
      return btn;
    });

    let replayBtn = null;
    if (hasMotion) {
      const divider = document.createElement('span');
      divider.className = 'vsp-divider';
      divider.setAttribute('aria-hidden', 'true');
      nav.appendChild(divider);

      replayBtn = document.createElement('button');
      replayBtn.className = 'vsp-btn vsp-replay';
      replayBtn.setAttribute('aria-label', 'Replay animation (R)');
      replayBtn.textContent = '↻';
      replayBtn.addEventListener('click', () => mount(current));
      nav.appendChild(replayBtn);
    }

    document.body.appendChild(nav);

    /* --- sliding highlight --- */
    function moveHighlight() {
      const el = btns[current];
      hl.style.width = el.offsetWidth + 'px';
      hl.style.transform = `translateX(${el.offsetLeft}px)`;
    }
    window.addEventListener('resize', moveHighlight);

    /* --- mount (re-runs entrance animations) --- */
    let current = 0;
    function mount(i) {
      stage.innerHTML = '';
      requestAnimationFrame(() => {
        const result = variants[i].render();
        if (typeof result === 'string') {
          stage.innerHTML = result;
        } else if (result instanceof Node) {
          stage.appendChild(result);
        }
      });
    }

    /* --- switch variant --- */
    function setActive(i) {
      if (i < 0 || i >= variants.length) return;
      current = i;
      btns.forEach((btn, j) => {
        const active = j === i;
        btn.toggleAttribute('data-active', active);
        btn.setAttribute('aria-current', active ? 'true' : 'false');
      });
      moveHighlight();
      writeParam(i);
      mount(i);
    }

    /* --- keyboard --- */
    document.addEventListener('keydown', e => {
      const tag = e.target.tagName;
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(tag) || e.target.isContentEditable) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      const num = parseInt(e.key, 10);
      if (num >= 1 && num <= variants.length) { setActive(num - 1); return; }
      if (e.key === 'ArrowRight') { setActive((current + 1) % variants.length); return; }
      if (e.key === 'ArrowLeft')  { setActive((current - 1 + variants.length) % variants.length); return; }
      if ((e.key === 'r' || e.key === 'R') && hasMotion) { mount(current); return; }
    });

    /* --- initial render from URL param, then enable slide animation --- */
    setActive(Math.min(readParam(), variants.length - 1));
    requestAnimationFrame(() => requestAnimationFrame(() => nav.setAttribute('data-ready', '')));
  }

  return { init };
})();
