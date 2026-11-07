// Shared state, small helpers, the API client, dialogs, navigation between views.

// The path the app is served under ('' at the root, '/mangas' behind a proxy that strips it): the
// server writes it into <html data-root>. Every address of the app goes through appUrl.
const APP_ROOT=document.documentElement.dataset.root||'';
const appUrl=path=>path.startsWith('/')?APP_ROOT+path:path;

// The fields every grid filters by value (listing.py VALUE_FILTERS and LIST_FILTERS).
const MANGA_FACETS=()=>({series:'',language:'',publisher:'',format:'',author:'',genre:'',demographic:'',status:''});
const defaultCatalogFilters=()=>({q:'',mode:'all',...MANGA_FACETS(),reading:'',sort:'title',direction:''});
const defaultCollectionFilters=()=>({q:'',mode:'all',...MANGA_FACETS(),reading:'',location:'',condition:'',sort:'title',direction:''});
const defaultWatchFilters=()=>({q:'',mode:'all',...MANGA_FACETS(),sort:'wished',direction:'desc'});

// What a grid shows (listing.py GROUPINGS): '' its editions, 'volumes' single volumes, or a kind of
// group; how the groups are sorted, and the group that is open ({by, name}; its editions are the
// grid filtered by it).
const defaultGrouping=()=>({by:'',sort:'name',open:null});

const state={
  boot:null, route:'dashboard', edit:false, view:'grid',
  catalogFilters:defaultCatalogFilters(), collectionFilters:defaultCollectionFilters(), watchFilters:defaultWatchFilters(),
  grouping:{catalog:defaultGrouping(),collection:defaultGrouping(),watch:defaultGrouping()},
  watchlistId:null, preorderStatus:'open', readingStatus:'', modalEdition:null, modalVolume:null, modalTab:'copies', suggestions:null,
  mobileFiltersOpen:{}, gridItems:[],
};

const $ = (q, root=document) => root.querySelector(q);
const $$ = (q, root=document) => [...root.querySelectorAll(q)];
const content = $('#content');
const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const currencyMoney = (value,currency='EUR') => {
  try{return new Intl.NumberFormat('de-DE',{style:'currency',currency,maximumFractionDigits:currency==='JPY'||currency==='KRW'?0:2}).format(Number(value)||0)}
  catch{return `${Number(value)||0} ${currency}`}
};
const money = value => currencyMoney(value,'EUR');
const moneyOrDash = value => value == null ? '–' : money(value);
// An amount for a form field, as it is typed in German: 159,90 / 22000.
const amountValue = value => value == null || value === '' ? '' : (Number(value) % 1 ? Number(value).toFixed(2) : String(Number(value))).replace('.', ',');
const date = value => value ? new Intl.DateTimeFormat('de-DE',{day:'2-digit',month:'short',year:'numeric'}).format(new Date(value)) : '–';
const MONTH_NAMES=['Januar','Februar','März','April','Mai','Juni','Juli','August','September','Oktober','November','Dezember'];
// A release or order date as precise as it is known: "2025", "März 2025", "14.03.2025".
function partialDate(value){
  if(!value)return '';
  const [year,month,day]=String(value).split('-');
  if(day)return `${day.slice(0,2)}.${month}.${year}`;
  if(month)return `${MONTH_NAMES[Number(month)-1]||month} ${year}`;
  return year;
}
const thisMonth=()=>new Date().toISOString().slice(0,7);
const plural=(count,one,many)=>`${count} ${count===1?one:many}`;
const conditionLabel=key=>state.boot?.conditions?.[key]||key;
const statusLabel=key=>state.boot?.statuses?.[key]||key;
const readingLabel=key=>state.boot?.reading_statuses?.[key]||key;
const languageLabel=code=>state.boot?.languages?.[code]||(code||'').toUpperCase();
const seriesStatusLabel=key=>state.boot?.series_statuses?.[key]||key;
const demographicLabel=key=>state.boot?.demographics?.[key]||key;
// A volume's number as people say it: "Band 5", a special volume by its title.
const volumeLabel=volume=>volume.number_label?`Band ${volume.number_label}`:(volume.title||volume.volume_title||'Sonderband');
// Pictures: a volume's cover, a series' picture, and an edition's cover (listing.py summarize: its
// first volume with a cover, else the series' picture); without any, the server's placeholder.
const pictureUrl=(kind,id,version,size='thumb')=>appUrl(`/images/${kind}/${id}${size==='thumb'?'/thumb':''}${version?`?v=${version}`:''}`);
const volumeThumb=volume=>pictureUrl('volumes',volume.volume_id??volume.id,volume.image_version);
const volumeImage=volume=>pictureUrl('volumes',volume.volume_id??volume.id,volume.image_version,'full');
const seriesThumb=series=>pictureUrl('series',series.series_id??series.id,series.image_version);
const seriesImage=series=>pictureUrl('series',series.series_id??series.id,series.image_version,'full');
const coverThumb=(cover,seriesId)=>cover?pictureUrl(cover.kind,cover.id,cover.version):pictureUrl('series',seriesId,'');

// A read that loses its connection (a phone between networks, a dropped socket) is tried once
// more after a moment; a write is not, it may have reached the server.
const API_RETRY_DELAY_MS=400;
const api = async (url, options={}) => {
  const request=()=>fetch(appUrl(url),{headers:{'Content-Type':'application/json',...(options.headers||{})},...options});
  const reading=!options.method||options.method==='GET';
  let response;
  try{
    response = await request().catch(async networkError=>{
      if(!reading||options.signal?.aborted)throw networkError;
      await new Promise(resolve=>setTimeout(resolve,API_RETRY_DELAY_MS));
      return request();
    });
  }catch(networkError){
    const error=new Error('Keine Verbindung zum Server');
    error.isNetworkError=true;
    throw error;
  }
  if (response.status===401) { location.href=appUrl('/login'); const error=new Error('Nicht angemeldet'); error.isAuthError=true; throw error; }
  let data;
  try{data = await response.json()}
  catch(parseError){throw new Error(`Serverfehler (${response.status})`)}
  if (!response.ok){const error=new Error(data.error || 'Anfrage fehlgeschlagen');error.status=response.status;error.data=data;throw error}
  return data;
};
const post = (url,data) => api(url,{method:'POST',body:JSON.stringify(data)});
const patch = (url,data) => api(url,{method:'PATCH',body:JSON.stringify(data)});
const del = url => api(url,{method:'DELETE'});

// A setting saved once its control rests (a slider reports every step); one still waiting when the
// page is left goes out with the unload.
const SETTING_SAVE_DELAY_MS=400;
const pendingSettings=new Map();
function saveSettingSoon(key,value){
  if(state.boot)state.boot.settings[key]=value;
  clearTimeout(pendingSettings.get(key)?.timer);
  const timer=setTimeout(()=>{pendingSettings.delete(key);post('/api/settings',{[key]:value}).catch(()=>{})},SETTING_SAVE_DELAY_MS);
  pendingSettings.set(key,{timer,value});
}
function flushPendingSettings(){
  if(!pendingSettings.size)return;
  const settings={};
  for(const [key,{timer,value}] of pendingSettings){clearTimeout(timer);settings[key]=value}
  pendingSettings.clear();
  fetch(appUrl('/api/settings'),{method:'POST',keepalive:true,headers:{'Content-Type':'application/json'},body:JSON.stringify(settings)}).catch(()=>{});
}
addEventListener('pagehide',flushPendingSettings);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden')flushPendingSettings()});

// Debounced search boxes re-render their view; only the most recently started render may put the
// focus and cursor back, so a slow earlier answer never moves the cursor while typing.
const reRenderTokens=new Map();
async function reRenderPreservingFocus(selector,renderFn){
  const myToken=(reRenderTokens.get(selector)||0)+1;
  reRenderTokens.set(selector,myToken);
  const active=document.activeElement;
  const hadFocus=active&&active.matches&&active.matches(selector);
  const selStart=hadFocus?active.selectionStart:null,selEnd=hadFocus?active.selectionEnd:null;
  await renderFn();
  if(reRenderTokens.get(selector)!==myToken)return;
  if(hadFocus){
    const el=$(selector);
    if(el){el.focus();if(selStart!=null)try{el.setSelectionRange(selStart,selEnd)}catch{}}
  }
}

function toast(message, actionLabel, action, key) {
  if(key)$$('.toast',$('#toast-stack')).filter(old=>old.dataset.key===key).forEach(old=>old.remove());
  const node=document.createElement('div'); node.className='toast'; if(key)node.dataset.key=key;
  node.innerHTML=`<span>${escapeHtml(message)}</span>${actionLabel?`<button>${escapeHtml(actionLabel)}</button>`:''}`;
  if(actionLabel) $('button',node).onclick=async()=>{ await action?.(); node.remove(); };
  $('#toast-stack').append(node); setTimeout(()=>node.remove(),actionLabel?8000:5000);
}

function setNav(route) {
  $$('.nav-item[data-route]').forEach(el=>el.classList.toggle('active',el.dataset.route===route));
  $$('.mt-tab[data-route]').forEach(el=>el.classList.toggle('active',el.dataset.route===route));
  $$('.mobile-profile-button[data-route]').forEach(el=>el.classList.toggle('active',el.dataset.route===route));
}

function setEditMode(enabled,announce=false){
  state.edit=Boolean(enabled);
  document.body.classList.toggle('editing',state.edit);
  $('#edit-panel')?.classList.toggle('on',state.edit);
  $('#edit-toggle')?.setAttribute('aria-checked',String(state.edit));
  $('#mobile-edit-toggle')?.classList.toggle('active',state.edit);
  $('#mobile-edit-toggle')?.setAttribute('aria-pressed',String(state.edit));
  if(announce)toast(state.edit?'Schnellbearbeitung an: Plus und Herz direkt auf den Kacheln':'Schnellbearbeitung aus');
}
function toggleEditMode(){setEditMode(!state.edit,true)}

// A view that finishes loading after the user has moved on must not draw over what is on screen.
let renderGeneration=0;
function renderGuard(){const mine=++renderGeneration;return ()=>mine!==renderGeneration}

const TITLES={dashboard:'Übersicht',catalog:'Katalog',collection:'Sammlung',reading:'Lesen',gaps:'Lücken',calendar:'Neuerscheinungen',
  watchlist:'Wunschlisten',preorders:'Vorbestellungen',settings:'Einstellungen',admin:'Admin'};
const LIVE_ROUTES=['dashboard','catalog','collection','reading','gaps','calendar','watchlist','preorders'];
function routeTo(route, data) {
  renderGeneration++;
  state.mobileFiltersOpen={};
  state.route=route; document.body.dataset.route=route; setNav(route); window.scrollTo({top:0,behavior:'smooth'});
  $('.mobile-topbar-title').textContent=TITLES[route]||'';
  if(route==='dashboard') renderDashboard();
  if(route==='catalog') renderCatalog();
  if(route==='collection') renderCollection();
  if(route==='reading') renderReading();
  if(route==='gaps') renderGaps();
  if(route==='calendar') renderCalendar();
  if(route==='watchlist') renderWatchlist(data);
  if(route==='preorders') renderPreorders();
  if(route==='settings') renderSettings();
  if(route==='admin') renderAdmin();
}
// Redraws whatever is on screen after a change elsewhere (a dialog saved something).
function refreshCurrentView(){
  if(LIVE_ROUTES.includes(state.route)){
    const y=window.scrollY;
    const result=routeTo(state.route,state.route==='watchlist'?state.watchlistId:undefined);
    requestAnimationFrame(()=>window.scrollTo({top:y}));
    return result;
  }
}
async function refreshCounts(){
  try{
    const boot=await api('/api/bootstrap');
    state.boot.counts=boot.counts;state.boot.watchlists=boot.watchlists;state.boot.imports=boot.imports;
    paintCounts();
  }catch{}
}
function paintCounts(){
  const counts=state.boot.counts||{};
  for(const [key,value] of Object.entries(counts)){
    $$(`[data-count="${key}"]`).forEach(badge=>{badge.textContent=value;badge.classList.toggle('hidden',!value)});
  }
}

function initials(name){return name.split(/\s+/).map(x=>x[0]).slice(0,2).join('').toUpperCase()}

function mountFilterPanel(key,selectors,label='Filter'){
  const targets=selectors.map(selector=>$(selector,content)).filter(Boolean);
  if(!targets.length)return;
  const panel=document.createElement('ophir-filter-panel');
  panel.setAttribute('filter-key',key);
  panel.setAttribute('label',label);
  panel.dataset.mobileFilterShell=key;
  if(state.mobileFiltersOpen[key])panel.setAttribute('open','');
  targets[0].before(panel);
  targets.forEach(target=>{target.classList.add('shared-filter-content');panel.contentElement.append(target)});
}

function statPill(items,{className='',columns=items.length,mobileColumns=Math.min(items.length,2)}={}){
  const safeColumns=Math.max(1,Math.min(8,Number(columns)||items.length||1));
  const safeMobileColumns=Math.max(1,Math.min(8,Number(mobileColumns)||Math.min(safeColumns,2)));
  const classAttribute=className?` class="${escapeHtml(className)}"`:'';
  return `<ophir-stat-pill${classAttribute} columns="${safeColumns}" mobile-columns="${safeMobileColumns}">${items.map(item=>{
    const itemClass=item.className?` class="${escapeHtml(item.className)}"`:'';
    return `<div data-stat${itemClass}><span>${escapeHtml(item.label)}</span><b>${item.value}</b></div>`;
  }).join('')}</ophir-stat-pill>`;
}

function lockScroll(locked){document.documentElement.style.overflow=locked?'hidden':'';document.body.style.overflow=locked?'hidden':''}
function openOverlay(id){$(`#${id}`).classList.remove('hidden');lockScroll(true)}
function closeOverlay(id){
  $(`#${id}`).classList.add('hidden');
  if(!$('.overlay:not(.hidden)')&&!$('.dl-modal-overlay'))lockScroll(false);
  if(id==='edition-modal')state.modalEdition=null;
  if(id==='volume-modal')state.modalVolume=null;
}

// A dialog over the page: openDialog() returns its element, the caller fills and wires it.
// stack: open over a dialog that is already open instead of replacing it.
function openDialog({id,eyebrow='',title,intro='',body='',stack=false,wide=false}){
  if(!stack)while($('.dl-modal-overlay'))closeDialog();
  const modal=document.createElement('div');
  modal.id=id;modal.className='overlay dl-modal-overlay';
  modal.setAttribute('role','dialog');modal.setAttribute('aria-modal','true');modal.setAttribute('aria-labelledby',`${id}-title`);
  modal.innerHTML=`<div class="dl-modal${wide?' dl-modal-wide':''}"><div class="dl-modal-head"><div>${eyebrow?`<span class="eyebrow">${eyebrow}</span>`:''}<h2 id="${id}-title">${title}</h2>${intro?`<p>${intro}</p>`:''}</div><button class="close-button" type="button" data-dialog-close aria-label="Schließen">×</button></div><div class="dl-modal-body">${body}</div></div>`;
  document.body.append(modal);
  lockScroll(true);
  $$('[data-dialog-close]',modal).forEach(button=>button.onclick=closeDialog);
  modal.onmousedown=event=>{if(event.target===modal)closeDialog()};
  requestAnimationFrame(()=>$('input:not([type=hidden]):not([type=checkbox]),select,textarea',$('.dl-modal-body',modal))?.focus());
  return modal;
}
function closeDialog(){
  const open=$$('.dl-modal-overlay').at(-1);if(!open)return;
  open.remove();
  if(!$('.dl-modal-overlay')&&!$('.overlay:not(.hidden)'))lockScroll(false);
}
// Kept for the settings view, which opened its dialogs under this name.
const openSettingsModal=openDialog,closeSettingsModal=closeDialog;
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&$('.dl-modal-overlay')){event.stopPropagation();closeDialog()}},true);

// Values of a dialog's fields: every element with data-field, by that name.
function fieldValues(root){
  const values={};
  $$('[data-field]',root).forEach(field=>{values[field.dataset.field]=field.type==='checkbox'?field.checked:field.value});
  return values;
}
const datalist=(id,values=[])=>`<datalist id="${id}">${values.map(value=>`<option value="${escapeHtml(value)}"></option>`).join('')}</datalist>`;
async function loadSuggestions(force=false){
  if(!state.suggestions||force)state.suggestions=await api('/api/catalog/suggestions');
  return state.suggestions;
}

// What a search box's text matches, as on the server (ophir_mangas/search.py): every word somewhere
// in the fields, spaces/case/accents aside and a letter off allowed; with | ^ $ \ [ ] * + ? { } the
// text as typed or read as a regular expression ("Naruto|Boruto").
const searchFold=text=>String(text??'').normalize('NFKD').replace(/\p{M}/gu,'').toLowerCase();
const searchWords=text=>searchFold(text).match(/[\p{L}\p{N}_]+/gu)||[];
function searchWithin(word,other,limit){
  if(Math.abs(word.length-other.length)>limit)return false;
  let previous=[...Array(other.length+1).keys()];
  for(let i=1;i<=word.length;i++){
    const current=[i];
    for(let j=1;j<=other.length;j++)current.push(Math.min(previous[j]+1,current[j-1]+1,previous[j-1]+(word[i-1]!==other[j-1])));
    if(Math.min(...current)>limit)return false;
    previous=current;
  }
  return previous[other.length]<=limit;
}
function searchNearMiss(token,words){
  if(token.length<4||/\d/.test(token))return false;
  const limit=token.length<8?1:2;
  return [...words,...words.slice(1).map((word,i)=>words[i]+word)].some(word=>searchWithin(token,word,limit)
    ||[token.length-1,token.length,token.length+1].some(size=>size>0&&size<word.length&&searchWithin(token,word.slice(0,size),limit)));
}
function searchMatcher(query){
  query=query.trim();
  if(/[|^$\\[\]*+?{}]/.test(query)){
    const literal=query.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    let pattern;
    try{pattern=new RegExp(query.length<=200?`${literal}|(?:${query})`:literal,'i')}catch{pattern=new RegExp(literal,'i')}
    return fields=>fields.some(text=>text!=null&&pattern.test(String(text)));
  }
  const tokens=[...new Set(searchWords(query))];
  return fields=>{
    const present=fields.filter(text=>text!=null&&text!=='').map(searchWords);
    return tokens.every(token=>present.some(words=>words.join('').includes(token)||searchNearMiss(token,words)));
  };
}

// The quick search (Ctrl+K): editions, and volumes for an ISBN or a number. An answer that arrives
// after a newer search started is dropped.
let searchSequence=0,searchController=null;
const SEARCH_HINT='<div class="empty-search"><b>Finde jede Reihe. Sofort.</b><span>Titel, Originaltitel, Autor:in, Verlag oder ISBN – in beliebiger Reihenfolge, z.&nbsp;B. „Frieren Egmont“ oder „Attack 12“. Alternativen mit |: Naruto|Boruto</span></div>';
async function doSearch(q){
  const mine=++searchSequence;searchController?.abort();searchController=null;
  const wrap=$('#search-results');
  if(q.trim().length<2){wrap.innerHTML=SEARCH_HINT;return}
  const controller=searchController=new AbortController();
  let found;
  try{found=await api(`/api/search?q=${encodeURIComponent(q)}`,{signal:controller.signal})}
  catch(error){if(mine!==searchSequence)return;throw error}
  if(mine!==searchSequence)return;
  const {editions,volumes}=found;
  if(!editions.length&&!volumes.length){
    const digits=q.replace(/[^\dXx]/g,'');
    wrap.innerHTML=`<div class="empty-search"><b>Keine Treffer</b><span>Nicht im Katalog? <button type="button" class="link-button" id="search-create">${digits.length>=10?`ISBN ${escapeHtml(q)} nachschlagen`:`„${escapeHtml(q)}“ neu anlegen`}</button></span></div>`;
    $('#search-create',wrap).onclick=()=>{closeOverlay('search-overlay');openNewManga(digits.length>=10?{isbn:digits}:{title:q})};
    return;
  }
  wrap.innerHTML=[
    ...volumes.map(volume=>`<button class="search-result" data-volume="${volume.id}"><img class="search-thumb fig-search-thumb" loading="lazy" src="${volumeThumb(volume)}" alt=""><div><b>${escapeHtml(volume.edition_name)} · ${escapeHtml(volumeLabel(volume))}</b><small>${escapeHtml([volume.variant,volume.publisher,volume.isbn,partialDate(volume.release_date)].filter(Boolean).join(' · '))}</small></div><span class="search-price">${volume.owned?`<span class="fig-owned-mark">×${volume.owned}</span>`:''}${volume.read?'<span class="mg-read-mark" title="Gelesen">✓</span>':''}</span></button>`),
    ...editions.map(edition=>`<button class="search-result" data-edition="${edition.id}"><img class="search-thumb fig-search-thumb" loading="lazy" src="${coverThumb(edition.cover,edition.series_id)}" alt=""><div><b>${escapeHtml(edition.name)}</b><small>${escapeHtml([edition.publisher,languageLabel(edition.language),edition.authors].filter(Boolean).join(' · '))}</small></div><span class="search-price">${edition.owned?`<span class="fig-owned-mark">${edition.owned}/${edition.total||'?'}</span>`:''}${edition.wished?'♥':''}</span></button>`),
  ].join('');
  $$('.search-result',wrap).forEach(el=>el.onclick=()=>{closeOverlay('search-overlay');el.dataset.volume?openVolume(Number(el.dataset.volume)):openEdition(Number(el.dataset.edition))});
}

// Light, dark or what the system uses. The resolved choice is also kept in a cookie: the login
// page and the first paint of the app read it before any settings have loaded.
const systemDark=globalThis.matchMedia?.('(prefers-color-scheme: dark)');
const appearancePreference=()=>['light','dark','auto'].includes(state.boot?.settings?.mobileThemeAppearance)?state.boot.settings.mobileThemeAppearance:'dark';
function applyAppearance(){
  const preference=appearancePreference();
  const light=preference==='light'||(preference==='auto'&&!systemDark?.matches);
  document.body.classList.toggle('mobile-light',light);
  document.cookie=`ophir_mangas_theme=${light?'light':'dark'};path=/;max-age=31536000;samesite=lax`;
}
systemDark?.addEventListener?.('change',()=>{if(state.boot&&appearancePreference()==='auto')applyAppearance()});
