// What every manga view shares: tiles and grids of editions and volumes, the filter bar and groups,
// the edition dialog with its volumes in order, the volume dialog with its tabs, and the forms -- a
// series (with AniList), an edition, a volume (with the ISBN lookup), copies, preorders, wishes --
// and the way a new manga comes in (ISBN, barcode, link, by hand).

// ---- Tiles and grids --------------------------------------------------------------------------

const GRID_PAGE=180;
const HEART='<svg viewBox="0 0 24 24"><path d="M12 20.5s-7.5-4.6-9.8-9A5.4 5.4 0 0 1 12 6a5.4 5.4 0 0 1 9.8 5.5c-2.3 4.4-9.8 9-9.8 9Z"/></svg>';

const editionSubtitle=edition=>[edition.publisher,languageLabel(edition.language),edition.format].filter(Boolean).join(' · ');
const share=(part,whole)=>whole?Math.max(0,Math.min(100,Math.round(part/whole*100))):0;

// Owned and read of an edition as two bars in one: how much of it is on the shelf, how much read.
function progressBar(edition){
  const total=edition.total||edition.highest||0;
  if(!total&&!edition.owned)return '';
  const owned=share(edition.owned_numbers,total),read=share(edition.read_numbers,total);
  const title=`${edition.owned_numbers} von ${total||'?'} vorhanden · ${edition.read_numbers} gelesen`;
  return `<span class="mg-progress" title="${escapeHtml(title)}" role="img" aria-label="${escapeHtml(title)}"><i class="mg-progress-owned" style="--share:${owned}%"></i><i class="mg-progress-read" style="--share:${read}%"></i></span>`;
}

function editionTile(edition,{note='',badge=''}={}){
  const total=edition.total||edition.highest||0;
  const marks=[
    edition.owned?`<span class="fig-mark owned" title="Vorhanden">${edition.owned_numbers}${total?`/${total}`:''}</span>`:'',
    edition.collecting?'<span class="fig-mark mg-mark-collecting" title="Sammle ich">★</span>':'',
    edition.gap_count?`<span class="fig-mark mg-mark-gaps" title="Fehlende Bände">${edition.gap_count} fehlen</span>`:'',
    edition.preordered?'<span class="fig-mark preordered" title="Vorbestellt">VB</span>':'',
    badge,
  ].join('');
  const next=edition.next_release?`Bd. ${escapeHtml(edition.next_release.number_label||'?')} · ${escapeHtml(partialDate(edition.next_release.release_date))}`:'';
  return `<article class="fig-tile mg-edition-tile${edition.owned?' owned':''}" data-edition="${edition.id}" tabindex="0" aria-label="${escapeHtml(edition.name)}">
    <div class="fig-art"><img loading="lazy" decoding="async" src="${coverThumb(edition.cover,edition.series_id)}" alt="">
      <div class="fig-marks">${marks}</div>
      <button type="button" class="fig-heart${edition.edition_wished?' active':''}" data-wish-edition="${edition.id}" aria-pressed="${edition.edition_wished?'true':'false'}" title="${edition.edition_wished?'Ganze Ausgabe auf der Wunschliste':'Ganze Ausgabe auf die Wunschliste'}">${HEART}</button>
      <button type="button" class="fig-plus" data-quick-next="${edition.id}" title="Den nächsten fehlenden Band zur Sammlung hinzufügen">＋</button>
    </div>
    <div class="fig-meta">
      <b title="${escapeHtml(edition.name)}">${escapeHtml(edition.name)}</b>
      <small>${escapeHtml(editionSubtitle(edition))||'&nbsp;'}</small>
      ${progressBar(edition)}
      ${note?`<span class="fig-note">${note}</span>`:next?`<span class="fig-note mg-next">Nächster: ${next}</span>`:''}
    </div>
  </article>`;
}

function volumeTile(volume,{note='',badge='',value=null}={}){
  const marks=[
    volume.owned?`<span class="fig-mark owned" title="In deiner Sammlung">×${volume.owned}</span>`:'',
    volume.read?'<span class="fig-mark mg-mark-read" title="Gelesen">✓</span>':'',
    volume.preordered?'<span class="fig-mark preordered" title="Vorbestellt">VB</span>':'',
    !volume.released?'<span class="fig-mark mg-mark-upcoming" title="Noch nicht erschienen">bald</span>':'',
    badge,
  ].join('');
  const title=`${volume.edition_name} · ${volumeLabel(volume)}`;
  const shownValue=value!==null?value:volume.market_value;
  return `<article class="fig-tile mg-volume-tile${volume.owned?' owned':''}" data-volume="${volume.id}" tabindex="0" aria-label="${escapeHtml(title)}">
    <div class="fig-art"><img loading="lazy" decoding="async" src="${volumeThumb(volume)}" alt="">
      <div class="fig-marks">${marks}</div>
      <button type="button" class="fig-heart${volume.wished?' active':''}" data-wish-volume="${volume.id}" aria-pressed="${volume.wished?'true':'false'}" title="${volume.wished?'Auf der Wunschliste':'Auf die Wunschliste'}">${HEART}</button>
      <button type="button" class="fig-plus" data-quick-add="${volume.id}" title="Ein Exemplar zur Sammlung hinzufügen">＋</button>
    </div>
    <div class="fig-meta">
      <b title="${escapeHtml(title)}">${escapeHtml(volume.edition_name)}</b>
      <small>${escapeHtml([volumeLabel(volume),volume.variant,partialDate(volume.release_date)].filter(Boolean).join(' · '))}</small>
      ${note?`<span class="fig-note">${note}</span>`:''}
      ${shownValue!=null&&shownValue!==0?`<span class="fig-value">${money(shownValue)}</span>`:''}
    </div>
  </article>`;
}

// Draws a grid in pages (a catalogue can hold thousands of entries); tile() makes one tile.
function renderGrid(container,items,{tile=editionTile,empty='<div class="empty-state"><b>Nichts gefunden</b><span>Ändere die Filter oder lege einen Manga an.</span></div>'}={}){
  state.gridItems=items;
  if(!items.length){container.innerHTML=empty;return}
  let shown=0;
  container.innerHTML='<div class="fig-grid"></div><div class="fig-grid-more"></div>';
  const grid=$('.fig-grid',container),more=$('.fig-grid-more',container);
  const page=()=>{
    grid.insertAdjacentHTML('beforeend',items.slice(shown,shown+GRID_PAGE).map(item=>tile(item)).join(''));
    shown=Math.min(items.length,shown+GRID_PAGE);
    more.innerHTML=shown<items.length?`<button type="button" class="secondary-button">Weitere ${Math.min(GRID_PAGE,items.length-shown)} von ${items.length-shown} anzeigen</button>`:'';
    const button=$('button',more);
    if(button){
      button.onclick=page;
      // Scrolling to the end loads the next page by itself.
      const observer=new IntersectionObserver(entries=>{if(entries.some(entry=>entry.isIntersecting)){observer.disconnect();page()}},{rootMargin:'600px'});
      observer.observe(button);
    }
  };
  page();
  wireGrid(grid);
}

function wireGrid(grid){
  grid.addEventListener('click',async event=>{
    const target=event.target;
    const actions=[
      ['[data-wish-edition]',element=>toggleEditionWish(Number(element.dataset.wishEdition),element)],
      ['[data-wish-volume]',element=>toggleVolumeWish(Number(element.dataset.wishVolume),element)],
      ['[data-quick-add]',element=>quickAddVolume(Number(element.dataset.quickAdd))],
      ['[data-quick-next]',element=>quickAddNext(Number(element.dataset.quickNext))],
    ];
    for(const [selector,act] of actions){
      const element=target.closest(selector);
      if(element){event.stopPropagation();await act(element);return}
    }
    const edition=target.closest('[data-edition]');
    if(edition){openEdition(Number(edition.dataset.edition));return}
    const volume=target.closest('[data-volume]');
    if(volume)openVolume(Number(volume.dataset.volume));
  });
  grid.addEventListener('keydown',event=>{
    if(!(event.key==='Enter'||event.key===' ')||!event.target.matches('.fig-tile'))return;
    event.preventDefault();
    event.target.dataset.edition?openEdition(Number(event.target.dataset.edition)):openVolume(Number(event.target.dataset.volume));
  });
}

function defaultListId(){return state.boot.watchlists.find(list=>list.is_default)?.id}

// The heart on a tile always means the default list: a whole edition, or one volume.
async function toggleWish(kind,id,button){
  const listId=defaultListId(),active=button?.classList.contains('active');
  const field=kind==='editions'?'edition_id':'volume_id';
  try{
    if(active){
      const result=await del(`/api/watchlists/${listId}/${kind}/${id}`);
      state.boot.watchlists=result.lists;
      toast('Von der Wunschliste genommen','Rückgängig',async()=>{await post(`/api/watchlists/${listId}/${kind}`,{[field]:id,...result.removed});afterChange()},'wish');
    }else{
      const result=await post(`/api/watchlists/${listId}/${kind}`,{[field]:id});
      state.boot.watchlists=result.lists;
      toast(kind==='editions'?'Ganze Ausgabe auf die Wunschliste gesetzt':'Auf die Wunschliste gesetzt',kind==='volumes'?'Zielpreis …':null,()=>openWishDialog('volumes',id),'wish');
    }
    if(button?.setAttribute){button.classList.toggle('active',!active);button.setAttribute('aria-pressed',String(!active))}
    refreshCounts();
    if(state.route==='watchlist')renderWatchlist(state.watchlistId);
    reloadDialogs();
  }catch(error){toast(error.message)}
}
const toggleEditionWish=(id,button)=>toggleWish('editions',id,button);
const toggleVolumeWish=(id,button)=>toggleWish('volumes',id,button);

async function quickAddVolume(volumeId){
  try{
    const entry=await post('/api/collection',{volume_id:volumeId,quantity:1});
    toast('Ein Exemplar hinzugefügt','Rückgängig',async()=>{await del(`/api/collection/${entry.id}`);afterChange()},'quick-add');
    afterChange();
  }catch(error){toast(error.message)}
}

async function setRead(volumeId,read){
  try{
    const result=read?await api(`/api/volumes/${volumeId}/read`,{method:'PUT',body:'{}'}):await del(`/api/volumes/${volumeId}/read`);
    toast(read?(result.reading_status==='finished'?'Gelesen – die Reihe ist fertig gelesen':'Als gelesen markiert'):'Nicht mehr als gelesen markiert',null,null,'read');
    afterChange();
  }catch(error){toast(error.message)}
}

// "＋" on an edition: the first volume it lacks (a gap, else the next one out) goes into the collection;
// when the catalogue does not have that volume yet, its form opens.
async function quickAddNext(editionId){
  let edition;
  try{edition=await api(`/api/editions/${editionId}`)}catch(error){toast(error.message);return}
  const slot=edition.slots.find(item=>item.released&&!edition.volumes.some(volume=>volume.number===item.number&&volume.owned));
  const volume=slot&&edition.volumes.find(item=>slot.volumes[0]===item.id);
  if(volume){await quickAddVolume(volume.id);return}
  if(slot){openVolumeForm({edition_id:edition.id,number:slot.number_label,list_price:edition.list_price,currency:edition.currency},{edition});return}
  toast('Von dieser Ausgabe hast du alle erschienenen Bände.');
}

// ---- The filter bar ---------------------------------------------------------------------------

const SORT_LABELS={title:'Titel',added:'Hinzugefügt',release:'Neueste Erscheinung',next:'Nächster Band',progress:'Fortschritt',value:'Wert',
  publisher:'Verlag',wished:'Gewünscht seit'};
const FACET_LABELS={series:'Reihe',language:'Sprache',publisher:'Verlag',format:'Format',author:'Autor:in',genre:'Genre',demographic:'Zielgruppe',
  status:'Status',location:'Aufbewahrung',reading:'Lesestatus'};
// Values shown under another name than they are stored with.
const FACET_VALUE={language:languageLabel,demographic:demographicLabel,status:seriesStatusLabel};

// grouping: the view's state.grouping entry. While it shows groups, the bar sorts the groups and
// leaves out the filter by the field they are grouped by; with a group open, that filter is the group.
function filterBar({key,filters,facets={},modes=null,sorts=[],extraFacets=[],extra='',grouping=null,placeholder='Titel, Autor:in, Verlag, ISBN …'}){
  const overview=Boolean(grouping?.by&&grouping.by!=='volumes'&&!grouping.open),locked=grouping?.open?.by;
  const facetKeys=['language','publisher','format','author','genre','demographic','status',...extraFacets].filter(name=>facets[name]&&!(overview&&GROUP_FIELD[grouping.by]===name));
  const label=(name,value)=>(FACET_VALUE[name]||(text=>text))(value);
  const select=name=>{
    const options=facets[name]||[];
    if(!options.length&&!filters[name])return '';
    const none=filters[name]===NONE_VALUE?`<option value="${NONE_VALUE}" selected>Ohne ${FACET_LABELS[name]||name}</option>`:'';
    return `<label class="fig-filter"><span>${FACET_LABELS[name]||name}</span><select class="select-control" data-filter="${name}"><option value="">Alle</option>${none}${options.map(([value,count])=>`<option value="${escapeHtml(value)}" ${filters[name]===value?'selected':''}>${escapeHtml(label(name,value))} (${count})</option>`).join('')}</select></label>`;
  };
  const readingSelect=Object.hasOwn(filters,'reading')?`<label class="fig-filter"><span>Lesestatus</span><select class="select-control" data-filter="reading"><option value="">Alle</option>${Object.entries(state.boot.reading_statuses||{}).map(([value,text])=>`<option value="${value}" ${filters.reading===value?'selected':''}>${escapeHtml(text)}</option>`).join('')}<option value="none" ${filters.reading==='none'?'selected':''}>Ohne Lesestatus</option></select></label>`:'';
  return `<div class="fig-toolbar" data-filter-bar="${key}">
    <div class="fig-toolbar-row">
      <label class="fig-search"><span aria-hidden="true">⌕</span><input type="search" data-filter="q" value="${escapeHtml(filters.q||'')}" placeholder="${escapeHtml(placeholder)}" autocomplete="off" aria-label="Suchen"></label>
      ${modes?`<div class="segmented fig-modes" data-scroll-x>${modes.map(([value,text])=>`<button type="button" data-mode="${value}" class="${(filters.mode||'all')===value?'active':''}">${text}</button>`).join('')}</div>`:''}
      ${extra}
    </div>
    <div class="fig-toolbar-row fig-filter-row">
      ${facetKeys.map(select).join('')}${readingSelect}
      ${overview?`<label class="fig-filter"><span>Gruppen sortieren</span><select class="select-control" data-group-sort>${Object.entries(GROUP_SORT_LABELS).map(([value,text])=>`<option value="${value}" ${grouping.sort===value?'selected':''}>${text}</option>`).join('')}</select></label>`
        :`<label class="fig-filter"><span>Sortierung</span><select class="select-control" data-filter="sort">${sorts.map(value=>`<option value="${value}" ${filters.sort===value?'selected':''}>${SORT_LABELS[value]||value}</option>`).join('')}</select></label>
      <button type="button" class="icon-button fig-direction" data-direction title="Reihenfolge umkehren" aria-label="Reihenfolge umkehren">${(filters.direction||defaultDirection(filters.sort))==='asc'?'↑':'↓'}</button>`}
      ${Object.entries(filters).some(([name,value])=>value&&!['sort','direction','mode',locked&&GROUP_FIELD[locked]].includes(name))?'<button type="button" class="link-button" data-filter-reset>Filter zurücksetzen</button>':''}
    </div>
  </div>`;
}
const defaultDirection=sort=>['title','publisher','next'].includes(sort)?'asc':'desc';

// Wires a filter bar: every change updates `filters` and calls render(); typing waits for a pause.
function wireFilterBar(root,filters,render,reset){
  const bar=$('[data-filter-bar]',root);if(!bar)return;
  let timer;
  $$('[data-filter]',bar).forEach(control=>{
    const apply=()=>{filters[control.dataset.filter]=control.value;if(control.dataset.filter==='sort')filters.direction='';render()};
    if(control.dataset.filter==='q')control.oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>reRenderPreservingFocus('[data-filter="q"]',async()=>{filters.q=control.value;await render()}),250)};
    else control.onchange=apply;
  });
  $$('[data-mode]',bar).forEach(button=>button.onclick=()=>{filters.mode=button.dataset.mode;render()});
  $('[data-direction]',bar)?.addEventListener('click',()=>{filters.direction=(filters.direction||defaultDirection(filters.sort))==='asc'?'desc':'asc';render()});
  $('[data-filter-reset]',bar)?.addEventListener('click',()=>{reset();render()});
}
const filterQuery=filters=>new URLSearchParams(Object.entries(filters).filter(([,value])=>value!==''&&value!=null)).toString();

// ---- Groups: editions side by side by series, publisher, author, genre, language ---------------

const GROUPINGS=[['series','Reihe','Reihen'],['publisher','Verlag','Verlage'],['author','Autor:in','Autor:innen'],['genre','Genre','Genres'],
  ['language','Sprache','Sprachen'],['demographic','Zielgruppe','Zielgruppen']];
// The filter that opens a group of each kind (the series is a filter by the series' title).
const GROUP_FIELD={series:'series',publisher:'publisher',author:'author',genre:'genre',language:'language',demographic:'demographic'};
const GROUP_SORT_LABELS={name:'Name',count:'Anzahl Ausgaben',owned:'Anteil in der Sammlung',value:'Wert',release:'Neueste Erscheinung'};
// A filter value for the entries without a value in that field (listing.py NONE_VALUE).
const NONE_VALUE='__none__';
const groupingLabel=(by,many=false)=>GROUPINGS.find(([key])=>key===by)?.[many?2:1]||'';
const groupValueLabel=(by,name)=>(FACET_VALUE[GROUP_FIELD[by]]||(text=>text))(name);
const groupName=(by,name)=>name?groupValueLabel(by,name):`Ohne ${groupingLabel(by)}`;

// The kind each grid was last shown in comes back with the user's settings.
function restoreGroupings(saved){
  if(!saved||typeof saved!=='object')return;
  for(const [view,by] of Object.entries(saved)){
    if(state.grouping[view]&&(by===''||by==='volumes'||GROUPINGS.some(([key])=>key===by)))state.grouping[view].by=by;
  }
}

// What a grid asks the server for: its filters and, while it shows groups, their kind and order.
function gridQuery(filters,grouping){
  const query=filterQuery(filters);
  if(grouping.by==='volumes')return `${query}${query?'&':''}level=volumes`;
  return grouping.by&&!grouping.open?`${query}${query?'&':''}group=${grouping.by}&group_sort=${grouping.sort}`:query;
}

// A filter changed in the bar may have moved off the open group: the select of the grouped field
// then picks another group, or with "Alle" goes back to the groups.
function syncOpenGroup(filters,grouping){
  const open=grouping.open;
  if(!open)return;
  const value=filters[GROUP_FIELD[open.by]]||'';
  if(value===(open.name||NONE_VALUE))return;
  grouping.open=value?{by:open.by,name:value===NONE_VALUE?'':value}:null;
}

function groupSwitch(view){
  const grouping=state.grouping[view];
  const button=(key,label)=>`<button type="button" role="tab" aria-selected="${grouping.by===key}" data-group-by="${key}" class="${grouping.by===key?'active':''}">${label}</button>`;
  return `<div class="segmented fig-group-switch" role="tablist" aria-label="Anzeigen als" data-scroll-x>${button('','Ausgaben')}${button('volumes','Bände')}${GROUPINGS.map(([key,label])=>button(key,label)).join('')}</div>`;
}

// Wires the switch, the group sort and the way back. Leaving an open group drops its filter.
function wireGroups(root,view,filters,render){
  const grouping=state.grouping[view];
  const close=()=>{if(grouping.open){filters[GROUP_FIELD[grouping.open.by]]='';grouping.open=null}};
  $$('[data-group-by]',root).forEach(button=>button.onclick=()=>{
    close();grouping.by=button.dataset.groupBy;
    // A sort of one level means nothing on the other.
    if(grouping.by==='volumes'&&!['title','release','added','value','wished'].includes(filters.sort))filters.sort='title';
    saveSettingSoon('groupings',Object.fromEntries(Object.entries(state.grouping).map(([key,value])=>[key,value.by])));
    render();
  });
  $('[data-group-sort]',root)?.addEventListener('change',event=>{grouping.sort=event.target.value;render()});
  $('[data-group-back]',root)?.addEventListener('click',()=>{close();render()});
}

function openGroup(view,filters,name,render){
  const grouping=state.grouping[view];
  grouping.open={by:grouping.by,name};
  filters[GROUP_FIELD[grouping.by]]=name||NONE_VALUE;
  render();
  window.scrollTo({top:0});
}

// The head over an open group's editions: the way back, the group and its numbers.
function groupHead(view,{count,owned=null,actions=''}){
  const {by,open}=state.grouping[view];
  const back=`Zurück zu allen ${groupingLabel(by,true)}`;
  return `<div class="fig-group-head">
    <button type="button" class="icon-button fig-group-back" data-group-back title="${back}" aria-label="${back}">←</button>
    <div class="fig-group-title"><span class="eyebrow">${escapeHtml(groupingLabel(by).toUpperCase())}</span><h2>${escapeHtml(groupName(by,open.name))}</h2>
      <small>${[plural(count,'Ausgabe','Ausgaben'),owned!=null?`${owned} in der Sammlung`:''].filter(Boolean).join(' · ')}</small></div>
    ${actions?`<div class="fig-group-actions">${actions}</div>`:''}
  </div>`;
}

// One group: up to four of its editions' covers as a mosaic, its name and numbers. stats(group)
// gives the lines under the name and, optionally, a share (0 to 1) for the bar.
function groupTile(by,group,stats){
  const {lines,share:part=null}=stats(group,by);
  const name=groupName(by,group.name);
  const samples=group.samples.length?group.samples:[null];
  return `<article class="fig-group-tile${group.name?'':' fig-group-none'}" data-group="${escapeHtml(group.name)}" tabindex="0" role="button" aria-label="${escapeHtml(name)} öffnen">
    <div class="fig-group-art" data-count="${samples.length}">${samples.map(sample=>sample?`<img loading="lazy" decoding="async" src="${coverThumb(sample.cover,sample.series_id)}" alt="">`:'<span></span>').join('')}</div>
    <div class="fig-group-meta">
      <b title="${escapeHtml(name)}">${escapeHtml(name)}</b>
      ${lines.filter(Boolean).map(line=>`<small>${line}</small>`).join('')}
      ${part!=null?`<span class="fig-group-share" title="${Math.round(part*100)} % in der Sammlung"><i style="--share:${Math.round(part*100)}%"></i></span>`:''}
    </div>
  </article>`;
}

const GROUP_MISSING={series:'eine Reihe',publisher:'einen Verlag',author:'eine Autorin oder einen Autor',genre:'ein Genre',language:'eine Sprache',demographic:'eine Zielgruppe'};

function renderGroupGrid(container,view,groups,{stats,empty,onOpen}){
  const by=state.grouping[view].by;
  if(!groups.length){container.innerHTML=empty;return}
  const unnamed=groups.length===1&&!groups[0].name;
  container.innerHTML=`${unnamed?`<div class="fig-hint"><b>Noch keine dieser Ausgaben hat ${GROUP_MISSING[by]}.</b><span>Trag es bei der Reihe oder Ausgabe ein.</span></div>`:''}
    <div class="fig-group-grid">${groups.map(group=>groupTile(by,group,stats)).join('')}</div>`;
  const grid=$('.fig-group-grid',container);
  grid.addEventListener('click',event=>{const tile=event.target.closest('[data-group]');if(tile)onOpen(tile.dataset.group)});
  grid.addEventListener('keydown',event=>{if((event.key==='Enter'||event.key===' ')&&event.target.matches('[data-group]')){event.preventDefault();onOpen(event.target.dataset.group)}});
}

// ---- The edition dialog: its volumes in order -----------------------------------------------

async function openEdition(editionId){
  let edition;
  try{edition=await api(`/api/editions/${editionId}`)}catch(error){toast(error.message);return}
  state.modalEdition=edition;
  paintEdition();
  openOverlay('edition-modal');
}

async function reloadEdition(){
  if(!state.modalEdition)return;
  try{state.modalEdition=await api(`/api/editions/${state.modalEdition.id}`);paintEdition()}catch(error){toast(error.message)}
}

function factRow(label,value){return value?`<div><dt>${label}</dt><dd>${value}</dd></div>`:''}
const hostOf=url=>{try{return new URL(url).hostname}catch{return url}};

// One number of an edition: its volume's cover (variants beside it), what the account has of it,
// and quick buttons to own or read it; a number the catalogue lacks as an empty place to create it.
function slotHtml(slot,byId,label=slot.number_label){
  const volumes=slot.volumes.map(id=>byId.get(id)).filter(Boolean);
  if(!volumes.length){
    return `<div class="mg-slot mg-slot-missing${slot.gap?' mg-slot-gap':''}${slot.released?'':' mg-slot-later'}">
      <button type="button" class="mg-slot-empty" data-slot-create="${escapeHtml(slot.number_label)}" title="Band ${escapeHtml(slot.number_label)} ist nicht im Katalog – anlegen">
        <b>${escapeHtml(slot.number_label)}</b><small>${slot.gap?'fehlt':'nicht im Katalog'}</small></button>
    </div>`;
  }
  const [main,...variants]=volumes;
  const owned=volumes.some(volume=>volume.owned),read=volumes.some(volume=>volume.read);
  const classes=['mg-slot',owned?'mg-slot-owned':'',read?'mg-slot-read':'',slot.gap?'mg-slot-gap':'',main.released?'':'mg-slot-later',
    volumes.some(volume=>volume.preordered)?'mg-slot-preordered':'',volumes.some(volume=>volume.wished)?'mg-slot-wished':''].filter(Boolean).join(' ');
  const facts=[owned?'vorhanden':slot.gap?'fehlt':'',read?'gelesen':'',main.released?'':`erscheint ${partialDate(main.release_date)}`].filter(Boolean).join(', ');
  const name=label?`Band ${label}`:volumeLabel(main);
  return `<div class="${classes}">
    <button type="button" class="mg-slot-cover" data-volume="${main.id}" title="${escapeHtml(`${name}${facts?` – ${facts}`:''}`)}">
      <img loading="lazy" decoding="async" src="${volumeThumb(main)}" alt="">
      <span class="mg-slot-number${label?'':' mg-slot-title'}">${escapeHtml(label||main.title||'Sonderband')}</span>
      ${read?'<span class="mg-slot-badge" aria-hidden="true">✓</span>':''}
      ${!main.released?`<span class="mg-slot-date">${escapeHtml(partialDate(main.release_date))}</span>`:''}
    </button>
    ${variants.map(variant=>`<button type="button" class="mg-slot-variant${variant.owned?' owned':''}" data-volume="${variant.id}" title="${escapeHtml(variant.variant||'Variante')}">+ ${escapeHtml(variant.variant||'Variante')}</button>`).join('')}
    <span class="mg-slot-actions">
      <button type="button" class="mg-slot-action${owned?' active':''}" data-slot-own="${main.id}" aria-pressed="${owned}" title="${owned?'In der Sammlung':'Zur Sammlung hinzufügen'}" aria-label="${escapeHtml(name)} ${owned?'ist in der Sammlung':'zur Sammlung hinzufügen'}">＋</button>
      <button type="button" class="mg-slot-action${read?' active':''}" data-slot-read="${main.id}" aria-pressed="${read}" title="${read?'Gelesen – nicht mehr als gelesen markieren':'Als gelesen markieren'}" aria-label="${escapeHtml(name)} ${read?'ist gelesen':'als gelesen markieren'}">✓</button>
    </span>
  </div>`;
}

function paintEdition(){
  const edition=state.modalEdition,dialog=$('#edition-dialog');
  if(!edition)return;
  const byId=new Map(edition.volumes.map(volume=>[volume.id,volume]));
  const specials=edition.special_ids.map(id=>byId.get(id)).filter(Boolean);
  const total=edition.total||edition.highest;
  const statuses=Object.entries(state.boot.reading_statuses||{});
  const chips=[
    `<span class="fig-chip${edition.owned?' owned':''}">${edition.owned_numbers} von ${total||'?'} vorhanden</span>`,
    edition.read?`<span class="fig-chip mg-chip-read">${plural(edition.read,'Band','Bände')} gelesen</span>`:'',
    edition.collecting&&edition.gap_count?`<span class="fig-chip mg-chip-gaps">${plural(edition.gap_count,'Lücke','Lücken')}</span>`:'',
    edition.next_release?`<span class="fig-chip">Nächster: Bd. ${escapeHtml(edition.next_release.number_label||'?')} · ${escapeHtml(partialDate(edition.next_release.release_date))}</span>`:'',
    edition.edition_wished?'<span class="fig-chip wished">♥ Ganze Ausgabe gewünscht</span>':'',
    edition.value?`<span class="fig-chip">Wert ${money(edition.value)}</span>`:'',
  ].join('');
  dialog.innerHTML=`<button type="button" class="close-button fig-dialog-close" data-close="edition-modal" aria-label="Schließen">×</button>
    <div class="mg-edition-head">
      <img class="mg-edition-cover" src="${coverThumb(edition.cover,edition.series_id)}" alt="">
      <div class="mg-edition-main">
        <span class="eyebrow">${escapeHtml([edition.publisher,languageLabel(edition.language),edition.format,seriesStatusLabel(edition.status)].filter(Boolean).join(' · ').toUpperCase()||'AUSGABE')}</span>
        <h2>${escapeHtml(edition.name)}</h2>
        <p class="fig-original">${escapeHtml([edition.series.original_title,edition.series.authors].filter(Boolean).join(' · '))}</p>
      </div>
      <div class="fig-chips">${chips}</div>
      <div class="fig-actions mg-edition-actions">
          <button type="button" class="${edition.collecting?'primary-button':'secondary-button'}" data-edition-action="collect" aria-pressed="${edition.collecting}">${edition.collecting?'★ Sammle ich':'☆ Sammle ich'}</button>
          <select class="select-control mg-reading-select" data-edition-reading aria-label="Lesestatus der Reihe"><option value="">Kein Lesestatus</option>${statuses.map(([key,label])=>`<option value="${key}" ${edition.reading_status===key?'selected':''}>${escapeHtml(label)}</option>`).join('')}</select>
          <button type="button" class="secondary-button" data-edition-action="own">Bände besitze ich …</button>
          <button type="button" class="secondary-button" data-edition-action="read">Gelesen bis …</button>
          <button type="button" class="secondary-button${edition.edition_wished?' active':''}" data-edition-action="wish">${edition.edition_wished?'♥ Gewünscht':'♡ Wunschliste'}</button>
          <button type="button" class="secondary-button" data-edition-action="new-volume">＋ Band</button>
          <button type="button" class="secondary-button" data-edition-action="edit">Bearbeiten</button>
      </div>
    </div>
    <div class="mg-slot-legend" aria-hidden="true"><span class="mg-legend-owned">vorhanden</span><span class="mg-legend-read">gelesen</span>${edition.collecting?'<span class="mg-legend-gap">fehlt</span>':''}<span class="mg-legend-later">erscheint</span></div>
    ${edition.slots.length?`<div class="mg-slots">${edition.slots.map(slot=>slotHtml(slot,byId)).join('')}</div>`
      :'<div class="fig-empty-soft">Noch kein Band dieser Ausgabe im Katalog. Leg den ersten an – am schnellsten mit der ISBN – oder trage die Bandanzahl der Ausgabe ein.</div>'}
    ${specials.length?`<h3 class="mg-section-title">Sonderbände</h3><div class="mg-slots">${specials.map(volume=>slotHtml({number_label:'',volumes:[volume.id],released:volume.released,gap:false},byId,'')).join('')}</div>`:''}
    <div class="mg-edition-more">
      <dl class="fig-facts">
        ${factRow('Reihe',`<button type="button" class="link-button" data-edition-action="series">${escapeHtml(edition.series.title)}</button>`)}
        ${factRow('Autor:innen',escapeHtml(edition.series.authors))}
        ${factRow('Genres',escapeHtml(edition.series.genres))}
        ${factRow('Zielgruppe',escapeHtml(demographicLabel(edition.series.demographic)))}
        ${factRow('Bände',edition.volume_count?`${edition.volume_count}${edition.status==='completed'?' (abgeschlossen)':''}`:'')}
        ${factRow('Listenpreis',edition.list_price!=null?escapeHtml(currencyMoney(edition.list_price,edition.currency)):'')}
        ${factRow('Original',edition.series.original_volumes?`${edition.series.original_volumes} Bände${edition.series.status?` · ${escapeHtml(seriesStatusLabel(edition.series.status))}`:''}`:'')}
        ${factRow('Quelle',edition.source_url?`<a href="${escapeHtml(edition.source_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(hostOf(edition.source_url))}</a>`:'')}
        ${factRow('Sammler',edition.owners?plural(edition.owners,'Konto hat Bände','Konten haben Bände'):'')}
      </dl>
      ${edition.other_editions.length?`<div class="mg-other-editions"><h3 class="mg-section-title">Andere Ausgaben der Reihe</h3>${edition.other_editions.map(other=>`<button type="button" class="mg-other-edition" data-open-edition="${other.id}"><img src="${coverThumb(other.cover,edition.series_id)}" alt=""><span><b>${escapeHtml(other.name)}</b><small>${escapeHtml([other.publisher,languageLabel(other.language)].filter(Boolean).join(' · '))}${other.owned?` · ${other.owned}/${other.total||'?'}`:''}</small></span></button>`).join('')}</div>`:''}
      ${edition.can_delete?'<button type="button" class="secondary-button danger" data-edition-action="delete">Ausgabe aus dem Katalog löschen</button>':''}
    </div>`;
  $$('[data-close="edition-modal"]',dialog).forEach(button=>button.onclick=()=>closeOverlay('edition-modal'));
  $$('[data-edition-action]',dialog).forEach(button=>button.onclick=()=>editionAction(button.dataset.editionAction));
  $$('[data-volume]',dialog).forEach(button=>button.onclick=()=>openVolume(Number(button.dataset.volume)));
  $$('[data-slot-create]',dialog).forEach(button=>button.onclick=()=>openVolumeForm({edition_id:edition.id,number:button.dataset.slotCreate,list_price:edition.list_price,currency:edition.currency},{edition}));
  $$('[data-slot-own]',dialog).forEach(button=>button.onclick=async event=>{
    event.stopPropagation();
    const volume=byId.get(Number(button.dataset.slotOwn));
    if(volume.owned)openVolume(volume.id,'copies');else await quickAddVolume(volume.id);
  });
  $$('[data-slot-read]',dialog).forEach(button=>button.onclick=event=>{event.stopPropagation();const volume=byId.get(Number(button.dataset.slotRead));setRead(volume.id,!volume.read)});
  $$('[data-open-edition]',dialog).forEach(button=>button.onclick=()=>openEdition(Number(button.dataset.openEdition)));
  $('[data-edition-reading]',dialog).onchange=async event=>{
    try{await api(`/api/series/${edition.series_id}/reading`,{method:'PUT',body:JSON.stringify({status:event.target.value})});toast(event.target.value?`Lesestatus: ${readingLabel(event.target.value)}`:'Kein Lesestatus mehr');afterChange()}
    catch(error){toast(error.message)}
  };
}

async function editionAction(action){
  const edition=state.modalEdition;
  if(action==='collect'){
    try{
      await api(`/api/editions/${edition.id}/collecting`,{method:edition.collecting?'DELETE':'PUT',body:'{}'});
      toast(edition.collecting?'Sammelst du nicht mehr – keine Lücken und Termine mehr dafür':'Sammle ich – Lücken und Neuerscheinungen werden verfolgt');
      afterChange();
    }catch(error){toast(error.message)}
  }
  if(action==='wish')toggleEditionWish(edition.id,{classList:{contains:()=>edition.edition_wished}});
  if(action==='new-volume')openNextVolumeForm(edition);
  if(action==='edit')openEditionForm(edition,{editionId:edition.id,series:edition.series});
  if(action==='series')openSeriesDialog(edition.series_id);
  if(action==='own')openOwnRange(edition);
  if(action==='read')openReadThrough(edition);
  if(action==='delete'){
    if(!confirm(`„${edition.name}“ mit allen Bänden endgültig aus dem Katalog löschen?`))return;
    try{await del(`/api/editions/${edition.id}`);closeOverlay('edition-modal');toast('Ausgabe gelöscht');refreshCounts();refreshCurrentView()}catch(error){toast(error.message)}
  }
}

async function openNextVolumeForm(edition){
  try{
    const next=await api(`/api/editions/${edition.id}/next-volume`);
    openVolumeForm({...next,edition_id:edition.id},{edition});
  }catch(error){toast(error.message)}
}

// "1-12, 14, 20.5" -> [1, ..., 12, 14, 20.5]; null for anything else.
function parseNumbers(text){
  const numbers=new Set();
  for(const part of String(text).split(/[,;\s]+/).filter(Boolean)){
    const range=part.match(/^(\d{1,4})[-–](\d{1,4})$/);
    if(range){
      const [from,to]=[Number(range[1]),Number(range[2])].sort((a,b)=>a-b);
      if(to-from>500)return null;
      for(let number=from;number<=to;number++)numbers.add(number);
    }else if(/^\d{1,4}([.,]\d{1,2})?$/.test(part))numbers.add(Number(part.replace(',','.')));
    else return null;
  }
  return [...numbers].sort((a,b)=>a-b);
}

// [1,2,3,5,7,8] -> "1-3, 5, 7-8"
function compactNumbers(numbers){
  const parts=[];let start=null,previous=null;
  for(const number of numbers){
    if(start!==null&&Number.isInteger(number)&&number===previous+1){previous=number;continue}
    if(start!==null)parts.push(start===previous?`${start}`:`${start}-${previous}`);
    start=previous=number;
  }
  if(start!==null)parts.push(start===previous?`${start}`:`${start}-${previous}`);
  return parts.join(', ');
}

// Owning many volumes of an edition at once, e.g. bringing an existing shelf in: the numbers the
// catalogue lacks are created first, then a copy of each standard volume is added.
function openOwnRange(edition){
  const owned=new Set(edition.volumes.filter(volume=>volume.owned).map(volume=>volume.number));
  const missing=edition.slots.filter(slot=>slot.released&&!owned.has(slot.number)).map(slot=>slot.number);
  const conditions=Object.entries(state.boot.conditions);
  const modal=openDialog({id:'own-range',eyebrow:'SAMMLUNG',title:'Welche Bände besitzt du?',intro:escapeHtml(edition.name),stack:true,body:`
    <div class="dl-grid">
      <label class="dl-field dl-field-wide"><span>Bände</span><input class="dl-control" data-field="numbers" placeholder="z. B. 1-12, 14" value="${escapeHtml(compactNumbers(missing))}" autocomplete="off"></label>
      <label class="dl-field"><span>Zustand</span><select class="dl-control" data-field="condition">${conditions.map(([key,label])=>`<option value="${key}">${escapeHtml(label)}</option>`).join('')}</select></label>
      <label class="dl-field"><span>Kaufpreis je Band (€)</span><input class="dl-control" data-field="purchase_price" inputmode="decimal" placeholder="optional" value="${edition.currency==='EUR'?amountValue(edition.list_price):''}"></label>
      <label class="dl-field"><span>Shop</span><input class="dl-control" data-field="shop" placeholder="optional"></label>
      <label class="dl-field"><span>Aufbewahrung</span><input class="dl-control" data-field="location" placeholder="z. B. Regal 2"></label>
    </div>
    <p class="muted">Bände, die noch nicht im Katalog sind, werden mit dem Listenpreis der Ausgabe angelegt. Was du schon hast, bekommt kein zweites Exemplar.</p>
    <div class="dl-modal-actions"><button type="button" class="secondary-button" data-dialog-close>Abbrechen</button><span class="spacer"></span><button type="button" class="primary-button" id="own-range-save">Hinzufügen</button></div>`});
  $$('[data-dialog-close]',modal).forEach(button=>button.onclick=closeDialog);
  $('#own-range-save',modal).onclick=async()=>{
    const {numbers,...fields}=fieldValues(modal);
    const wanted=parseNumbers(numbers);
    if(!wanted?.length){toast('Bitte Bandnummern angeben, z. B. 1-12, 14.');return}
    try{
      const catalogued=new Set(edition.volumes.map(volume=>volume.number));
      for(const number of wanted.filter(number=>!catalogued.has(number))){
        if(Number.isInteger(number))await post(`/api/editions/${edition.id}/volumes`,{from:number,to:number});
        else await post('/api/volumes',{edition_id:edition.id,number});
      }
      const fresh=await api(`/api/editions/${edition.id}`);
      const ids=wanted.filter(number=>!owned.has(number)).map(number=>fresh.volumes.find(volume=>volume.number===number&&!volume.variant)?.id).filter(Boolean);
      if(!ids.length){closeDialog();toast('Die hast du alle schon.');return}
      await post('/api/collection',{volume_ids:ids,...fields});
      closeDialog();toast(`${plural(ids.length,'Band','Bände')} zur Sammlung hinzugefügt`);afterChange();
    }catch(error){toast(error.message)}
  };
}

function openReadThrough(edition){
  const read=edition.volumes.filter(volume=>volume.read&&volume.number!=null).map(volume=>volume.number);
  const modal=openDialog({id:'read-through',eyebrow:'LESEN',title:'Gelesen bis Band …',intro:escapeHtml(edition.name),stack:true,body:`
    <div class="dl-grid"><label class="dl-field dl-field-wide"><span>Bis einschließlich Band</span><input class="dl-control" data-field="through" inputmode="decimal" value="${read.length?Math.max(...read):''}" placeholder="z. B. 12; 0 = nichts gelesen"></label></div>
    <p class="muted">Alle Bände bis dahin gelten als gelesen, die danach als ungelesen. Sonderbände bleiben, wie sie sind.</p>
    <div class="dl-modal-actions"><button type="button" class="secondary-button" data-dialog-close>Abbrechen</button><span class="spacer"></span><button type="button" class="primary-button" id="read-through-save">Übernehmen</button></div>`});
  $$('[data-dialog-close]',modal).forEach(button=>button.onclick=closeDialog);
  $('#read-through-save',modal).onclick=async()=>{
    try{
      const result=await post(`/api/editions/${edition.id}/read`,{through:fieldValues(modal).through});
      closeDialog();toast(result.reading_status==='finished'?'Fertig gelesen – Glückwunsch!':`Gelesen bis Band ${result.through}`);afterChange();
    }catch(error){toast(error.message)}
  };
}

// ---- The series dialog: the work and its editions ----------------------------------------------

async function openSeriesDialog(seriesId){
  let series;
  try{series=await api(`/api/series/${seriesId}`)}catch(error){toast(error.message);return}
  const statuses=Object.entries(state.boot.reading_statuses||{});
  const modal=openDialog({id:'series-dialog',eyebrow:'REIHE',title:escapeHtml(series.title),wide:true,stack:true,
    intro:escapeHtml([series.original_title,series.authors].filter(Boolean).join(' · ')),body:`
    <div class="mg-series-head">
      <img class="mg-edition-cover" src="${seriesThumb(series)}" alt="">
      <div>
        <dl class="fig-facts">
          ${factRow('Andere Titel',escapeHtml(series.alt_titles))}
          ${factRow('Genres',escapeHtml(series.genres))}
          ${factRow('Zielgruppe',escapeHtml(demographicLabel(series.demographic)))}
          ${factRow('Im Original',[series.original_volumes?`${series.original_volumes} Bände`:'',series.status?seriesStatusLabel(series.status):'',series.start_year||''].filter(Boolean).map(escapeHtml).join(' · '))}
          ${factRow('AniList',series.anilist_id?`<a href="https://anilist.co/manga/${series.anilist_id}" target="_blank" rel="noopener noreferrer">#${series.anilist_id}</a>`:'')}
        </dl>
        <label class="dl-field"><span>Lesestatus</span><select class="dl-control" id="series-reading"><option value="">Kein Lesestatus</option>${statuses.map(([key,label])=>`<option value="${key}" ${series.reading_status===key?'selected':''}>${escapeHtml(label)}</option>`).join('')}</select></label>
      </div>
    </div>
    ${series.description?`<p class="fig-description">${escapeHtml(series.description)}</p>`:''}
    <h3 class="mg-section-title">Ausgaben <small>${series.editions.length}</small></h3>
    <div class="mg-other-editions">${series.editions.map(edition=>`<button type="button" class="mg-other-edition" data-open-edition="${edition.id}"><img src="${coverThumb(edition.cover,series.id)}" alt=""><span><b>${escapeHtml(edition.name)}</b><small>${escapeHtml(editionSubtitle(edition))}${edition.owned?` · ${edition.owned_numbers}/${edition.total||'?'} vorhanden`:''}</small></span></button>`).join('')||'<p class="muted">Noch keine Ausgabe.</p>'}</div>
    <div class="dl-modal-actions">${series.can_delete?'<button type="button" class="secondary-button danger" id="series-delete">Reihe löschen</button>':''}<button type="button" class="secondary-button" id="series-image">Bild</button><span class="spacer"></span><button type="button" class="secondary-button" id="series-edit">Bearbeiten</button><button type="button" class="primary-button" id="series-new-edition">＋ Ausgabe</button></div>`});
  $$('[data-open-edition]',modal).forEach(button=>button.onclick=()=>{closeDialog();openEdition(Number(button.dataset.openEdition))});
  $('#series-reading',modal).onchange=async event=>{
    try{await api(`/api/series/${series.id}/reading`,{method:'PUT',body:JSON.stringify({status:event.target.value})});toast('Lesestatus gespeichert');afterChange()}catch(error){toast(error.message)}
  };
  $('#series-edit',modal).onclick=()=>openSeriesForm(series,{seriesId:series.id,onSaved:()=>{afterChange();openSeriesDialog(series.id)}});
  $('#series-image',modal).onclick=()=>openImageDialog('series',series);
  $('#series-new-edition',modal).onclick=()=>openEditionForm({series_id:series.id},{series,onSaved:edition=>{refreshCurrentView();openEdition(edition.id)}});
  $('#series-delete',modal)?.addEventListener('click',async()=>{
    if(!confirm(`„${series.title}“ mit allen Ausgaben und Bänden endgültig aus dem Katalog löschen?`))return;
    try{await del(`/api/series/${series.id}`);closeDialog();closeOverlay('edition-modal');toast('Reihe gelöscht');refreshCounts();refreshCurrentView()}catch(error){toast(error.message)}
  });
}

// ---- The volume dialog ---------------------------------------------------------------------------

async function openVolume(volumeId,tab){
  if(tab)state.modalTab=tab;
  let volume;
  try{volume=await api(`/api/volumes/${volumeId}`)}catch(error){toast(error.message);return}
  state.modalVolume=volume;
  paintVolume();
  openOverlay('volume-modal');
}

async function reloadVolume(){
  if(!state.modalVolume)return;
  try{state.modalVolume=await api(`/api/volumes/${state.modalVolume.id}`);paintVolume()}catch(error){toast(error.message)}
}

const VOLUME_TABS=[['copies','Exemplare'],['preorders','Vorbestellungen'],['value','Wert'],['lists','Wunschlisten'],['info','Info']];

function paintVolume(){
  const volume=state.modalVolume,dialog=$('#volume-dialog');
  if(!volume)return;
  const openPreorders=volume.preorders.filter(item=>['ordered','paid','shipped'].includes(item.status));
  const chips=[
    volume.owned?`<span class="fig-chip owned">${volume.owned}× in der Sammlung</span>`:'',
    volume.read?`<span class="fig-chip mg-chip-read">✓ Gelesen${volume.read_at?` am ${escapeHtml(partialDate(volume.read_at))}`:''}</span>`:'',
    openPreorders.length?`<span class="fig-chip preordered">Vorbestellt · ${statusLabel(openPreorders[0].status)}</span>`:'',
    volume.wished?'<span class="fig-chip wished">♥ Wunschliste</span>':'',
    !volume.released?`<span class="fig-chip">Erscheint ${escapeHtml(partialDate(volume.release_date))}</span>`:'',
    volume.market_value!=null?`<span class="fig-chip">Marktwert ${money(volume.market_value)}</span>`:'',
  ].join('');
  const tabs=VOLUME_TABS.map(([key,label])=>{
    const count={copies:volume.entries.length,preorders:volume.preorders.length,value:volume.prices.length,lists:volume.lists.length}[key];
    return `<button type="button" data-volume-tab="${key}" class="${state.modalTab===key?'active':''}">${label}${count?` <small>${count}</small>`:''}</button>`;
  }).join('');
  dialog.innerHTML=`<button type="button" class="close-button fig-dialog-close" data-close="volume-modal" aria-label="Schließen">×</button>
    <div class="fig-dialog-media">${volume.has_image?`<a href="${volumeImage(volume)}" target="_blank" rel="noopener" title="Cover in voller Größe"><img src="${volumeImage(volume)}" alt="${escapeHtml(volumeLabel(volume))}"></a>`:`<img src="${volumeImage(volume)}" alt="">`}
      <div class="fig-media-actions"><button type="button" class="secondary-button" data-volume-action="image">${volume.has_image?'Cover ändern':'Cover hinzufügen'}</button></div>
      <div class="mg-volume-nav">
        <button type="button" class="icon-button" data-volume-goto="${volume.previous_id??''}" ${volume.previous_id?'':'disabled'} title="Vorheriger Band" aria-label="Vorheriger Band">‹</button>
        <button type="button" class="link-button" data-volume-action="edition">Alle Bände</button>
        <button type="button" class="icon-button" data-volume-goto="${volume.next_id??''}" ${volume.next_id?'':'disabled'} title="Nächster Band" aria-label="Nächster Band">›</button>
      </div>
    </div>
    <div class="fig-dialog-main">
      <span class="eyebrow">${escapeHtml(volume.edition_name.toUpperCase())}</span>
      <h2>${escapeHtml(volumeLabel(volume))}${volume.variant?` <small class="mg-variant">${escapeHtml(volume.variant)}</small>`:''}</h2>
      ${volume.number_label&&volume.title?`<p class="fig-original">${escapeHtml(volume.title)}</p>`:''}
      ${chips?`<div class="fig-chips">${chips}</div>`:''}
      <div class="fig-actions">
        <button type="button" class="primary-button" data-volume-action="copy">＋ Exemplar</button>
        <button type="button" class="secondary-button${volume.read?' active':''}" data-volume-action="read" aria-pressed="${volume.read}">${volume.read?'✓ Gelesen':'Als gelesen markieren'}</button>
        <button type="button" class="secondary-button" data-volume-action="preorder">Vorbestellen</button>
        <button type="button" class="secondary-button${volume.wished?' active':''}" data-volume-action="wish">${volume.wished?'♥ Gewünscht':'♡ Wunschliste'}</button>
        <button type="button" class="secondary-button" data-volume-action="edit">Bearbeiten</button>
      </div>
      <dl class="fig-facts">
        ${factRow('Ausgabe',`${escapeHtml(volume.edition.name)} <small class="muted">${escapeHtml([volume.publisher,languageLabel(volume.language)].filter(Boolean).join(' · '))}</small>`)}
        ${factRow('Autor:innen',escapeHtml(volume.authors))}
        ${factRow('ISBN',escapeHtml(volume.isbn))}
        ${factRow('Erscheinung',escapeHtml(partialDate(volume.release_date)))}
        ${factRow('Listenpreis',volume.list_price!=null?escapeHtml(currencyMoney(volume.list_price,volume.currency)):'')}
        ${factRow('Seiten',volume.pages?String(volume.pages):'')}
      </dl>
      <div class="segmented fig-tabs" role="tablist" data-scroll-x>${tabs}</div>
      <div class="fig-tab-body" id="volume-tab-body">${volumeTabHtml(volume)}</div>
    </div>`;
  $$('[data-close="volume-modal"]',dialog).forEach(button=>button.onclick=()=>closeOverlay('volume-modal'));
  $$('[data-volume-tab]',dialog).forEach(button=>button.onclick=()=>{state.modalTab=button.dataset.volumeTab;paintVolume()});
  $$('[data-volume-action]',dialog).forEach(button=>button.onclick=()=>volumeAction(button.dataset.volumeAction));
  $$('[data-volume-goto]',dialog).forEach(button=>button.onclick=()=>{if(button.dataset.volumeGoto)openVolume(Number(button.dataset.volumeGoto))});
  wireVolumeTab(volume);
}

function volumeAction(action){
  const volume=state.modalVolume;
  if(action==='copy')openEntryDialog(volume);
  if(action==='read')setRead(volume.id,!volume.read);
  if(action==='preorder')openPreorderDialog(volume);
  if(action==='wish')openWishDialog('volumes',volume.id);
  if(action==='edit')openVolumeForm(volume,{volumeId:volume.id,edition:volume.edition});
  if(action==='image')openImageDialog('volumes',volume);
  if(action==='edition'){closeOverlay('volume-modal');openEdition(volume.edition_id)}
}

function entryLine(entry){
  return [conditionLabel(entry.condition),entry.first_printing?'Erstauflage':'',entry.purchase_price!=null?`${money(entry.purchase_price)}${entry.quantity>1?' je Stück':''}`:'',entry.shop,partialDate(entry.purchased_at),entry.location&&`📍 ${entry.location}`].filter(Boolean).map(escapeHtml).join(' · ');
}

function preorderLine(item){
  const parts=[item.shop,item.ordered_at&&`bestellt ${partialDate(item.ordered_at)}`,item.expected_release&&`erwartet ${partialDate(item.expected_release)}`];
  return parts.filter(Boolean).map(escapeHtml).join(' · ');
}

function volumeTabHtml(volume){
  const tab=state.modalTab;
  if(tab==='copies'){
    if(!volume.entries.length)return `<p class="muted">Du hast diesen Band noch nicht in deiner Sammlung.</p><button type="button" class="secondary-button" data-volume-action-inline="copy">＋ Exemplar hinzufügen</button>`;
    return `<div class="fig-rows">${volume.entries.map(entry=>`<div class="fig-row"><b>${entry.quantity}×</b><span><span>${entryLine(entry)}</span>${entry.extras?`<small>Extras: ${escapeHtml(entry.extras)}</small>`:''}${entry.notes?`<small>${escapeHtml(entry.notes)}</small>`:''}${entry.preorder_id?'<small>aus einer Vorbestellung</small>':''}</span><span class="fig-row-actions"><button type="button" class="icon-button" data-edit-entry="${entry.id}" title="Bearbeiten" aria-label="Exemplar bearbeiten">✎</button><button type="button" class="icon-button" data-delete-entry="${entry.id}" title="Entfernen" aria-label="Exemplar entfernen">✕</button></span></div>`).join('')}</div>
      <button type="button" class="secondary-button" data-volume-action-inline="copy">＋ Weiteres Exemplar</button>`;
  }
  if(tab==='preorders'){
    if(!volume.preorders.length)return `<p class="muted">Keine Vorbestellung für diesen Band.</p><button type="button" class="secondary-button" data-volume-action-inline="preorder">Vorbestellen</button>`;
    return `<div class="fig-rows">${volume.preorders.map(item=>`<div class="fig-row"><span class="status-pill status-${item.status}">${escapeHtml(statusLabel(item.status))}</span><span><span>${preorderLine(item)}</span><small>${item.total!=null?`${money(item.total)}`:'Preis offen'}${item.outstanding?` · noch ${money(item.outstanding)} offen`:''}${item.delays?` · ${item.delays}× verschoben`:''}</small></span><span class="fig-row-actions"><button type="button" class="icon-button" data-edit-preorder="${item.id}" title="Bearbeiten" aria-label="Vorbestellung bearbeiten">✎</button></span></div>`).join('')}</div>
      <button type="button" class="secondary-button" data-volume-action-inline="preorder">Weitere Vorbestellung</button>`;
  }
  if(tab==='value'){
    return `<div class="fig-value-head"><div><span class="eyebrow">MARKTWERT</span><b>${moneyOrDash(volume.market_value)}</b></div><small class="muted">Nur nötig, wo ein Band mehr (oder weniger) wert ist als sein Preis – vergriffen, Limited Edition. Ohne Marktwert zählt in deiner Sammlung der Kaufpreis, sonst der Listenpreis.</small></div>
      ${priceHistoryHtml(volume.prices)}
      <div class="fig-inline-form"><input class="dl-control" id="price-amount" inputmode="decimal" placeholder="Wert in €" aria-label="Marktwert in Euro"><input class="dl-control" id="price-note" placeholder="Quelle/Notiz (optional)" aria-label="Quelle oder Notiz"><button type="button" class="primary-button" id="price-add">Eintragen</button></div>
      ${volume.prices.length?`<div class="fig-rows">${volume.prices.map(price=>`<div class="fig-row"><b>${money(price.amount)}</b><span><span>${date(price.observed_at)}${price.author?` · ${escapeHtml(price.author)}`:''}</span>${price.note?`<small>${escapeHtml(price.note)}</small>`:''}</span><span class="fig-row-actions"><button type="button" class="icon-button" data-delete-price="${price.id}" title="Wert löschen" aria-label="Wert löschen">✕</button></span></div>`).join('')}</div>`:''}`;
  }
  if(tab==='lists'){
    const memberships=new Map(volume.lists.map(item=>[item.list_id,item]));
    return `<div class="fig-rows">${state.boot.watchlists.map(list=>{const entry=memberships.get(list.id);return `<div class="fig-row fig-list-row"><label class="fig-list-toggle"><input type="checkbox" data-list-toggle="${list.id}" ${entry?'checked':''}><b>${escapeHtml(list.name)}</b></label>${entry?`<span class="fig-list-fields"><input class="dl-control" data-list-target="${list.id}" inputmode="decimal" placeholder="Zielpreis €" aria-label="Zielpreis" value="${amountValue(entry.target_price)}"><input class="dl-control" data-list-note="${list.id}" placeholder="Notiz" aria-label="Notiz" value="${escapeHtml(entry.note)}"></span>`:'<span class="muted">nicht auf der Liste</span>'}</div>`}).join('')}</div>
      <p class="muted">Ein Zielpreis markiert den Band auf der Liste, sobald sein Marktwert darunter fällt.</p>`;
  }
  const attributes=Object.entries(volume.attributes||{});
  return `${volume.description?`<p class="fig-description">${escapeHtml(volume.description)}</p>`:'<p class="muted">Keine Beschreibung.</p>'}
    <dl class="fig-facts">
      ${factRow('Quelle',volume.source_url?`<a href="${escapeHtml(volume.source_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(hostOf(volume.source_url))}</a>`:'')}
      ${factRow('Angelegt',`${date(volume.created_at)}${volume.created_by_name?` von ${escapeHtml(volume.created_by_name)}`:''}`)}
      ${factRow('Sammler',volume.owners?plural(volume.owners,'Konto hat ihn','Konten haben ihn'):'')}
      ${attributes.map(([key,value])=>factRow(escapeHtml(key),escapeHtml(value))).join('')}
    </dl>
    ${volume.can_delete?'<button type="button" class="secondary-button danger" id="volume-delete">Aus dem Katalog löschen</button>':''}`;
}

function wireVolumeTab(volume){
  const body=$('#volume-tab-body');if(!body)return;
  $$('[data-volume-action-inline]',body).forEach(button=>button.onclick=()=>volumeAction(button.dataset.volumeActionInline));
  $$('[data-edit-entry]',body).forEach(button=>button.onclick=()=>openEntryDialog(volume,volume.entries.find(entry=>entry.id===Number(button.dataset.editEntry))));
  $$('[data-delete-entry]',body).forEach(button=>button.onclick=async()=>{
    try{
      const {deleted}=await del(`/api/collection/${button.dataset.deleteEntry}`);
      toast('Exemplar entfernt','Rückgängig',async()=>{const {id,user_id,created_at,updated_at,preorder_id,...fields}=deleted;await post('/api/collection',fields);afterChange()});
      afterChange();
    }catch(error){toast(error.message)}
  });
  $$('[data-edit-preorder]',body).forEach(button=>button.onclick=()=>openPreorderDialog(volume,volume.preorders.find(item=>item.id===Number(button.dataset.editPreorder))));
  $('#price-add',body)?.addEventListener('click',async()=>{
    try{await post(`/api/volumes/${volume.id}/prices`,{amount:$('#price-amount',body).value,note:$('#price-note',body).value});toast('Marktwert eingetragen');afterChange()}
    catch(error){toast(error.message)}
  });
  $('#price-amount',body)?.addEventListener('keydown',event=>{if(event.key==='Enter')$('#price-add',body).click()});
  $$('[data-delete-price]',body).forEach(button=>button.onclick=async()=>{
    try{await del(`/api/volumes/${volume.id}/prices/${button.dataset.deletePrice}`);afterChange()}catch(error){toast(error.message)}
  });
  $$('[data-list-toggle]',body).forEach(box=>box.onchange=async()=>{
    const listId=box.dataset.listToggle;
    try{
      const result=box.checked?await post(`/api/watchlists/${listId}/volumes`,{volume_id:volume.id}):await del(`/api/watchlists/${listId}/volumes/${volume.id}`);
      state.boot.watchlists=result.lists;afterChange();
    }catch(error){toast(error.message)}
  });
  const saveEntry=async listId=>{
    try{await patch(`/api/watchlists/${listId}/volumes/${volume.id}`,{target_price:$(`[data-list-target="${listId}"]`,body).value,note:$(`[data-list-note="${listId}"]`,body).value});toast('Gespeichert',null,null,'list-entry')}
    catch(error){toast(error.message)}
  };
  $$('[data-list-target],[data-list-note]',body).forEach(input=>input.onchange=()=>saveEntry(input.dataset.listTarget||input.dataset.listNote));
  $('#volume-delete',body)?.addEventListener('click',async()=>{
    if(!confirm(`„${volume.edition_name} · ${volumeLabel(volume)}“ endgültig aus dem Katalog löschen?`))return;
    try{await del(`/api/volumes/${volume.id}`);closeOverlay('volume-modal');toast('Aus dem Katalog gelöscht');afterChange()}
    catch(error){toast(error.message)}
  });
}

// After any change made from a dialog: the open dialogs, the counts and the view behind them.
function reloadDialogs(){reloadVolume();reloadEdition()}
function afterChange(){reloadDialogs();refreshCounts();refreshCurrentView()}

function priceHistoryHtml(prices){
  const points=[...prices].sort((a,b)=>a.observed_at.localeCompare(b.observed_at)||a.id-b.id);
  if(points.length<2)return '';
  const width=300,height=80,pad=8,amounts=points.map(point=>point.amount);
  const min=Math.min(...amounts),max=Math.max(...amounts),range=max-min;
  const t0=new Date(points[0].observed_at).getTime(),span=(new Date(points.at(-1).observed_at).getTime()-t0)||1;
  const coords=points.map(point=>[(new Date(point.observed_at).getTime()-t0)/span*width,pad+(1-(range?(point.amount-min)/range:.5))*(height-2*pad)]);
  const line=coords.map(([x,y],i)=>`${i?'L':'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const delta=points.at(-1).amount-points[0].amount;
  return `<div class="price-history"><div class="price-history-head"><span>${date(points[0].observed_at)} – ${date(points.at(-1).observed_at)}</span><b class="price-history-delta ${delta>0?'up':delta<0?'down':'flat'}">${delta>0?'+':''}${money(delta)}</b></div>
    <svg class="price-history-chart" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Verlauf des Marktwerts"><path class="price-history-area" d="${line} L${width},${height} L0,${height} Z"/><path class="price-history-line" d="${line}"/></svg>
    <div class="price-history-range"><span>Tief ${money(min)}</span><span>Hoch ${money(max)}</span></div></div>`;
}

// ---- Copies -------------------------------------------------------------------------------------

async function openEntryDialog(volume,entry=null){
  const suggestions=await loadSuggestions().catch(()=>({}));
  const conditions=Object.entries(state.boot.conditions);
  const value=key=>escapeHtml(entry?.[key]??'');
  const price=entry?entry.purchase_price:(volume.currency==='EUR'?volume.list_price:null);
  const modal=openDialog({id:'entry-dialog',eyebrow:'SAMMLUNG',title:entry?'Exemplar bearbeiten':'Exemplar hinzufügen',intro:escapeHtml(`${volume.edition_name} · ${volumeLabel(volume)}`),stack:true,body:`
    <div class="dl-grid">
      <label class="dl-field"><span>Anzahl</span><input class="dl-control" data-field="quantity" type="number" min="1" max="999" value="${entry?.quantity??1}"></label>
      <label class="dl-field"><span>Zustand</span><select class="dl-control" data-field="condition">${conditions.map(([key,label])=>`<option value="${key}" ${(entry?.condition||'new')===key?'selected':''}>${escapeHtml(label)}</option>`).join('')}</select></label>
      <label class="dl-field"><span>Kaufpreis je Stück (€)</span><input class="dl-control" data-field="purchase_price" inputmode="decimal" placeholder="z. B. 7,50" value="${amountValue(price)}"></label>
      <label class="dl-field"><span>Kaufdatum</span><input class="dl-control" data-field="purchased_at" placeholder="TT.MM.JJJJ oder JJJJ-MM" value="${escapeHtml(entry?.purchased_at||'')}"></label>
      <label class="dl-field"><span>Shop / Verkäufer</span><input class="dl-control" data-field="shop" list="shop-suggestions" value="${value('shop')}"></label>
      <label class="dl-field"><span>Aufbewahrung</span><input class="dl-control" data-field="location" list="location-suggestions" placeholder="z. B. Regal 2" value="${value('location')}"></label>
      <label class="dl-field dl-field-wide"><span>Extras</span><input class="dl-control" data-field="extras" placeholder="z. B. Schuber, Postkarte, Acrylstand" value="${value('extras')}"></label>
      <label class="checkbox-row dl-field-wide"><span><b>Erstauflage</b><small>Das Exemplar stammt aus der ersten Auflage.</small></span><input type="checkbox" data-field="first_printing" ${entry?.first_printing?'checked':''}><i aria-hidden="true"></i></label>
      <label class="dl-field dl-field-wide"><span>Notizen</span><textarea class="dl-control" data-field="notes" rows="2">${value('notes')}</textarea></label>
    </div>
    ${datalist('shop-suggestions',suggestions.shop)}${datalist('location-suggestions',suggestions.location)}
    <div class="dl-modal-actions"><button type="button" class="secondary-button" data-dialog-close>Abbrechen</button><span class="spacer"></span><button type="button" class="primary-button" id="entry-save">${entry?'Speichern':'Hinzufügen'}</button></div>`});
  $$('[data-dialog-close]',modal).forEach(button=>button.onclick=closeDialog);
  $('#entry-save',modal).onclick=async()=>{
    const values=fieldValues(modal);
    try{
      if(entry)await patch(`/api/collection/${entry.id}`,values);
      else await post('/api/collection',{volume_id:volume.id,...values});
      closeDialog();toast(entry?'Exemplar gespeichert':'Zur Sammlung hinzugefügt');state.suggestions=null;afterChange();
    }catch(error){toast(error.message)}
  };
}

// ---- Preorders ----------------------------------------------------------------------------------

async function openPreorderDialog(volume,preorder=null,prefill={}){
  const suggestions=await loadSuggestions().catch(()=>({}));
  const listPrice=volume.currency==='EUR'?volume.list_price:null;
  const item={quantity:1,status:'ordered',expected_release:volume.release_date||'',price:listPrice,...prefill,...(preorder||{})};
  const value=key=>escapeHtml(item[key]??'');
  const statuses=Object.entries(state.boot.statuses);
  const delays=preorder?.events?.filter(event=>event.kind==='release')||[];
  const name=`${volume.edition_name} · ${volumeLabel(volume)}`;
  const modal=openDialog({id:'preorder-dialog',eyebrow:'VORBESTELLUNG',title:preorder?'Vorbestellung bearbeiten':'Vorbestellen',intro:escapeHtml(name),stack:true,body:`
    <div class="dl-grid">
      <label class="dl-field"><span>Status</span><select class="dl-control" data-field="status">${statuses.map(([key,label])=>`<option value="${key}" ${item.status===key?'selected':''}>${escapeHtml(label)}</option>`).join('')}</select></label>
      <label class="dl-field"><span>Erwartet</span><input class="dl-control" data-field="expected_release" placeholder="z. B. 2026-03" value="${value('expected_release')}"></label>
      <label class="dl-field"><span>Shop</span><input class="dl-control" data-field="shop" list="preorder-shop-suggestions" value="${value('shop')}"></label>
      <label class="dl-field"><span>Bestellnummer</span><input class="dl-control" data-field="order_number" value="${value('order_number')}"></label>
      <label class="dl-field"><span>Bestellt am</span><input class="dl-control" data-field="ordered_at" placeholder="heute" value="${value('ordered_at')}"></label>
      <label class="dl-field"><span>Anzahl</span><input class="dl-control" data-field="quantity" type="number" min="1" max="99" value="${item.quantity}"></label>
      <label class="dl-field"><span>Preis gesamt (€)</span><input class="dl-control" data-field="price" inputmode="decimal" value="${amountValue(item.price)}"></label>
      <label class="dl-field"><span>Versand & Gebühren (€)</span><input class="dl-control" data-field="shipping" inputmode="decimal" value="${amountValue(item.shipping)}"></label>
      <label class="dl-field"><span>Schon bezahlt (€)</span><input class="dl-control" data-field="paid" inputmode="decimal" placeholder="z. B. Anzahlung" value="${amountValue(item.paid||'')}"></label>
      <label class="dl-field"><span>Sendungsnummer</span><input class="dl-control" data-field="tracking" value="${value('tracking')}"></label>
      <label class="dl-field dl-field-wide"><span>Notizen</span><textarea class="dl-control" data-field="notes" rows="2">${value('notes')}</textarea></label>
      ${!preorder&&volume.wished?'<label class="checkbox-row dl-field-wide"><span><b>Von den Wunschlisten nehmen</b><small>Der Band ist bestellt, er muss nicht mehr gesucht werden.</small></span><input type="checkbox" data-field="remove_from_wishlists" checked><i aria-hidden="true"></i></label>':''}
    </div>
    ${datalist('preorder-shop-suggestions',suggestions.shop)}
    ${delays.length?`<div class="fig-delays"><b>Verschiebungen</b>${delays.map(event=>`<span>${escapeHtml(partialDate(event.old_value)||'–')} → ${escapeHtml(partialDate(event.new_value)||'–')} <small>${date(event.created_at)}</small></span>`).join('')}</div>`:''}
    <p class="muted">„Angekommen“ bucht die Exemplare als neu (Erstauflage) in die Sammlung, mit dem Preis je Stück inklusive Versand.</p>
    <div class="dl-modal-actions">${preorder?'<button type="button" class="secondary-button danger" id="preorder-delete">Löschen</button>':'<button type="button" class="secondary-button" data-dialog-close>Abbrechen</button>'}<span class="spacer"></span><button type="button" class="primary-button" id="preorder-save">${preorder?'Speichern':'Vorbestellung anlegen'}</button></div>`});
  $$('[data-dialog-close]',modal).forEach(button=>button.onclick=closeDialog);
  $('#preorder-save',modal).onclick=async()=>{
    const values=fieldValues(modal);
    try{
      if(preorder)await patch(`/api/preorders/${preorder.id}`,values);
      else await post('/api/preorders',{volume_id:volume.volume_id??volume.id,...values});
      closeDialog();toast(values.status==='delivered'?'Angekommen – in die Sammlung gebucht':preorder?'Vorbestellung gespeichert':'Vorbestellung angelegt');state.suggestions=null;afterChange();
    }catch(error){toast(error.message)}
  };
  $('#preorder-delete',modal)?.addEventListener('click',async()=>{
    if(!confirm('Diese Vorbestellung löschen? Bereits eingebuchte Exemplare bleiben in der Sammlung.'))return;
    try{await del(`/api/preorders/${preorder.id}`);closeDialog();toast('Vorbestellung gelöscht');afterChange()}catch(error){toast(error.message)}
  });
}

// ---- Wishlists ----------------------------------------------------------------------------------

// Which lists a volume (with a target price) or a whole edition (with a note) is on.
async function openWishDialog(kind,id){
  let item;
  try{item=kind==='volumes'?(state.modalVolume?.id===id?state.modalVolume:await api(`/api/volumes/${id}`)):await api(`/api/editions/${id}`)}
  catch(error){toast(error.message);return}
  const memberships=new Map(item.lists.map(entry=>[entry.list_id,entry]));
  const field=kind==='editions'?'edition_id':'volume_id';
  const name=kind==='volumes'?`${item.edition_name} · ${volumeLabel(item)}`:item.name;
  const modal=openDialog({id:'wish-dialog',eyebrow:'WUNSCHLISTEN',title:kind==='editions'?'Ganze Ausgabe wünschen':'Auf welche Listen?',intro:escapeHtml(name),stack:true,body:`
    <div class="fig-rows">${state.boot.watchlists.map(list=>{const entry=memberships.get(list.id);return `<label class="fig-row fig-list-row"><span class="fig-list-toggle"><input type="checkbox" data-wish-list="${list.id}" ${entry||(!item.lists.length&&list.is_default)?'checked':''}><b>${escapeHtml(list.name)}</b></span></label>`}).join('')}</div>
    <div class="dl-grid">
      ${kind==='volumes'?`<label class="dl-field"><span>Zielpreis (€)</span><input class="dl-control" data-field="target_price" inputmode="decimal" placeholder="optional" value="${amountValue(item.lists[0]?.target_price)}"></label>`:''}
      <label class="dl-field${kind==='volumes'?'':' dl-field-wide'}"><span>Notiz</span><input class="dl-control" data-field="note" placeholder="${kind==='volumes'?'z. B. nur Erstauflage':'z. B. erst ab Band 1 neu'}" value="${escapeHtml(item.lists[0]?.note??'')}"></label>
      <label class="dl-field dl-field-wide"><span>Neue Liste</span><input class="dl-control" id="wish-new-list" placeholder="Name einer neuen Liste (optional)"></label>
    </div>
    <div class="dl-modal-actions"><button type="button" class="secondary-button" data-dialog-close>Abbrechen</button><span class="spacer"></span><button type="button" class="primary-button" id="wish-save">Speichern</button></div>`});
  $$('[data-dialog-close]',modal).forEach(button=>button.onclick=closeDialog);
  $('#wish-save',modal).onclick=async()=>{
    const values=fieldValues(modal);
    try{
      const newName=$('#wish-new-list',modal).value.trim();
      const chosen=$$('[data-wish-list]',modal).filter(box=>box.checked).map(box=>Number(box.dataset.wishList));
      if(newName)chosen.push((await post('/api/watchlists',{name:newName})).id);
      for(const list of state.boot.watchlists){
        if(memberships.has(list.id)&&!chosen.includes(list.id))await del(`/api/watchlists/${list.id}/${kind}/${id}`);
      }
      for(const listId of chosen)await post(`/api/watchlists/${listId}/${kind}`,{[field]:id,...values});
      closeDialog();toast('Wunschlisten gespeichert');afterChange();
    }catch(error){toast(error.message)}
  };
}

// ---- Pictures -----------------------------------------------------------------------------------

// What the server takes (images.py FORMATS); the file pickers offer these.
const PICTURE_TYPES='image/jpeg,image/png,image/webp,image/gif,image/avif';

function openImageDialog(kind,item){
  const name=kind==='volumes'?`${item.edition_name} · ${volumeLabel(item)}`:item.title;
  const modal=openDialog({id:'image-dialog',eyebrow:kind==='volumes'?'COVER':'BILD',title:kind==='volumes'?'Cover des Bands':'Bild der Reihe',intro:escapeHtml(name),stack:true,body:`
    <div class="dl-grid">
      <label class="dl-field dl-field-wide"><span>Datei hochladen</span><input class="dl-control" type="file" id="image-file" accept="${PICTURE_TYPES}"></label>
      <label class="dl-field dl-field-wide"><span>… oder Link zu einem Bild</span><input class="dl-control" id="image-url" placeholder="https://…/cover.jpg" value="${escapeHtml(item.image_url||'')}"></label>
    </div>
    <div class="dl-modal-actions">${item.has_image?'<button type="button" class="secondary-button danger" id="image-remove">Bild entfernen</button>':''}<span class="spacer"></span><button type="button" class="primary-button" id="image-save">Übernehmen</button></div>`});
  $('#image-save',modal).onclick=async()=>{
    const file=$('#image-file',modal).files[0],url=$('#image-url',modal).value.trim();
    try{
      if(file)await uploadImage(kind,item.id,file);
      else if(url)await post(`/api/${kind}/${item.id}/image`,{url});
      else{toast('Bitte eine Datei oder einen Link wählen.');return}
      closeDialog();toast('Bild gespeichert');afterChange();
    }catch(error){toast(error.message)}
  };
  $('#image-remove',modal)?.addEventListener('click',async()=>{
    try{await del(`/api/${kind}/${item.id}/image`);closeDialog();afterChange()}catch(error){toast(error.message)}
  });
}

async function uploadImage(kind,id,file){
  const form=new FormData();form.append('file',file);
  const response=await fetch(appUrl(`/api/${kind}/${id}/image`),{method:'POST',body:form});
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(data.error||'Upload fehlgeschlagen');
  return data;
}

// ---- Forms: series, edition, volume ---------------------------------------------------------

// A form field: [key, label, {wide, list, placeholder, options, inputmode}] -> HTML.
function formField(values,[key,label,{wide=false,list=null,placeholder='',options=null,inputmode=''}={}]){
  const value=values[key]??'';
  const control=options
    ?`<select class="dl-control" data-field="${key}">${options.map(([optionValue,text])=>`<option value="${escapeHtml(optionValue)}" ${String(value)===String(optionValue)?'selected':''}>${escapeHtml(text)}</option>`).join('')}</select>`
    :`<input class="dl-control" data-field="${key}" ${list?`list="suggest-${list}"`:''} ${placeholder?`placeholder="${escapeHtml(placeholder)}"`:''} ${inputmode?`inputmode="${inputmode}"`:''} value="${escapeHtml(value)}" autocomplete="off">`;
  return `<label class="dl-field${wide?' dl-field-wide':''}"><span>${label}</span>${control}</label>`;
}
const formSection=(title,body)=>`<section class="fig-form-section"><h3>${title}</h3><div class="dl-grid fig-form-grid">${body}</div></section>`;
const choiceOptions=(entries,empty='–')=>[['',empty],...Object.entries(entries||{})];
const currencySelect=(value,currencies)=>`<select class="dl-control" data-field="currency" aria-label="Währung">${(currencies||['EUR','JPY','USD']).map(code=>`<option ${(value||'EUR')===code?'selected':''}>${code}</option>`).join('')}</select>`;

// Saves a form; on a duplicate (409) it says so in the note and offers the existing entry or saving anyway.
async function saveWithDuplicateCheck(modal,noteSelector,saveFn,{openLabel,openExisting}){
  const button=$('[data-save]',modal);button.disabled=true;
  try{return await saveFn(false)}
  catch(error){
    if(error.status===409&&error.data?.duplicate_id){
      const note=$(noteSelector,modal);
      note.innerHTML=`<div class="fig-import-note warning"><b>Schon im Katalog?</b><span>${escapeHtml(error.message)}</span><span class="fig-import-actions"><button type="button" class="secondary-button" data-open-duplicate>${openLabel}</button><button type="button" class="link-button" data-force>Trotzdem speichern</button></span></div>`;
      $('[data-open-duplicate]',note).onclick=()=>{closeDialog();openExisting(error.data.duplicate_id)};
      $('[data-force]',note).onclick=()=>{button.dataset.force='1';button.click()};
      note.scrollIntoView({behavior:'smooth',block:'nearest'});
    }else toast(error.message);
    return null;
  }finally{button.disabled=false}
}
// Whether the save was asked for after "Trotzdem speichern" (once).
function forced(modal){const button=$('[data-save]',modal);const value=button.dataset.force==='1';delete button.dataset.force;return value}

// A series: by hand, or from AniList (search, pick, the fields fill themselves).
async function openSeriesForm(prefill={},{seriesId=null,onSaved=null}={}){
  const suggestions=await loadSuggestions().catch(()=>({}));
  const editing=Boolean(seriesId);
  const values={...prefill};
  const modal=openDialog({id:'series-form',eyebrow:'KATALOG · REIHE',title:editing?'Reihe bearbeiten':'Neue Reihe',wide:true,stack:editing,
    intro:editing?'Der Katalog ist für alle Konten gemeinsam – Korrekturen sehen alle.':'Die Reihe ist das Werk an sich – Verlag, Sprache und Bände kommen mit der Ausgabe.',body:`
    <div class="fig-import mg-anilist">
      <input class="dl-control" id="anilist-query" placeholder="Bei AniList suchen: Titel der Reihe" value="${escapeHtml(editing?'':values.title||'')}" autocomplete="off" aria-label="Bei AniList suchen">
      <button type="button" class="secondary-button" id="anilist-search">Suchen</button>
      <small class="muted">Füllt Originaltitel, Autor:innen, Genres, Zielgruppe, Status und Bild aus der freien Datenbank AniList.</small>
    </div>
    <div id="anilist-results" class="mg-anilist-results"></div>
    <div id="series-note"></div>
    ${formSection('Reihe',[
      formField(values,['title','Titel *',{wide:true}]),
      formField(values,['original_title','Originaltitel',{placeholder:'z. B. 葬送のフリーレン'}]),
      formField(values,['alt_titles','Weitere Titel',{placeholder:'Romaji, englisch …'}]),
      formField(values,['authors','Autor:innen',{list:'author',placeholder:'Story und Zeichnungen, mit Komma'}]),
      formField(values,['genres','Genres',{list:'genre',placeholder:'mit Komma getrennt'}]),
      formField(values,['demographic','Zielgruppe',{options:choiceOptions(state.boot.demographics)}]),
      formField(values,['status','Status im Original',{options:choiceOptions(state.boot.series_statuses)}]),
      formField(values,['original_volumes','Bände im Original',{inputmode:'numeric'}]),
      formField(values,['start_year','Startjahr',{inputmode:'numeric'}]),
    ].join(''))}
    ${formSection('Bild & Quelle',[
      formField(values,['image_url','Bild-Link',{wide:true,placeholder:'https://…/bild.jpg'}]),
      formField(values,['source_url','Link zur Quelle',{wide:true,placeholder:'https://…'}]),
      `<label class="dl-field dl-field-wide"><span>Beschreibung</span><textarea class="dl-control" data-field="description" rows="3">${escapeHtml(values.description||'')}</textarea></label>`,
    ].join(''))}
    <input type="hidden" data-field="anilist_id" value="${escapeHtml(values.anilist_id||'')}">
    ${datalist('suggest-author',suggestions.author)}${datalist('suggest-genre',suggestions.genre)}
    <div class="dl-modal-actions"><button type="button" class="secondary-button" data-dialog-close>Abbrechen</button><span class="spacer"></span><button type="button" class="primary-button" data-save>${editing?'Speichern':onSaved?'Weiter zur Ausgabe':'Reihe anlegen'}</button></div>`});
  $$('[data-dialog-close]',modal).forEach(button=>button.onclick=closeDialog);
  const fill=fields=>{for(const [key,value] of Object.entries(fields)){const input=$(`[data-field="${key}"]`,modal);if(input&&value!=null&&value!=='')input.value=value}};
  const search=async()=>{
    const query=$('#anilist-query',modal).value.trim(),results=$('#anilist-results',modal);
    if(query.length<2){toast('Bitte mindestens zwei Zeichen.');return}
    results.innerHTML='<p class="muted">Suche bei AniList …</p>';
    try{
      const answer=await api(`/api/lookup/anilist?q=${encodeURIComponent(query)}`);
      results.innerHTML=answer.results.length?answer.results.map((item,index)=>`<button type="button" class="mg-anilist-result" data-anilist="${index}">
          ${item.series.image_url?`<img src="${escapeHtml(item.series.image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer">`:'<span></span>'}
          <span><b>${escapeHtml(item.series.title)}</b><small>${escapeHtml([item.series.original_title,item.series.authors,item.series.start_year].filter(Boolean).join(' · '))}</small>${item.match?.series_id?'<small class="mg-warn">Schon im Katalog</small>':''}</span></button>`).join('')
        :'<p class="muted">AniList kennt dazu nichts. Trag die Reihe von Hand ein.</p>';
      $$('[data-anilist]',results).forEach(button=>button.onclick=()=>{
        const item=answer.results[Number(button.dataset.anilist)];
        if(item.match?.series_id&&!editing){closeDialog();toast('Die Reihe ist schon im Katalog');onSaved?onSaved({id:item.match.series_id}):openSeriesDialog(item.match.series_id);return}
        fill(item.series);results.innerHTML=`<div class="fig-import-note ok"><b>Von AniList übernommen</b><span>${escapeHtml(item.series.title)} – prüfe die Felder und speichere.</span></div>`;
      });
    }catch(error){results.innerHTML=`<div class="fig-import-note warning"><b>AniList nicht erreichbar</b><span>${escapeHtml(error.message)}</span></div>`}
  };
  $('#anilist-search',modal).onclick=search;
  $('#anilist-query',modal).addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();search()}});
  $('[data-save]',modal).onclick=async()=>{
    const fields=fieldValues(modal),force=forced(modal);
    if(!fields.title.trim()){toast('Der Titel fehlt.');return}
    const saved=await saveWithDuplicateCheck(modal,'#series-note',()=>editing?patch(`/api/series/${seriesId}`,{...fields,force}):post('/api/series',{...fields,force}),
      {openLabel:'Vorhandene öffnen',openExisting:id=>onSaved?onSaved({id}):openSeriesDialog(id)});
    if(!saved)return;
    if(saved.image_error)toast(`Bild nicht geladen: ${saved.image_error}`);
    closeDialog();state.suggestions=null;refreshCounts();
    if(onSaved)onSaved(saved);else{toast(editing?'Reihe gespeichert':'Reihe angelegt');afterChange()}
  };
}

// An edition of a series.
async function openEditionForm(prefill={},{editionId=null,series=null,onSaved=null}={}){
  const suggestions=await loadSuggestions().catch(()=>({}));
  const editing=Boolean(editionId);
  const values={language:'de',currency:'EUR',...prefill};
  const languages=Object.entries(state.boot.languages||{});
  if(values.language&&!languages.some(([code])=>code===values.language))languages.push([values.language,values.language.toUpperCase()]);
  const modal=openDialog({id:'edition-form',eyebrow:'KATALOG · AUSGABE',title:editing?'Ausgabe bearbeiten':'Neue Ausgabe',wide:true,stack:editing,
    intro:series?`Reihe: ${escapeHtml(series.title)}`:'',body:`
    <div id="edition-note"></div>
    ${formSection('Ausgabe',[
      formField(values,['publisher','Verlag',{list:'publisher',placeholder:'z. B. Carlsen'}]),
      formField(values,['language','Sprache',{options:languages}]),
      formField(values,['format','Format',{list:'format',placeholder:'z. B. Taschenbuch'}]),
      formField(values,['label','Name der Ausgabe',{list:'label',placeholder:'z. B. Perfect Edition; leer = normal'}]),
      formField(values,['title','Titel dieser Ausgabe',{wide:true,placeholder:series?`leer = „${series.title}“`:'leer = Titel der Reihe'}]),
      formField(values,['status','Status',{options:choiceOptions(state.boot.series_statuses)}]),
      formField(values,['volume_count','Bände (bekannt)',{inputmode:'numeric',placeholder:'z. B. 34'}]),
      `<label class="dl-field"><span>Listenpreis je Band</span><span class="fig-price-input"><input class="dl-control" data-field="list_price" inputmode="decimal" value="${amountValue(values.list_price)}" aria-label="Listenpreis je Band">${currencySelect(values.currency,suggestions.currencies)}</span></label>`,
    ].join(''))}
    ${formSection('Quelle',[
      formField(values,['source_url','Link zur Verlagsseite',{wide:true,placeholder:'https://…'}]),
      `<label class="dl-field dl-field-wide"><span>Beschreibung</span><textarea class="dl-control" data-field="description" rows="2">${escapeHtml(values.description||'')}</textarea></label>`,
      editing?'':`<label class="checkbox-row dl-field-wide"><span><b>Sammle ich</b><small>Die Ausgabe erscheint mit ihren Lücken und Neuerscheinungen in deiner Planung.</small></span><input type="checkbox" data-field="collect" ${values.collect?'checked':''}><i aria-hidden="true"></i></label>`,
    ].join(''))}
    ${datalist('suggest-publisher',suggestions.publisher)}${datalist('suggest-format',suggestions.format)}${datalist('suggest-label',suggestions.label)}
    <div class="dl-modal-actions"><button type="button" class="secondary-button" data-dialog-close>Abbrechen</button><span class="spacer"></span><button type="button" class="primary-button" data-save>${editing?'Speichern':onSaved?'Weiter zum Band':'Ausgabe anlegen'}</button></div>`});
  $$('[data-dialog-close]',modal).forEach(button=>button.onclick=closeDialog);
  $('[data-save]',modal).onclick=async()=>{
    const fields={...fieldValues(modal),series_id:values.series_id??series?.id},force=forced(modal);
    const saved=await saveWithDuplicateCheck(modal,'#edition-note',()=>editing?patch(`/api/editions/${editionId}`,{...fields,force}):post('/api/editions',{...fields,force}),
      {openLabel:'Vorhandene öffnen',openExisting:id=>onSaved?api(`/api/editions/${id}`).then(onSaved):openEdition(id)});
    if(!saved)return;
    closeDialog();state.suggestions=null;refreshCounts();
    if(onSaved)onSaved(saved);else{toast(editing?'Ausgabe gespeichert':'Ausgabe angelegt');afterChange();if(!editing)openEdition(saved.id)}
  };
}

function coverChoices(covers){
  const list=[...new Set((covers||[]).filter(Boolean))];
  if(list.length<2)return '';
  return `<span class="muted">Cover wählen:</span>${list.map(url=>`<button type="button" class="mg-cover-choice" data-cover="${escapeHtml(url)}" title="Dieses Cover nehmen"><img src="${escapeHtml(url)}" alt="" loading="lazy" referrerpolicy="no-referrer"></button>`).join('')}`;
}

function proposalNote(result){
  const parts=[];
  const sources={dnb:'Deutsche Nationalbibliothek',google:'Google Books',openlibrary:'Open Library',page:'der Seite'};
  if(result.found===false)parts.push('<b>Nichts gefunden</b>');
  else parts.push(`<b>Übernommen aus ${(result.sources||[]).map(source=>sources[source]||source).join(', ')||'der Suche'}</b>`);
  for(const warning of result.warnings||[])parts.push(`<span>${escapeHtml(warning)}</span>`);
  if(result.series?.title)parts.push(`<span>Reihe laut Quelle: ${escapeHtml(result.series.title)}${result.volume?.number?` · Band ${escapeHtml(result.volume.number)}`:''}${result.edition?.publisher?` · ${escapeHtml(result.edition.publisher)}`:''}</span>`);
  return `<div class="fig-import-note ${result.found===false||(result.warnings||[]).length>1?'warning':'ok'}">${parts.join('')}</div>`;
}

// A volume of an edition: by hand, or filled in from its ISBN (lookup or barcode).
async function openVolumeForm(prefill={},{volumeId=null,edition=null,covers=[],note=''}={}){
  const suggestions=await loadSuggestions().catch(()=>({}));
  const editing=Boolean(volumeId);
  const values={currency:edition?.currency||'EUR',...prefill};
  const modal=openDialog({id:'volume-form',eyebrow:'KATALOG · BAND',title:editing?'Band bearbeiten':'Neuer Band',wide:true,stack:editing,
    intro:edition?`Ausgabe: ${escapeHtml(edition.name)}`:'',body:`
    ${editing?'':`<div class="fig-import mg-isbn-row">
      <input class="dl-control" id="volume-isbn-lookup" inputmode="numeric" placeholder="ISBN nachschlagen (DNB, Google Books, Open Library)" value="${escapeHtml(values.isbn||'')}" autocomplete="off" aria-label="ISBN nachschlagen">
      <button type="button" class="secondary-button" id="volume-lookup">Nachschlagen</button>
      <button type="button" class="secondary-button" id="volume-scan" title="Strichcode scannen">Scannen</button>
    </div>`}
    <div id="volume-note">${note}</div>
    <div id="volume-covers" class="mg-cover-choices">${coverChoices(covers)}</div>
    ${formSection('Band',[
      formField(values,['number','Bandnummer',{placeholder:'leer = Sonderband',inputmode:'decimal'}]),
      formField(values,['title','Titel',{placeholder:'Untertitel; bei Sonderbänden nötig'}]),
      formField(values,['variant','Variante',{list:'variant',placeholder:'leer = normal; z. B. Limited Edition'}]),
      formField(values,['isbn','ISBN',{inputmode:'numeric'}]),
      formField(values,['release_date','Erscheinung',{placeholder:'z. B. 2026-03 oder 14.03.2026'}]),
      `<label class="dl-field"><span>Listenpreis</span><span class="fig-price-input"><input class="dl-control" data-field="list_price" inputmode="decimal" value="${amountValue(values.list_price)}" aria-label="Listenpreis">${currencySelect(values.currency,suggestions.currencies)}</span></label>`,
      formField(values,['pages','Seiten',{inputmode:'numeric'}]),
    ].join(''))}
    ${formSection('Cover & Quelle',[
      formField(values,['image_url','Cover-Link',{wide:true,placeholder:'https://…/cover.jpg'}]),
      editing?'':`<label class="dl-field dl-field-wide"><span>… oder Cover hochladen</span><input class="dl-control" type="file" id="volume-image-file" accept="${PICTURE_TYPES}"></label>`,
      formField(values,['source_url','Link zur Quelle',{wide:true,placeholder:'https://…'}]),
      `<label class="dl-field dl-field-wide"><span>Beschreibung</span><textarea class="dl-control" data-field="description" rows="2">${escapeHtml(values.description||'')}</textarea></label>`,
      editing?'':`<label class="dl-field dl-field-wide"><span>Danach</span><select class="dl-control" id="volume-after">
        <option value="copy">Zur Sammlung hinzufügen</option><option value="open">Nur in den Katalog</option><option value="read">Zur Sammlung, schon gelesen</option><option value="preorder">Vorbestellen</option><option value="wish">Auf die Wunschliste</option></select></label>`,
    ].join(''))}
    ${datalist('suggest-variant',suggestions.variant)}
    <div class="dl-modal-actions"><button type="button" class="secondary-button" data-dialog-close>Abbrechen</button><span class="spacer"></span><button type="button" class="primary-button" data-save>${editing?'Speichern':'Band anlegen'}</button></div>`});
  $$('[data-dialog-close]',modal).forEach(button=>button.onclick=closeDialog);
  const fill=fields=>{for(const [key,value] of Object.entries(fields)){const input=$(`[data-field="${key}"]`,modal);if(input&&value!=null&&value!=='')input.value=value}};
  const wireCovers=()=>$$('[data-cover]',modal).forEach(button=>button.onclick=()=>{
    $('[data-field="image_url"]',modal).value=button.dataset.cover;
    $$('[data-cover]',modal).forEach(other=>other.classList.toggle('active',other===button));
  });
  wireCovers();
  const lookup=async isbn=>{
    isbn=String(isbn||$('#volume-isbn-lookup',modal).value).trim();
    if(!isbn){toast('Bitte eine ISBN eingeben.');return}
    const button=$('#volume-lookup',modal);button.disabled=true;button.textContent='Suche …';
    try{
      const result=await api(`/api/lookup/isbn/${encodeURIComponent(isbn.replace(/[^\dXx]/g,''))}`);
      if(result.match?.volume_id){closeDialog();toast('Dieser Band ist schon im Katalog');openVolume(result.match.volume_id);return}
      fill({isbn:result.isbn,...result.volume});
      $('#volume-note',modal).innerHTML=proposalNote(result);
      $('#volume-covers',modal).innerHTML=coverChoices(result.covers);wireCovers();
    }catch(error){$('#volume-note',modal).innerHTML=`<div class="fig-import-note warning"><b>Nicht gefunden</b><span>${escapeHtml(error.message)}</span></div>`}
    finally{button.disabled=false;button.textContent='Nachschlagen'}
  };
  $('#volume-lookup',modal)?.addEventListener('click',()=>lookup());
  $('#volume-isbn-lookup',modal)?.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();lookup()}});
  $('#volume-scan',modal)?.addEventListener('click',()=>openScanner({onIsbn:code=>{$('#volume-isbn-lookup',modal).value=code;lookup(code)}}));
  $('[data-save]',modal).onclick=async()=>{
    const fields=fieldValues(modal),force=forced(modal);
    if(!fields.number.trim()&&!fields.title.trim()){toast('Ein Band braucht eine Nummer, ein Sonderband einen Titel.');return}
    const editionId=values.edition_id??edition?.id;
    const saved=await saveWithDuplicateCheck(modal,'#volume-note',()=>editing?patch(`/api/volumes/${volumeId}`,{...fields,force}):post('/api/volumes',{...fields,edition_id:editionId,force}),
      {openLabel:'Vorhandenen öffnen',openExisting:id=>openVolume(id)});
    if(!saved)return;
    if(saved.image_error)toast(`Cover nicht geladen: ${saved.image_error}`);
    const file=$('#volume-image-file',modal)?.files[0];
    if(file)await uploadImage('volumes',saved.id,file).catch(error=>toast(error.message));
    const after=$('#volume-after',modal)?.value||'open';
    closeDialog();state.suggestions=null;refreshCounts();
    if(editing){toast('Band gespeichert');afterChange();return}
    if(after==='copy'||after==='read'){
      await post('/api/collection',{volume_id:saved.id,quantity:1,purchase_price:saved.currency==='EUR'?saved.list_price:null}).catch(error=>toast(error.message));
      if(after==='read')await api(`/api/volumes/${saved.id}/read`,{method:'PUT',body:'{}'}).catch(()=>{});
      toast(after==='read'?'Band angelegt, in der Sammlung und gelesen':'Band angelegt und zur Sammlung hinzugefügt');
    }else toast('Band angelegt');
    if(after==='wish')await post(`/api/watchlists/${defaultListId()}/volumes`,{volume_id:saved.id}).catch(error=>toast(error.message));
    afterChange();
    if(after==='preorder')openPreorderDialog(saved);
    else if(state.modalEdition?.id!==editionId)openEdition(editionId);
  };
}

// ---- A new manga: ISBN, barcode, link or by hand -------------------------------------------

// The entry point (＋ Manga): whatever is known -- an ISBN, a link, a title -- leads to the volume,
// creating what the catalogue lacks on the way: the series, the edition, the volume.
function openNewManga(prefill={}){
  const modal=openDialog({id:'new-manga',eyebrow:'NEU',title:'Manga hinzufügen',wide:true,
    intro:'Am schnellsten mit der ISBN von der Rückseite: eintippen oder scannen.',body:`
    <section class="fig-form-section"><h3>ISBN</h3>
      <div class="fig-import mg-isbn-row">
        <input class="dl-control" id="new-isbn" inputmode="numeric" placeholder="978-3-551-…" value="${escapeHtml(prefill.isbn||'')}" autocomplete="off" aria-label="ISBN">
        <button type="button" class="primary-button" id="new-isbn-go">Nachschlagen</button>
        <button type="button" class="secondary-button" id="new-scan">Scannen</button>
      </div>
    </section>
    <section class="fig-form-section"><h3>Link</h3>
      <div class="fig-import">
        <input class="dl-control" id="new-url" placeholder="Link zur Verlags- oder Shopseite" autocomplete="off" aria-label="Link">
        <button type="button" class="secondary-button" id="new-url-go">Daten holen</button>
        <small class="muted">Blockt eine Seite automatische Abrufe, hilft das Lesezeichen <a href="${bookmarkletHref()}" class="fig-bookmarklet" title="In die Lesezeichenleiste ziehen">„Zu Ophir Mangas“</a>: in die Lesezeichenleiste ziehen und auf der Seite anklicken.</small>
      </div>
    </section>
    <section class="fig-form-section"><h3>Von Hand</h3>
      <div class="fig-import"><input class="dl-control" id="new-series-query" placeholder="Reihe im Katalog suchen …" value="${escapeHtml(prefill.title||'')}" autocomplete="off" aria-label="Reihe suchen"><button type="button" class="secondary-button" id="new-series-create">＋ Neue Reihe</button></div>
      <div id="new-series-results" class="fig-pick-results"></div>
    </section>
    <div id="new-note"></div>`});
  const note=$('#new-note',modal);
  const lookup=async isbn=>{
    isbn=String(isbn||$('#new-isbn',modal).value).replace(/[^\dXx]/g,'');
    if(isbn.length!==10&&isbn.length!==13){toast('Eine ISBN hat 10 oder 13 Ziffern.');return}
    note.innerHTML='<p class="muted">Suche bei DNB, Google Books und Open Library …</p>';
    try{handleProposal(await api(`/api/lookup/isbn/${isbn}`))}
    catch(error){note.innerHTML=`<div class="fig-import-note warning"><b>Nicht nachgeschlagen</b><span>${escapeHtml(error.message)}</span></div>`}
  };
  $('#new-isbn-go',modal).onclick=()=>lookup();
  $('#new-isbn',modal).addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();lookup()}});
  $('#new-scan',modal).onclick=()=>openScanner({onIsbn:code=>{$('#new-isbn',modal).value=code;lookup(code)}});
  const fromLink=async()=>{
    const url=$('#new-url',modal).value.trim();
    if(!url){toast('Bitte einen Link einfügen.');return}
    note.innerHTML='<p class="muted">Seite wird gelesen …</p>';
    try{handleProposal(await post('/api/link-import',{url}))}
    catch(error){note.innerHTML=`<div class="fig-import-note warning"><b>Nicht übernommen</b><span>${escapeHtml(error.message)}</span></div>`}
  };
  $('#new-url-go',modal).onclick=fromLink;
  $('#new-url',modal).addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();fromLink()}});
  let timer,sequence=0;
  const findSeries=async()=>{
    const q=$('#new-series-query',modal).value.trim(),mine=++sequence,results=$('#new-series-results',modal);
    if(q.length<2){results.innerHTML='';return}
    const rows=await api(`/api/series?q=${encodeURIComponent(q)}&limit=12`).catch(()=>[]);
    if(mine!==sequence)return;
    results.innerHTML=rows.length?rows.map(row=>`<button type="button" class="search-result" data-pick-series="${row.id}"><img class="search-thumb fig-search-thumb" src="${seriesThumb(row)}" alt=""><div><b>${escapeHtml(row.title)}</b><small>${escapeHtml([row.original_title,row.authors,plural(row.editions,'Ausgabe','Ausgaben')].filter(Boolean).join(' · '))}</small></div></button>`).join('')
      :`<p class="muted">Nicht im Katalog. <button type="button" class="link-button" id="new-series-from-query">„${escapeHtml(q)}“ als neue Reihe anlegen</button></p>`;
    $$('[data-pick-series]',results).forEach(button=>button.onclick=()=>chooseEdition(Number(button.dataset.pickSeries)));
    $('#new-series-from-query',results)?.addEventListener('click',()=>startNewSeries({title:q}));
  };
  $('#new-series-query',modal).oninput=()=>{clearTimeout(timer);timer=setTimeout(findSeries,220)};
  $('#new-series-create',modal).onclick=()=>startNewSeries({title:$('#new-series-query',modal).value.trim()});
  if(prefill.isbn)lookup(prefill.isbn);
  else if(prefill.title)findSeries();
}

// Series -> edition -> volume, each form opening the next with what is known.
function startNewSeries(series,carried={}){
  openSeriesForm(series,{onSaved:saved=>startNewEdition(saved,carried)});
}
async function startNewEdition(series,{edition={},volume={},covers=[],note=''}={}){
  let full=series;
  if(!series.title){try{full=await api(`/api/series/${series.id}`)}catch(error){toast(error.message);return}}
  openEditionForm({...edition,series_id:full.id},{series:full,onSaved:saved=>openVolumeForm(
    {...volume,edition_id:saved.id,list_price:volume.list_price??saved.list_price,currency:volume.currency||saved.currency},{edition:saved,covers,note})});
}

// The editions of a series to put the volume into, or a new one.
async function chooseEdition(seriesId,{edition={},volume={},covers=[],note=''}={}){
  let series;
  try{series=await api(`/api/series/${seriesId}`)}catch(error){toast(error.message);return}
  const modal=openDialog({id:'choose-edition',eyebrow:'AUSGABE WÄHLEN',title:escapeHtml(series.title),intro:'In welche Ausgabe gehört der Band?',body:`
    <div class="mg-other-editions">${series.editions.map(item=>`<button type="button" class="mg-other-edition" data-choose="${item.id}"><img src="${coverThumb(item.cover,series.id)}" alt=""><span><b>${escapeHtml(item.name)}</b><small>${escapeHtml(editionSubtitle(item))}${item.catalogued?` · ${plural(item.catalogued,'Band','Bände')} im Katalog`:''}</small></span></button>`).join('')||'<p class="muted">Diese Reihe hat noch keine Ausgabe.</p>'}</div>
    <div class="dl-modal-actions"><button type="button" class="secondary-button" data-dialog-close>Abbrechen</button><span class="spacer"></span><button type="button" class="primary-button" id="choose-new-edition">＋ Neue Ausgabe</button></div>`});
  $$('[data-dialog-close]',modal).forEach(button=>button.onclick=closeDialog);
  $$('[data-choose]',modal).forEach(button=>button.onclick=async()=>{
    let chosen;
    try{chosen=await api(`/api/editions/${button.dataset.choose}`)}catch(error){toast(error.message);return}
    if(volume.number||volume.isbn||volume.title)openVolumeForm({...volume,edition_id:chosen.id,list_price:volume.list_price??chosen.list_price,currency:volume.currency||chosen.currency},{edition:chosen,covers,note});
    else openNextVolumeForm(chosen);
  });
  $('#choose-new-edition',modal).onclick=()=>startNewEdition(series,{edition,volume,covers,note});
}

// What a lookup or a link import found, and where it fits in the catalogue.
async function handleProposal(result){
  const volume={...(result.volume||{}),isbn:result.volume?.isbn||result.isbn||''};
  const covers=result.covers||[],note=proposalNote(result),match=result.match||{};
  if(match.volume_id){closeDialog();toast('Dieser Band ist schon im Katalog');openVolume(match.volume_id);return}
  if(match.edition_id){
    try{
      const edition=await api(`/api/editions/${match.edition_id}`);
      openVolumeForm({...volume,edition_id:edition.id,list_price:volume.list_price??edition.list_price,currency:volume.currency||edition.currency},{edition,covers,note});
    }catch(error){toast(error.message)}
    return;
  }
  if(match.series_id){chooseEdition(match.series_id,{edition:result.edition||{},volume,covers,note});return}
  startNewSeries(result.series||{},{edition:result.edition||{},volume,covers,note});
}

// ---- The bookmarklet ----------------------------------------------------------------------------

// Runs on a product page in the user's own browser: gathers meta tags, JSON-LD and label/value
// pairs (as ophir_mangas/link_import.py reads them) and opens the app with them in the address's
// fragment, which never reaches a server log. The page is only read, never changed or sent elsewhere.
function bookmarkletHref(){
  const code=`(()=>{const d=document,m={},j=[],f={};d.querySelectorAll('meta[property],meta[name],meta[itemprop]').forEach(e=>{const k=e.getAttribute('property')||e.getAttribute('name')||e.getAttribute('itemprop');if(k&&e.content&&!(k in m))m[k]=e.content.slice(0,2000)});d.querySelectorAll('script[type="application/ld+json"]').forEach(s=>{try{j.push(JSON.parse(s.textContent))}catch(e){}});const a=(l,v)=>{l=(l||'').replace(/\\s+/g,' ').trim().replace(/[:：]$/,'');v=(v||'').replace(/\\s+/g,' ').trim();if(l&&v&&l.length<60&&!(l in f))f[l]=v.slice(0,500)};d.querySelectorAll('.data-field').forEach(e=>a(e.querySelector('.data-label')?.innerText,e.querySelector('.data-value')?.innerText));d.querySelectorAll('dt').forEach(e=>{const n=e.nextElementSibling;if(n&&n.tagName=='DD')a(e.innerText,n.innerText)});d.querySelectorAll('tr').forEach(r=>{const c=r.querySelectorAll(':scope>th,:scope>td');if(c.length==2)a(c[0].innerText,c[1].innerText)});const b={url:location.href,canonical:d.querySelector('link[rel=canonical]')?.href||'',title:d.title,heading:d.querySelector('h1')?.innerText||'',meta:m,jsonld:j,fields:f};let s=JSON.stringify(b);if(s.length>400000){b.jsonld=[];s=JSON.stringify(b)}const u='${location.origin}${APP_ROOT}/#import='+encodeURIComponent(s);window.open(u,'_blank')||(location.href=u)})()`;
  return `javascript:${encodeURIComponent(code)}`;
}

// The app opened by the bookmarklet: read what it brought and go on from there.
async function handleImportFragment(){
  if(!location.hash.startsWith('#import='))return;
  let snapshot;
  try{snapshot=JSON.parse(decodeURIComponent(location.hash.slice('#import='.length)))}catch{toast('Die Seitendaten vom Lesezeichen waren unvollständig.');return}
  finally{history.replaceState(null,'',location.pathname)}
  try{await handleProposal(await post('/api/link-import',{snapshot}))}catch(error){toast(error.message)}
}
