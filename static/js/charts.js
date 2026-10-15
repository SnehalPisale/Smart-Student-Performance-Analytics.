/* Shared Plotly helpers */
const COLORS = {primary:'#26408b', low:'#2a8c82', med:'#d99a00', high:'#c8423b',
                grey:'#8a94a6', ink:'#1c2333', unrated:'#cfd5df'};
const RISK_COLOR = {Low:COLORS.low, Medium:COLORS.med, High:COLORS.high, Unrated:COLORS.unrated};

function baseLayout(extra) {
  const out = {
    margin:{l:52,r:16,t:12,b:48},
    font:{family:'Public Sans, system-ui, sans-serif', size:12, color:COLORS.ink},
    paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
    xaxis:{gridcolor:'#e6e9ef', zerolinecolor:'#cfd5df'},
    yaxis:{gridcolor:'#e6e9ef', zerolinecolor:'#cfd5df'},
    legend:{orientation:'h', y:-0.22}
  };
  for (const k in (extra || {})) {
    const v = extra[k];
    out[k] = (v && typeof v === 'object' && !Array.isArray(v) && out[k]) ? Object.assign({}, out[k], v) : v;
  }
  return out;
}
function draw(id, data, extra) {
  const node = document.getElementById(id);
  if (!node) return;
  if (!window.Plotly) {
    node.textContent = 'Charts could not load. Check your internet connection (Plotly is loaded from a CDN) and refresh.';
    node.style.color = '#5d667a';
    return;
  }
  Plotly.newPlot(node, data, baseLayout(extra), {responsive:true, displayModeBar:false});
}
async function getJSON(url) {
  const r = await fetch(url, {headers:{'Accept':'application/json'}});
  if (!r.ok) throw new Error('Request failed: ' + r.status);
  return r.json();
}
function fmt(v, suffix) { return (v === null || v === undefined) ? '-' : v + (suffix || ''); }
function el(tag, attrs, text) {
  const n = document.createElement(tag);
  for (const k in (attrs || {})) n.setAttribute(k, attrs[k]);
  if (text !== undefined) n.textContent = text;
  return n;
}
/* Run fn after the page and the deferred Plotly script have been processed */
function whenReady(fn) {
  if (document.readyState !== 'loading') return fn();
  document.addEventListener('DOMContentLoaded', fn);
}
