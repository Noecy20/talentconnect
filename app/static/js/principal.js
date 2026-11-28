/* TalentConnect — petits comportements communs à toutes les pages.
   La plupart des interactions passent par Alpine.js (attributs x-data dans les gabarits) ;
   ce fichier contient seulement ce qui sert à plusieurs pages. */
(function () {
  // Icônes Lucide : remplace chaque <i data-lucide="..."> par son dessin SVG
  function icones() { if (window.lucide) lucide.createIcons({ attrs: { 'stroke-width': 1.9 } }); }

  // Barres de progression : <div class="progress"><span data-w="72"></span></div>
  function barres() {
    document.querySelectorAll('.progress > span[data-w]').forEach(s => { s.style.width = s.dataset.w + '%'; });
  }

  // Tableaux Kanban : pas de barre de défilement visible. On fait défiler les colonnes
  // avec la molette (vers le bas = vers la droite) ou en faisant glisser le fond du tableau.
  function kanbans() {
    document.querySelectorAll('.defile-kanban:not([data-pret])').forEach(k => {
      k.dataset.pret = '1';
      k.addEventListener('wheel', e => {
        if (Math.abs(e.deltaX) > Math.abs(e.deltaY) || e.shiftKey) return;     // défilement horizontal natif
        const liste = e.target.closest('.kanban-list');
        if (liste && liste.scrollHeight > liste.clientHeight) return;          // la colonne défile elle-même
        const max = k.scrollWidth - k.clientWidth;
        if (max <= 0) return;
        const avant = k.scrollLeft;
        k.scrollLeft = Math.max(0, Math.min(max, avant + e.deltaY));
        if (k.scrollLeft !== avant) e.preventDefault();
      }, { passive: false });
      let x0 = null, g0 = 0;
      k.addEventListener('pointerdown', e => {
        if (e.pointerType !== 'mouse' || e.button !== 0 || e.target.closest('a,button,input,select,textarea,.kanban-card,.carte-suivi')) return;
        x0 = e.clientX; g0 = k.scrollLeft; k.classList.add('glisse');
      });
      window.addEventListener('pointermove', e => { if (x0 !== null) k.scrollLeft = g0 - (e.clientX - x0); });
      window.addEventListener('pointerup', () => { x0 = null; k.classList.remove('glisse'); });
    });
  }

  function init() { icones(); barres(); kanbans(); }
  document.addEventListener('DOMContentLoaded', init);
  document.addEventListener('htmx:afterSwap', init);
  document.addEventListener('htmx:afterSettle', icones);
  window.tcInit = init;

  // Plein écran (bouton de l'en-tête)
  window.basculerPleinEcran = function () {
    if (!document.fullscreenElement) document.documentElement.requestFullscreen?.();
    else document.exitFullscreen?.();
  };

  // Recherche de l'en-tête : liste les pages du menu, s'ouvre aussi avec Ctrl/⌘ + K
  window.recherche = function (liens) {
    const norm = s => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    return {
      ouvert: false, q: '', index: 0, liens: liens || [],
      get resultats() {
        const q = norm(this.q);
        return q ? this.liens.filter(l => norm(l.libelle + ' ' + l.section).includes(q)) : this.liens;
      },
      ouvrir() { this.ouvert = true; this.q = ''; this.index = 0; this.$nextTick(() => { this.$refs.champ.focus(); icones(); }); },
      fermer() { this.ouvert = false; },
      bouger(pas) {
        const n = this.resultats.length;
        if (n) this.index = (this.index + pas + n) % n;
      },
      aller(lien) { lien = lien || this.resultats[this.index]; if (lien) window.location = lien.url; },
      raccourci(e) {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); this.ouvert ? this.fermer() : this.ouvrir(); }
      }
    };
  };

  // Saisie de tags (compétences…)
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

  // Choix de la ville selon le pays (liste servie par /api/cities/<pays>)
  window.cityPicker = function (country, city) {
    const norm = s => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    return {
      country: country || 'CI', city: city || '', list: [], q: '', open: false, loading: false,
      async load() {
        this.loading = true;
        try { const r = await fetch('/api/cities/' + this.country); this.list = await r.json(); } catch (e) { this.list = []; }
        this.loading = false;
        this.$nextTick(icones);
      },
      get filtered() { const q = norm(this.q); return (q ? this.list.filter(c => norm(c.name).includes(q)) : this.list).slice(0, 80); },
      get exact() { const q = norm(this.q); return this.list.some(c => norm(c.name) === q); },
      choose(name) { this.city = name; this.q = ''; this.open = false; },
      pickFirst() { if (this.filtered.length) this.choose(this.filtered[0].name); else if (this.q) this.choose(this.q); },
      init() { this.load(); this.$watch('country', () => { this.city = ''; this.load(); }); this.$watch('open', v => v && this.$nextTick(icones)); }
    };
  };
})();
