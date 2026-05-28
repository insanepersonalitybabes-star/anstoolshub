/* ANS Tools – Main JS */
'use strict';

// ── Hamburger Menu ────────────────────────────────────────────────
const hamburger = document.getElementById('hamburger');
const mobileNav = document.getElementById('mobileNav');
if (hamburger && mobileNav) {
  hamburger.addEventListener('click', () => {
    mobileNav.classList.toggle('open');
  });
  document.addEventListener('click', e => {
    if (!hamburger.contains(e.target) && !mobileNav.contains(e.target))
      mobileNav.classList.remove('open');
  });
}

// ── Hero Search syncs to tool grid ───────────────────────────────
const heroSearch = document.getElementById('heroSearch');
const toolSearch = document.getElementById('toolSearch');
if (heroSearch && toolSearch) {
  heroSearch.addEventListener('input', () => {
    toolSearch.value = heroSearch.value;
    toolSearch.dispatchEvent(new Event('input'));
    if (heroSearch.value.length > 0) {
      const toolsSection = document.getElementById('tools');
      if (toolsSection) toolsSection.scrollIntoView({ behavior: 'smooth' });
    }
  });
}

// ── Tool Search + Category Filter ────────────────────────────────
const searchInput = document.getElementById('toolSearch');
const filterBtns  = document.querySelectorAll('.filter-btn');
const toolCards   = document.querySelectorAll('.tool-card[data-category]');
let activeCategory = 'all';

function filterTools() {
  const q = searchInput ? searchInput.value.toLowerCase().trim() : '';
  let visible = 0;
  toolCards.forEach(card => {
    const nameMatch = (card.dataset.name || '').toLowerCase().includes(q);
    const descMatch = (card.dataset.desc || '').toLowerCase().includes(q);
    const catMatch  = activeCategory === 'all' || card.dataset.category === activeCategory;
    const show = (nameMatch || descMatch) && catMatch;
    card.style.display = show ? '' : 'none';
    if (show) visible++;
  });
  const noResults = document.getElementById('noResults');
  if (noResults) noResults.style.display = visible === 0 ? '' : 'none';
}
if (searchInput) searchInput.addEventListener('input', filterTools);
filterBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    filterBtns.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeCategory = btn.dataset.cat;
    filterTools();
  });
});

// ── FAQ Accordion ─────────────────────────────────────────────────
document.querySelectorAll('.faq-question').forEach(btn => {
  btn.addEventListener('click', () => {
    const answer = btn.nextElementSibling;
    const isOpen = btn.classList.contains('open');
    document.querySelectorAll('.faq-question.open').forEach(ob => {
      ob.classList.remove('open');
      ob.nextElementSibling.classList.remove('open');
    });
    if (!isOpen) { btn.classList.add('open'); answer.classList.add('open'); }
  });
});

// ── Toast Notification ────────────────────────────────────────────
function showToast(msg, duration = 2500) {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), duration);
}
window.showToast = showToast;

// ── Copy to Clipboard ─────────────────────────────────────────────
function copyText(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    showToast('Copied to clipboard!');
    if (btn) {
      const orig = btn.innerHTML;
      btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> Copied!';
      setTimeout(() => { btn.innerHTML = orig; }, 2000);
    }
  }).catch(() => showToast('Copy failed – please copy manually'));
}
document.querySelectorAll('[data-copy-target]').forEach(btn => {
  btn.addEventListener('click', () => {
    const el = document.getElementById(btn.dataset.copyTarget);
    if (el) copyText(el.value || el.textContent.trim(), btn);
  });
});
document.querySelectorAll('[data-copy-text]').forEach(btn => {
  btn.addEventListener('click', () => copyText(btn.dataset.copyText, btn));
});
window.copyText = copyText;

// ── Back to Top ───────────────────────────────────────────────────
const btt = document.getElementById('backToTop');
if (btt) {
  window.addEventListener('scroll', () => btt.classList.toggle('visible', window.scrollY > 400), { passive: true });
  btt.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
}

// ── Cookie Banner ─────────────────────────────────────────────────
const cookieBanner = document.getElementById('cookieBanner');
if (cookieBanner && !localStorage.getItem('cookieAccepted')) {
  cookieBanner.classList.add('visible');
}
function acceptCookies() {
  localStorage.setItem('cookieAccepted', '1');
  if (cookieBanner) cookieBanner.classList.remove('visible');
}
window.acceptCookies = acceptCookies;

// ── Text to Speech ────────────────────────────────────────────────
function speakText() {
  const text = document.getElementById('ttsText');
  if (!text || !text.value.trim()) { showToast('Please enter text first'); return; }
  window.speechSynthesis.cancel();
  const utt = new SpeechSynthesisUtterance(text.value);
  const voice = document.getElementById('ttsVoice');
  const speed = document.getElementById('ttsSpeed');
  const pitch = document.getElementById('ttsPitch');
  if (voice && window._ttsVoices && window._ttsVoices[voice.value]) utt.voice = window._ttsVoices[voice.value];
  utt.rate  = speed ? parseFloat(speed.value) : 1;
  utt.pitch = pitch ? parseFloat(pitch.value) : 1;
  window.speechSynthesis.speak(utt);
}
function stopTTS() { window.speechSynthesis.cancel(); }
window.speakText = speakText; window.stopTTS = stopTTS;
if (typeof window.speechSynthesis !== 'undefined') {
  const loadVoices = () => {
    const sel = document.getElementById('ttsVoice');
    if (!sel) return;
    const voices = window.speechSynthesis.getVoices();
    window._ttsVoices = voices;
    sel.innerHTML = voices.map((v, i) => `<option value="${i}">${v.name} (${v.lang})</option>`).join('');
  };
  window.speechSynthesis.onvoiceschanged = loadVoices;
  loadVoices();
}

// ── Suggestion Widget ─────────────────────────────────────────────
async function submitSuggestion(toolSlug) {
  const textarea = document.getElementById('suggestionText');
  const emailEl  = document.getElementById('suggestionEmail');
  const typeEl   = document.getElementById('suggestionType');
  if (!textarea || !textarea.value.trim()) { showToast('Please enter a suggestion'); return; }
  const btn = document.getElementById('suggestionSubmit');
  if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }
  try {
    const res = await fetch('/api/suggest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tool_slug: toolSlug,
        type: typeEl ? typeEl.value : 'suggestion',
        suggestion: textarea.value.trim(),
        email: emailEl ? emailEl.value.trim() : ''
      })
    });
    const data = await res.json();
    if (data.ok) {
      const s = document.getElementById('suggestionSuccess');
      if (s) s.classList.add('visible');
      if (textarea) textarea.value = '';
      if (emailEl) emailEl.value = '';
    } else showToast('Could not send. Try again.');
  } catch { showToast('Network error. Try again.'); }
  finally { if (btn) { btn.disabled = false; btn.textContent = 'Send Suggestion'; } }
}
window.submitSuggestion = submitSuggestion;

// ── Share ─────────────────────────────────────────────────────────
function shareUrl(platform) {
  const url   = encodeURIComponent(location.href);
  const title = encodeURIComponent(document.title);
  if (platform === 'copy') { copyText(location.href, null); return; }
  const map = {
    twitter:  `https://twitter.com/intent/tweet?url=${url}&text=${title}`,
    facebook: `https://www.facebook.com/sharer/sharer.php?u=${url}`,
    whatsapp: `https://wa.me/?text=${title}%20${url}`,
  };
  if (map[platform]) window.open(map[platform], '_blank', 'width=600,height=400');
}
window.shareUrl = shareUrl;

// ── Password length display ───────────────────────────────────────
const pwLen = document.getElementById('pwLength');
const pwDisp = document.getElementById('pwLengthDisplay');
if (pwLen && pwDisp) pwLen.addEventListener('input', () => pwDisp.textContent = pwLen.value);

// ── Invoice: Add item ─────────────────────────────────────────────
function addInvoiceItem() {
  const container = document.getElementById('invoiceItems');
  if (!container) return;
  const row = document.createElement('div');
  row.className = 'form-row invoice-item';
  row.style.cssText = 'grid-template-columns:3fr 1fr 1fr auto;align-items:end;gap:10px;margin-bottom:10px;';
  row.innerHTML = `
    <div class="form-group" style="margin:0"><input name="item_desc" class="form-control" placeholder="Item description"></div>
    <div class="form-group" style="margin:0"><input name="item_qty" class="form-control" type="number" value="1" min="0.01" step="0.01"></div>
    <div class="form-group" style="margin:0"><input name="item_price" class="form-control" type="number" value="0" min="0" step="0.01"></div>
    <button type="button" onclick="this.closest('.invoice-item').remove()" style="padding:11px 12px;background:#FEE2E2;border:none;border-radius:8px;cursor:pointer;color:#DC2626;">✕</button>`;
  container.appendChild(row);
}
window.addInvoiceItem = addInvoiceItem;

// ── Text Diff char counts ─────────────────────────────────────────
['diffText1','diffText2'].forEach((id,i) => {
  const el = document.getElementById(id);
  const counter = document.getElementById(`diffCount${i+1}`);
  if (el && counter) el.addEventListener('input', () => {
    counter.textContent = `${el.value.length} chars · ${el.value.split('\n').length} lines`;
  });
});

// ── JSON live validation ──────────────────────────────────────────
const jsonInput  = document.getElementById('jsonInput');
const jsonStatus = document.getElementById('jsonStatus');
if (jsonInput && jsonStatus) {
  jsonInput.addEventListener('input', () => {
    try { JSON.parse(jsonInput.value); jsonStatus.textContent = '✓ Valid JSON'; jsonStatus.style.color = 'var(--success)'; }
    catch (e) { jsonStatus.textContent = `✗ ${e.message}`; jsonStatus.style.color = 'var(--danger)'; }
  });
}

// ── Smooth anchor scroll ──────────────────────────────────────────
document.querySelectorAll('a[href^="#"]').forEach(a => {
  a.addEventListener('click', e => {
    const target = document.querySelector(a.getAttribute('href'));
    if (target) { e.preventDefault(); target.scrollIntoView({ behavior: 'smooth' }); }
  });
});
