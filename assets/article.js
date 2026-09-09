(function () {
  'use strict';
  const R=window.NewsReader, main=document.querySelector('.article-main');
  if(!R||!main)return;
  const meta=document.querySelector('.article-meta'), title=document.querySelector('.article-title');
  if(!meta||!title)return;
  const script=document.querySelector('script[src*="assets/article.js"]');
  const root=new URL('../', script.src);
  const home=new URL('index.html',root);
  const category=document.querySelector('meta[name="article-category"]')?.content || 'general';
  let lang=R.validLang(new URLSearchParams(location.search).get('lang')||R.savedLang());
  main.id='article-content';
  const skip=document.createElement('a');skip.className='skip-link';skip.href='#article-content';skip.dataset.i18n='skip';document.body.prepend(skip);
  // A single accessible language select, retaining the old buttons as fallback without JS.
  const oldSelector=document.querySelector('.lang-selector');
  const languageLabel=document.createElement('label');languageLabel.className='language-control';
  const select=document.createElement('select');select.id='reader-language';
  for(const [value,label] of Object.entries({ko:'한국어',en:'English',ja:'日本語',zh:'中文'})){const option=document.createElement('option');option.value=value;option.textContent=label;select.append(option);}
  languageLabel.append(select);oldSelector?.after(languageLabel);
  const crumb=document.createElement('a');crumb.className='reader-breadcrumb';crumb.href=new URL('index.html?cat='+encodeURIComponent(category),root);meta.prepend(crumb);
  // Only the actual category is used. Supplier/brand metadata can be ambiguous.
  const badges=document.querySelector('.badge-row');if(badges){badges.replaceChildren();const badge=document.createElement('span');badge.className='badge';badges.append(badge);}
  const source=document.querySelector('.source-footer a');
  const sourceInfo=document.createElement('div');sourceInfo.className='reader-source';
  if(source){const link=source.cloneNode(true);link.className='';link.replaceChildren();link.textContent=new URL(source.href).hostname.replace(/^www\./,'');sourceInfo.append(link);}
  const notice=document.createElement('span');notice.dataset.i18n='translated';sourceInfo.append(notice);meta.append(sourceInfo);
  const summary=document.createElement('aside');summary.className='reader-summary';
  const summaryTitle=document.createElement('strong');summaryTitle.dataset.i18n='summary';const summaryText=document.createElement('p');summary.append(summaryTitle,summaryText);main.append(summary);
  const pending=document.createElement('p');pending.className='translation-notice';pending.hidden=true;pending.dataset.i18n='pending';meta.append(pending);
  // Mobile readers get search before the article instead of after a long body.
  const searchForm=document.createElement('form');searchForm.className='article-search-form';searchForm.action=home.href;searchForm.setAttribute('role','search');
  const searchInput=document.createElement('input');searchInput.type='search';searchInput.name='search';const searchButton=document.createElement('button');searchButton.type='submit';searchButton.dataset.i18n='search';searchForm.append(searchInput,searchButton);meta.prepend(searchForm);
  const back=document.createElement('a');back.className='reader-back';back.href=home.href;back.dataset.i18n='back';main.append(back);
  let related=[];
  const relatedSection=document.createElement('section');relatedSection.className='related-reading';relatedSection.hidden=true;
  const relatedHeading=document.createElement('h2');relatedHeading.dataset.i18n='related';const relatedLinks=document.createElement('div');relatedSection.append(relatedHeading,relatedLinks);main.append(relatedSection);
  function apply() {
    const t=R.copy[lang];
    R.localize(lang);R.saveLang(lang);select.value=lang;select.setAttribute('aria-label',t.language);
    title.textContent=title.dataset[lang]||title.dataset.ko||title.textContent;
    document.title='AI시테이 · '+title.textContent;
    const bodies=[...document.querySelectorAll('.lang-body')];
    const korean=bodies.find(el=>el.dataset.lang==='ko');
    const chosen=bodies.find(el=>el.dataset.lang===lang)||korean;
    bodies.forEach(el=>{el.classList.toggle('lang-active',el===chosen);el.hidden=el!==chosen;});
    pending.hidden=lang==='ko'||!korean||!chosen||chosen.textContent.trim()!==korean.textContent.trim();
    document.querySelectorAll('.caption-lang').forEach(el=>{const active=el.dataset.lang===lang;el.classList.toggle('lang-active',active);el.hidden=!active;});
    if(badges)badges.firstElementChild.textContent=t[category]||t.general;
    crumb.textContent=t.back+' / '+(t[category]||t.general);
    crumb.href=new URL('index.html?cat='+encodeURIComponent(category)+'&lang='+lang,root);
    searchInput.placeholder=t.searchLabel;searchInput.setAttribute('aria-label',t.searchLabel);
    const paragraph=[...(chosen?.querySelectorAll('p')||[])].find(el=>el.textContent.trim().length>35);
    summary.hidden=!paragraph;
    if(paragraph){const text=paragraph.textContent.trim();summaryText.textContent=text.length>200?text.slice(0,200)+'…':text;}
    // Translate common legacy navigation labels while preserving links and dates.
    document.querySelectorAll('.header-nav a').forEach(el=>el.textContent=t.news);
    document.querySelectorAll('.sidebar .cat-btn').forEach(el=>{const url=new URL(el.href),cat=url.searchParams.get('cat');el.textContent=cat?t[cat]||t.general:t.all;});
    const sidebarTitles=document.querySelectorAll('.sidebar-title');
    sidebarTitles.forEach(el=>{const parent=el.parentElement;if(parent.querySelector('input'))el.textContent=t.searchLabel;else if(parent.querySelector('.archive-list'))el.textContent=t.archive;else if(parent.querySelector('.category-btns'))el.textContent=t.news;});
    document.querySelectorAll('.sidebar input').forEach(el=>{el.placeholder=t.searchLabel;el.setAttribute('aria-label',t.searchLabel);});
    const imageHeading=document.querySelector('.images-section-title');if(imageHeading)imageHeading.textContent=t.images;
    const sourceLabel=document.querySelector('.source-label strong');if(sourceLabel)sourceLabel.textContent=t.source;
    if(source)source.textContent=t.source+' ↗';
    back.href=home.href+'?lang='+lang;
    relatedLinks.replaceChildren();related.forEach(a=>{const link=document.createElement('a');link.href=new URL(a.url+'?lang='+lang,root);link.textContent=a['title_'+lang]||a.title_ko||a.title;relatedLinks.append(link);});
  }
  select.addEventListener('change',()=>{lang=R.validLang(select.value);apply();const url=new URL(location.href);url.searchParams.set('lang',lang);history.replaceState({},'',url);});
  async function loadRelated() {
    try {
      const response=await fetch(new URL('assets/data/articles.json',root));if(!response.ok)return;
      const articles=await response.json();
      const others=articles.filter(a=>new URL(a.url,root).pathname!==location.pathname);
      related=others.filter(a=>a.category===category).slice(0,3);
      if(related.length<3)related.push(...others.filter(a=>!related.includes(a)).slice(0,3-related.length));
      relatedSection.hidden=!related.length;apply();
    } catch (_) { /* The article and original-source links remain available offline. */ }
  }
  if('IntersectionObserver' in window){const observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)){observer.disconnect();loadRelated();}},{rootMargin:'500px'});observer.observe(back);}else{loadRelated();}
  apply();
})();
