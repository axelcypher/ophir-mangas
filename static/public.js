// The public profile (templates/public.html, ophir_mangas/public_profile.py): a shared collection
// without signing in. Its own small script -- the app's scripts expect a signed-in user. The
// address says what is shown: #wishlist for the shared wishlist, otherwise the collection.

const view=document.getElementById('content');
const slug=view.dataset.slug;
// The path the app is served under ('' at the root, e.g. /mangas behind a proxy), from <html data-root>.
const root=document.documentElement.dataset.root||'';
const base=`${root}/u/${encodeURIComponent(slug)}`;
const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const number=value=>Number(value||0).toLocaleString('de-DE');
const count=(value,one,many)=>`${number(value)} ${Number(value)===1?one:many}`;
const MONTHS=['Januar','Februar','März','April','Mai','Juni','Juli','August','September','Oktober','November','Dezember'];
const partialDate=value=>{if(!value)return '';const [year,month,day]=value.split('-');return day?`${day}.${month}.${year}`:month?`${MONTHS[Number(month)-1]} ${year}`:year};
const LANGUAGES={de:'Deutsch',ja:'Japanisch',en:'Englisch',fr:'Französisch',it:'Italienisch',es:'Spanisch',ko:'Koreanisch',zh:'Chinesisch'};
const READING={reading:'Lese ich',planned:'Geplant',paused:'Pausiert',finished:'Fertig',dropped:'Abgebrochen'};
const language=code=>LANGUAGES[code]||(code||'').toUpperCase();
const filters={q:'',language:'',publisher:''};
let profile=null;

// A picture the profile shows: an edition's cover (a volume's or the series'), a volume's cover.
const picture=(kind,id,version,full=false)=>`${base}/images/${kind}/${id}${full?'?size=full':''}${version?`${full?'&':'?'}v=${esc(version)}`:''}`;
const cover=edition=>edition.cover?picture(edition.cover.kind,edition.cover.id,edition.cover.version):picture('series',edition.series_id,'');

const matches=(edition,query)=>{
  const fold=text=>String(text||'').toLowerCase().normalize('NFKD').replace(/\p{M}/gu,'');
  const words=fold(query).match(/[\p{L}\p{N}]+/gu)||[];
  const text=fold([edition.name,edition.series_title,edition.original_title,edition.authors,edition.genres,edition.publisher].join(' '));
  return words.every(word=>text.includes(word));
};

function tile(edition){
  const total=edition.total||0,owned=edition.owned||0;
  const progress=total?Math.min(100,Math.round(owned/total*100)):0;
  return `<article class="fig-tile mg-edition-tile${owned?' owned':''}" tabindex="0" data-edition="${edition.id}">
    <div class="fig-art"><img loading="lazy" decoding="async" src="${cover(edition)}" alt="">
      ${owned?`<div class="fig-marks"><span class="fig-mark owned">${owned}${total?`/${total}`:''}</span></div>`:''}</div>
    <div class="fig-meta"><b title="${esc(edition.name)}">${esc(edition.name)}</b><small>${esc([edition.publisher,language(edition.language)].filter(Boolean).join(' · '))||'&nbsp;'}</small>
      ${total&&owned?`<span class="mg-progress" role="img" aria-label="${owned} von ${total} Bänden"><i class="mg-progress-owned" style="--share:${progress}%"></i></span>`:''}
      ${edition.reading_status?`<span class="fig-note">${esc(READING[edition.reading_status]||edition.reading_status)}${edition.read?` · ${count(edition.read,'Band','Bände')} gelesen`:''}</span>`:''}</div>
  </article>`;
}

function showEdition(edition){
  const facts=[['Reihe',edition.series_title],['Originaltitel',edition.original_title],['Autor:innen',edition.authors],['Genres',edition.genres],['Verlag',edition.publisher],
    ['Sprache',language(edition.language)],['Format',edition.format],['Bände',edition.total?String(edition.total):'']].filter(([,value])=>value);
  const overlay=document.createElement('div');
  overlay.className='overlay';overlay.id='public-edition';
  overlay.innerHTML=`<div class="fig-dialog mg-edition-dialog" role="dialog" aria-modal="true"><button type="button" class="close-button fig-dialog-close" aria-label="Schließen">×</button>
    <div class="mg-edition-head"><img class="mg-edition-cover" src="${cover(edition)}" alt="">
      <div class="mg-edition-main"><span class="eyebrow">${esc([edition.publisher,language(edition.language)].filter(Boolean).join(' · ').toUpperCase())}</span><h2>${esc(edition.name)}</h2>
        <dl class="fig-facts">${facts.map(([label,value])=>`<div><dt>${label}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl></div></div>
    ${edition.volumes.length?`<h3 class="mg-section-title">${count(edition.volumes.length,'Band','Bände')} in der Sammlung</h3><div class="mg-slots">${edition.volumes.map(volume=>`<div class="mg-slot mg-slot-owned${volume.read?' mg-slot-read':''}">
      <span class="mg-slot-cover"><img loading="lazy" src="${picture('volumes',volume.id,volume.image_version)}" alt=""><span class="mg-slot-number${volume.number_label?'':' mg-slot-title'}">${esc(volume.number_label||volume.title||'Sonderband')}</span>${volume.read?'<span class="mg-slot-badge" aria-label="gelesen">✓</span>':''}</span>
      ${volume.variant?`<span class="mg-slot-variant owned">${esc(volume.variant)}</span>`:''}</div>`).join('')}</div>`:''}</div>`;
  const close=()=>{overlay.remove();document.body.style.overflow=''};
  overlay.onmousedown=event=>{if(event.target===overlay)close()};
  overlay.querySelector('.close-button').onclick=close;
  document.addEventListener('keydown',function onKey(event){if(event.key==='Escape'){close();document.removeEventListener('keydown',onKey)}});
  document.body.append(overlay);document.body.style.overflow='hidden';
}

function render(){
  const wishlist=location.hash==='#wishlist'&&profile.wishlist;
  const all=wishlist?profile.wishlist:profile.collection;
  let shown=all.filter(edition=>['language','publisher'].every(key=>!filters[key]||edition[key]===filters[key]));
  if(filters.q.trim())shown=shown.filter(edition=>matches(edition,filters.q));
  const select=(key,label,show=value=>value)=>{
    const values=[...new Set(all.map(edition=>edition[key]).filter(Boolean))].sort((a,b)=>show(a).localeCompare(show(b),'de'));
    return values.length>1?`<label class="fig-filter"><span>${label}</span><select class="select-control" data-filter="${key}"><option value="">Alle</option>${values.map(value=>`<option value="${esc(value)}" ${filters[key]===value?'selected':''}>${esc(show(value))}</option>`).join('')}</select></label>`:'';
  };
  const stats=profile.stats;
  view.innerHTML=`<section class="public-head"><div><span class="eyebrow">ÖFFENTLICHE SAMMLUNG</span><h1>${esc(profile.name)}</h1>
      <p>${count(stats.series,'Reihe','Reihen')} · ${count(stats.editions,'Ausgabe','Ausgaben')} · ${count(stats.volumes,'Band','Bände')}${stats.read!=null?` · ${count(stats.read,'Band','Bände')} gelesen`:''}</p></div></section>
    ${profile.wishlist?`<nav class="segmented public-games" aria-label="Ansicht"><button type="button" data-view="" class="${wishlist?'':'active'}">Sammlung</button><button type="button" data-view="#wishlist" class="${wishlist?'active':''}">Wunschliste <small>${profile.wishlist.length}</small></button></nav>`:''}
    <div class="fig-toolbar"><div class="fig-toolbar-row">
      <label class="fig-search"><span aria-hidden="true">⌕</span><input type="search" id="public-search" value="${esc(filters.q)}" placeholder="Titel, Autor:in, Verlag …" aria-label="Suchen"></label>
      ${select('language','Sprache',language)}${select('publisher','Verlag')}
    </div></div>
    ${shown.length?`<div class="fig-grid">${shown.map(tile).join('')}</div>`:`<div class="empty-state"><b>${all.length?'Nichts passt zur Suche':'Hier ist noch nichts'}</b></div>`}`;
  view.querySelectorAll('[data-view]').forEach(button=>button.onclick=()=>{history.replaceState(null,'',button.dataset.view||location.pathname);render()});
  view.querySelectorAll('[data-filter]').forEach(control=>control.onchange=()=>{filters[control.dataset.filter]=control.value;render()});
  const search=view.querySelector('#public-search');
  let timer;search.oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>{filters.q=search.value;render();const field=view.querySelector('#public-search');field.focus();field.setSelectionRange(field.value.length,field.value.length)},250)};
  const byId=new Map(all.map(edition=>[edition.id,edition]));
  view.querySelectorAll('[data-edition]').forEach(element=>{
    element.onclick=()=>showEdition(byId.get(Number(element.dataset.edition)));
    element.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();element.click()}};
  });
}

fetch(`${root}/api/public/${encodeURIComponent(slug)}`).then(async response=>{
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(data.error||`Fehler ${response.status}`);
  profile=data;render();
}).catch(error=>{view.innerHTML=`<div class="empty-state"><b>Die Sammlung konnte nicht geladen werden</b><span>${esc(error.message)}</span></div>`});
addEventListener('hashchange',()=>profile&&render());
