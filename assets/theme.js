/* Apply a saved preference in <head>, before the page can paint. */
(function () {
  'use strict';
  const key='aisitei_theme', root=document.documentElement;
  const normalize=value=>value==='dark'?'dark':'light';
  let theme='light';
  try { theme=normalize(localStorage.getItem(key)); } catch (_) { /* Storage may be disabled. */ }
  root.dataset.theme=theme;
  const labels={
    ko:{light:'다크 모드',dark:'라이트 모드'},
    en:{light:'Dark mode',dark:'Light mode'},
    ja:{light:'ダークモード',dark:'ライトモード'},
    zh:{light:'深色模式',dark:'浅色模式'}
  };
  function render() {
    const language=(root.lang||'ko').split('-')[0];
    const label=(labels[language]||labels.ko)[theme];
    document.querySelectorAll('[data-theme-toggle]').forEach(button=>{
      button.hidden=false;
      button.setAttribute('aria-pressed',String(theme==='dark'));
      button.setAttribute('aria-label',label);
      const text=button.querySelector('[data-theme-label]');
      if(text)text.textContent=label;
    });
  }
  function apply(value) {
    theme=normalize(value);root.dataset.theme=theme;render();
  }
  document.addEventListener('click',event=>{
    if(!event.target.closest('[data-theme-toggle]'))return;
    apply(theme==='dark'?'light':'dark');
    try { localStorage.setItem(key,theme); } catch (_) { /* Still usable in this page. */ }
  });
  window.addEventListener('storage',event=>{
    if(event.key===key||event.key===null)apply(event.newValue);
  });
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',render,{once:true});
  else render();
  if(typeof MutationObserver!=='undefined')new MutationObserver(render).observe(root,{attributes:true,attributeFilter:['lang']});
})();
