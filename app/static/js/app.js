/* TalentConnect — interactions globales */
(function () {
  function icons() { if (window.lucide) lucide.createIcons({ attrs: { 'stroke-width': 1.9 } }); }

  // Apparition au défilement
  function reveal() {
    const els = document.querySelectorAll('.reveal:not(.in)');
    if (!('IntersectionObserver' in window)) { els.forEach(e => e.classList.add('in')); return; }
    const io = new IntersectionObserver((entries) => {
      entries.forEach(en => { if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); } });
    }, { threshold: 0.12 });
    els.forEach((e, i) => { e.style.transitionDelay = (e.dataset.delay || (i % 6) * 60) + 'ms'; io.observe(e); });
  }

  // Compteurs animés : <span data-count="1234">0</span>
  function counters() {
    document.querySelectorAll('[data-count]:not([data-done])').forEach(el => {
      el.dataset.done = 1;
      const target = parseFloat(el.dataset.count) || 0, dur = 1100, t0 = performance.now();
      const step = (now) => {
        const p = Math.min(1, (now - t0) / dur), v = target * (1 - Math.pow(1 - p, 3));
        el.textContent = Math.round(v).toLocaleString();
        if (p < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });
  }

  // Barres de progression animées : <div class="progress"><span data-w="72"></span></div>
  function bars() {
    document.querySelectorAll('.progress > span[data-w]').forEach(s => {
      requestAnimationFrame(() => { s.style.width = s.dataset.w + '%'; });
    });
  }

  function init() { icons(); reveal(); counters(); bars(); }
  document.addEventListener('DOMContentLoaded', init);
  document.addEventListener('htmx:afterSwap', init);
  document.addEventListener('htmx:afterSettle', icons);
  window.tcInit = init;

  // Saisie de tags (compétences…) : <div data-tags data-name="skills" data-value="a,b"></div>
  window.tagInput = function (initial, suggestions) {
    return {
      tags: (initial || '').split(',').map(s => s.trim()).filter(Boolean),
      draft: '', suggestions: suggestions || [],
      get filtered() {
        const d = this.draft.toLowerCase();
        return d.length < 1 ? [] : this.suggestions.filter(s => s.toLowerCase().includes(d) && !this.tags.includes(s)).slice(0, 6);
      },
      add(v) { v = (v ?? this.draft).trim().replace(/,$/, ''); if (v && !this.tags.includes(v)) this.tags.push(v); this.draft = ''; },
      remove(i) { this.tags.splice(i, 1); },
      key(e) {
        if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); this.add(); }
        else if (e.key === 'Backspace' && !this.draft && this.tags.length) this.tags.pop();
      },
      get joined() { return this.tags.join(', '); }
    };
  };

  // Villes selon le pays (autocomplétion)
  window.cityPicker = function (country, city) {
    return {
      country: country || 'CI', city: city || '', list: [],
      async load() {
        try { const r = await fetch('/api/cities/' + this.country); this.list = await r.json(); } catch (e) { this.list = []; }
      },
      init() { this.load(); this.$watch('country', () => { this.city = ''; this.load(); }); }
    };
  };
})();
