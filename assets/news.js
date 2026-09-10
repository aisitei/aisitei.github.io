(function () {
  'use strict';
  const languages = ['ko', 'en', 'ja', 'zh'];
  const copy = {
    ko: {news:'테크 뉴스', language:'언어',headline:'기술의 변화, 매일 한눈에.',description:'카메라 · 스마트폰 · AI, 해외 테크 소식을 모아 전합니다.', updated:'최근 발행',searchLabel:'기사 검색',search:'검색',placeholder:'궁금한 기술, 제품, 소식을 검색하세요',archive:'아카이브',allDates:'전체 기간',latestHighlights:'새로 들어온 소식',latest:'최신 뉴스',results:'검색 결과',previous:'이전',next:'다음',reset:'필터 초기화',empty:'검색 결과가 없습니다',emptyHint:'다른 검색어를 입력하거나 필터를 초기화해 보세요.',footer:'해외 테크 뉴스 · 자동 수집 및 번역 · 원문 출처는 각 기사에 표시됩니다.',top:'맨 위로 ↑',read:'기사 읽기',count:'개 기사',all:'전체',camera:'카메라',phone:'스마트폰',ai:'AI',general:'테크',loadError:'전체 기사 목록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.',retry:'다시 시도',source:'원문',translated:'자동 번역 · 자세한 내용은 원문을 확인하세요',summary:'기사 미리 읽기',related:'이어서 읽기',back:'전체 뉴스 보기',images:'이미지 전체 보기',pending:'선택한 언어의 번역을 준비 중입니다. 한국어 원문을 표시합니다.',skip:'본문으로 건너뛰기'},
    en: {news:'Tech news',language:'Language',headline:'A daily perspective on tech.',description:'Cameras, smartphones and AI. Technology news from around the world.',updated:'Latest edition',searchLabel:'Search articles',search:'Search',placeholder:'Search products, technology and news',archive:'Archive',allDates:'All dates',latestHighlights:'Just in',latest:'Latest news',results:'Search results',previous:'Previous',next:'Next',reset:'Clear filters',empty:'No stories found',emptyHint:'Try a different search or clear your filters.',footer:'International tech news · Automatically collected and translated · Original sources linked in each article.',top:'Back to top ↑',read:'Read story',count:'stories',all:'All',camera:'Cameras',phone:'Phones',ai:'AI',general:'Tech',loadError:'Could not load all articles. Please try again.',retry:'Retry',source:'Source',translated:'Automatically translated · Refer to the original for details',summary:'Story preview',related:'Read next',back:'All news',images:'All images',pending:'This translation is being prepared. Showing Korean content.',skip:'Skip to content'},
    ja: {news:'テックニュース',language:'言語',headline:'技術の変化を、毎日ひと目で。',description:'カメラ・スマートフォン・AI。世界のテックニュースをお届けします。',updated:'最新の配信',searchLabel:'記事を検索',search:'検索',placeholder:'製品、技術、ニュースを検索',archive:'アーカイブ',allDates:'すべての期間',latestHighlights:'新着トピックス',latest:'最新ニュース',results:'検索結果',previous:'前へ',next:'次へ',reset:'条件をクリア',empty:'記事が見つかりません',emptyHint:'検索語や絞り込み条件を変更してください。',footer:'海外テックニュース・自動収集と翻訳・各記事に原文のリンクを掲載しています。',top:'トップへ ↑',read:'記事を読む',count:'件の記事',all:'すべて',camera:'カメラ',phone:'スマートフォン',ai:'AI',general:'テック',loadError:'記事を読み込めませんでした。もう一度お試しください。',retry:'再試行',source:'原文',translated:'自動翻訳・詳細は原文をご確認ください',summary:'記事のプレビュー',related:'あわせて読む',back:'ニュース一覧',images:'すべての画像',pending:'翻訳を準備中です。韓国語の記事を表示しています。',skip:'本文へ移動'},
    zh: {news:'科技新闻',language:'语言',headline:'科技新变化，每日一览。',description:'相机、智能手机与 AI，汇集全球科技资讯。',updated:'最近发布',searchLabel:'搜索文章',search:'搜索',placeholder:'搜索产品、技术和新闻',archive:'归档',allDates:'全部日期',latestHighlights:'最新看点',latest:'最新新闻',results:'搜索结果',previous:'上一页',next:'下一页',reset:'清除筛选',empty:'没有找到相关文章',emptyHint:'请更换关键词或清除筛选条件。',footer:'海外科技新闻 · 自动收集和翻译 · 每篇文章均附原文来源。',top:'返回顶部 ↑',read:'阅读文章',count:'篇文章',all:'全部',camera:'相机',phone:'智能手机',ai:'AI',general:'科技',loadError:'无法加载全部文章，请稍后重试。',retry:'重试',source:'原文',translated:'自动翻译 · 详情请参阅原文',summary:'文章预览',related:'继续阅读',back:'全部新闻',images:'全部图片',pending:'所选语言的翻译正在准备中，暂时显示韩语内容。',skip:'跳至正文'}
  };
  function validLang(lang) { return languages.includes(lang) ? lang : 'ko'; }
  function readState(search, fallback) {
    const p = new URLSearchParams(search);
    return {lang:validLang(p.get('lang') || fallback),query:p.get('search') || '',category:p.get('cat') || '',month:p.get('month') || '',page:Math.max(1, parseInt(p.get('page'), 10) || 1)};
  }
  function filterArticles(items, state) {
    const query = state.query.trim().toLocaleLowerCase();
    return items.filter(a => (!state.category || a.category === state.category) && (!state.month || a.month === state.month) && (!query || String(a['title_' + state.lang] || a.title_ko || a.title).toLocaleLowerCase().includes(query)));
  }
  function paginate(items, requestedPage, size=24) {
    const pages = Math.max(1, Math.ceil(items.length / size));
    const page = Math.min(pages, Math.max(1, parseInt(requestedPage, 10) || 1));
    return {items:items.slice((page - 1) * size, page * size),page,pages};
  }
  function pageLink(state,page,route='news') {
    const p=new URLSearchParams();
    if(state.query) p.set('search',state.query);
    if(state.category) p.set('cat',state.category);
    if(state.month) p.set('month',state.month);
    p.set('lang',state.lang);
    const filtered=Boolean(state.query||state.category||state.month);
    const first=route==='news'?'index.html':'reports.html';
    if(filtered){if(page>1)p.set('page',page);return first+'?'+p;}
    return (page===1?first:(route==='news'?'news':'report-pages')+'/page-'+page+'.html')+'?'+p;
  }
  function savedLang() { try { return validLang(localStorage.getItem('aisitei_lang')); } catch (_) { return 'ko'; } }
  function saveLang(lang) { try { localStorage.setItem('aisitei_lang', lang); } catch (_) {} }
  function escape(value) { return String(value || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  function localize(lang, root=document) {
    const t = copy[validLang(lang)];
    root.querySelectorAll('[data-i18n]').forEach(el => { const value=t[el.dataset.i18n]; if(value) el.textContent=value; });
    document.documentElement.lang = {ko:'ko',en:'en',ja:'ja',zh:'zh-Hans'}[validLang(lang)];
  }
  function articleCard(a, lang, lead=false) {
    const t=copy[lang], title=a['title_'+lang] || a.title_ko || a.title, topic=t[a.category] || t.general;
    const image = a.thumbnail && !a.thumbnail.endsWith('apple-touch-icon.png') ? `<img src="${escape(a.thumbnail)}" alt="" loading="${lead?'eager':'lazy'}" width="640" height="400">` : `<img class="fallback-image" src="assets/images/apple-touch-icon.png" alt="" loading="lazy" width="180" height="180">`;
    return `<article class="news-card${lead?' lead-card':''}"><a href="${escape(a.url)}?lang=${lang}"><div class="news-image">${image}</div><div class="news-copy"><div class="news-meta"><span class="topic">${escape(topic)}</span><time datetime="${escape(a.date)}">${escape(a.date)}</time></div><h2>${escape(title)}</h2><span class="read-story" aria-hidden="true">${t.read}<span>↗</span></span></div></a></article>`;
  }
  const api={filterArticles,paginate,readState,pageLink,copy,validLang,savedLang,saveLang,escape,localize,articleCard};
  if(typeof module !== 'undefined') module.exports=api;
  if(typeof window === 'undefined') return;
  window.NewsReader=api;
  const seedElement=document.getElementById('news-seed');
  if(!seedElement) return;
  const seed=JSON.parse(seedElement.textContent);
  // Freeze the site root before pushState moves between index.html and news/page-N.html.
  const siteBase=new URL('./',document.baseURI).href;
  const base=document.querySelector('base')||document.head.appendChild(document.createElement('base'));
  base.href=siteBase;
  document.querySelectorAll('.skip-link, .site-footer a[href$="#news-content"]').forEach(link=>link.addEventListener('click',event=>{
    if(event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
    event.preventDefault();
    const content=document.getElementById('news-content');content.setAttribute('tabindex','-1');content.focus({preventScroll:true});content.scrollIntoView({block:'start'});
  }));
  let state=readState(location.search, savedLang());
  if(!new URLSearchParams(location.search).has('page')) state.page=seed.page;
  let corpus=null, pending=null, requestId=0;
  const byId=id=>document.getElementById(id);
  const categoryLinks=[...document.querySelectorAll('[data-filter]')];
  function pageHref(page) {
    return pageLink(state,page,seed.route);
  }

  async function allArticles() {
    if(corpus) return corpus;
    if(!pending) pending=fetch(new URL(seed.dataUrl, document.baseURI)).then(r=>{if(!r.ok) throw Error('index'); return r.json();}).then(data=>{if(!Array.isArray(data)) throw Error('index');corpus=data;return data;}).finally(()=>{pending=null;});
    return pending;
  }
  function controls() {
    const t=copy[state.lang];
    localize(state.lang);
    document.querySelector('.skip-link').textContent=t.skip;
    byId('language').value=state.lang;
    byId('language').setAttribute('aria-label', t.language);
    byId('search').value=state.query;
    byId('search').placeholder=t.placeholder;
    byId('month').value=state.month;
    byId('month').setAttribute('aria-label',t.archive);
    document.querySelector('.topic-nav').setAttribute('aria-label',t.all);
    categoryLinks.forEach(link=>{const active=link.dataset.filter===state.category;link.textContent=t[link.dataset.filter || 'all'];link.classList.toggle('selected',active);if(active)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');});
  }
  function render(items,total,hasFullCorpus) {
    const t=copy[state.lang], filtered=Boolean(state.query||state.category||state.month);
    const result=hasFullCorpus?paginate(items,state.page):{items,page:seed.page,pages:Math.max(1,Math.ceil(total/24))};
    state.page=result.page;
    const feature=!filtered&&state.page===1?result.items.slice(0,3):[];
    byId('featured-section').hidden=!feature.length;
    byId('featured').innerHTML=feature.map((a,i)=>articleCard(a,state.lang,i===0)).join('');
    byId('news-grid').innerHTML=(feature.length?result.items.slice(3):result.items).map(a=>articleCard(a,state.lang)).join('');
    byId('latest-heading').textContent=filtered?t.results:t.latest;
    byId('result-count').textContent=`${total.toLocaleString()} ${t.count}`;
    byId('empty-state').hidden=total!==0;
    byId('filter-state').hidden=!filtered;
    byId('filter-description').textContent=[state.query?`“${state.query}”`:'',state.category?t[state.category]||state.category:'',state.month].filter(Boolean).join(' · ');
    const nav=byId('pagination');nav.replaceChildren();
    function link(label,page,current=false) {const a=document.createElement('a');a.href=pageHref(page);a.textContent=label;a.dataset.page=page;if(current){a.className='current';a.setAttribute('aria-current','page');}nav.append(a);}
    if(result.page>1)link(t.previous,result.page-1);
    const first=Math.max(1,Math.min(result.page-1,result.pages-2));
    for(let n=first;n<=Math.min(result.pages,first+2);n++)link(String(n),n,n===result.page);
    if(result.page<result.pages)link(t.next,result.page+1);
  }
  async function update(push=false) {
    const id=++requestId;
    controls();
    byId('load-error').hidden=true;
    byId('news-content').setAttribute('aria-busy','true');
    try {
      const full=Boolean(corpus||state.query||state.category||state.month||state.page!==seed.page);
      const items=full?filterArticles(await allArticles(),state):seed.articles;
      if(id!==requestId)return;
      render(items,full?items.length:seed.total,full);
      if(push)history.pushState({},'',new URL(pageHref(state.page), document.baseURI));
      return true;
    } catch (_) {
      if(id!==requestId)return;
      const error=byId('load-error');error.replaceChildren(document.createTextNode(copy[state.lang].loadError));
      const retry=document.createElement('button');retry.textContent=copy[state.lang].retry;retry.onclick=()=>update(push);error.append(retry);error.hidden=false;
      return false;
    } finally {if(id===requestId)byId('news-content').removeAttribute('aria-busy');}
  }
  let timer;
  document.querySelector('.reader-tools').addEventListener('submit',event=>{event.preventDefault();clearTimeout(timer);state.query=byId('search').value.trim();state.page=1;update(true);});
  byId('search').addEventListener('input',event=>{state.query=event.target.value;state.page=1;clearTimeout(timer);timer=setTimeout(()=>update(true),220);});
  byId('month').addEventListener('change',event=>{state.month=event.target.value;state.page=1;update(true);});
  categoryLinks.forEach(link=>link.addEventListener('click',event=>{event.preventDefault();state.category=link.dataset.filter;state.page=1;update(true);}));
  byId('reset').addEventListener('click',()=>{clearTimeout(timer);state.query='';state.category='';state.month='';state.page=1;update(true);});
  byId('language').addEventListener('change',event=>{state.lang=validLang(event.target.value);saveLang(state.lang);state.page=1;update(true);});
  byId('pagination').addEventListener('click',event=>{const link=event.target.closest('[data-page]');if(!link||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey||event.button!==0)return;event.preventDefault();state.page=Number(link.dataset.page);update(true).then(ok=>{if(ok)byId('latest-heading').scrollIntoView({block:'start'});else if(ok===false&&!state.query&&!state.category&&!state.month)location.href=link.href;});});
  window.addEventListener('popstate',()=>{clearTimeout(timer);state=readState(location.search,savedLang());if(!new URLSearchParams(location.search).has('page'))state.page=Number(location.pathname.match(/\/page-(\d+)\.html$/)?.[1])||1;update();});
  document.addEventListener('error',event=>{if(event.target.tagName==='IMG'&&event.target.closest('.news-image')){const target=event.target;if(target.classList.contains('fallback-image'))return;target.classList.add('fallback-image');target.src=new URL('assets/images/apple-touch-icon.png',document.baseURI).href;}},true);
  update();
})();
