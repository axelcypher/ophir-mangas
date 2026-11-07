// The views: catalogue, collection, reading, gaps, release calendar, wishlists, preorders.

const CATALOG_MODES=[['all','Alle'],['owned','In der Sammlung'],['missing','Nicht in der Sammlung'],['collecting','Sammle ich'],['wished','Gewünscht'],['preordered','Vorbestellt']];
const CATALOG_VOLUME_MODES=[['all','Alle'],['owned','In der Sammlung'],['missing','Nicht in der Sammlung'],['upcoming','Noch nicht erschienen'],['wished','Gewünscht']];
const COLLECTION_MODES=[['all','Alle'],['collecting','Sammle ich'],['gaps','Mit Lücken'],['complete','Vollständig'],['unread','Mit Ungelesenen']];
const COLLECTION_VOLUME_MODES=[['all','Alle'],['unread','Ungelesen'],['read','Gelesen'],['preordered','Vorbestellt']];
const EDITION_SORTS=['title','added','release','next','progress','value','publisher'];
const VOLUME_SORTS=['title','release','added','value'];

function pageHead({eyebrow,title,text,actions=''}){
  return `<div class="page-head compact-page-head fig-page-head"><div><span class="eyebrow">${eyebrow}</span><h1>${title}</h1>${text?`<p>${text}</p>`:''}</div>${actions?`<div class="fig-head-actions">${actions}</div>`:''}</div>`;
}
const loader=text=>`<div class="page-loader"><span></span><p>${text}</p></div>`;
const failed=(title,error)=>`<div class="empty-state"><b>${title}</b><span>${escapeHtml(error.message)}</span></div>`;

// The line over a grid: how many editions, volumes or groups it shows of how many.
function gridCount(data,grouping){
  const volumes=grouping.by==='volumes';
  const [one,many]=volumes?['Band','Bände']:['Ausgabe','Ausgaben'];
  const counted=data.shown===data.total?plural(data.total,one,many):`${data.shown} von ${data.total} ${many}`;
  return data.groups?`${plural(data.groups.length,groupingLabel(grouping.by),groupingLabel(grouping.by,true))} · ${counted}`:counted;
}

// A view's filter reset keeps the open group: it is where the user is, not a filter they set.
function resetFilters(filters,defaults,grouping){
  Object.assign(filters,defaults);
  if(grouping.open)filters[GROUP_FIELD[grouping.open.by]]=grouping.open.name||NONE_VALUE;
}

const editionGroupStats=group=>({lines:[`${plural(group.count,'Ausgabe','Ausgaben')}${group.volumes?` · ${plural(group.volumes,'Band','Bände')} vorhanden`:''}`,
  group.gaps?`<span class="mg-warn">${plural(group.gaps,'Lücke','Lücken')}</span>`:group.read?`${group.read} gelesen`:''],share:group.owned/group.count});

// ---- Catalogue ----------------------------------------------------------------------------------

async function renderCatalog(){
  const stale=renderGuard(),filters=state.catalogFilters,grouping=state.grouping.catalog;
  syncOpenGroup(filters,grouping);
  const volumes=grouping.by==='volumes';
  if(volumes&&!CATALOG_VOLUME_MODES.some(([key])=>key===filters.mode))filters.mode='all';
  if(!volumes&&!CATALOG_MODES.some(([key])=>key===filters.mode))filters.mode='all';
  if(!$('#catalog-grid'))content.innerHTML=loader('Katalog wird geladen …');
  let data;
  try{data=await api(volumes?`/api/volumes?${filterQuery(filters)}`:`/api/editions?${gridQuery(filters,grouping)}`)}
  catch(error){if(!stale())content.innerHTML=failed('Katalog nicht erreichbar',error);return}
  if(stale())return;
  const items=(volumes?data.volumes:data.editions)||[];
  content.innerHTML=`${pageHead({eyebrow:'GEMEINSAMER KATALOG',title:'Katalog',text:`${plural(volumes?data.total:data.stats.editions,volumes?'Band':'Ausgabe',volumes?'Bände':'Ausgaben')} – von allen Konten gepflegt. Fehlt etwas, leg es an.`,
      actions:'<button type="button" class="secondary-button" data-scan-here>Scannen</button><button type="button" class="primary-button" id="catalog-create">＋ Manga</button>'})}
    ${groupSwitch('catalog')}
    ${grouping.open?groupHead('catalog',{count:items.length,owned:items.filter(item=>item.owned).length}):''}
    ${filterBar({key:'catalog',filters,facets:data.facets,modes:volumes?CATALOG_VOLUME_MODES:CATALOG_MODES,sorts:volumes?VOLUME_SORTS:EDITION_SORTS,grouping})}
    <p class="fig-count muted">${gridCount(data,grouping)}</p>
    <div id="catalog-grid"></div>`;
  mountFilterPanel('catalog',['.fig-filter-row']);
  wireFilterBar(content,filters,renderCatalog,()=>resetFilters(filters,defaultCatalogFilters(),grouping));
  wireGroups(content,'catalog',filters,renderCatalog);
  $('#catalog-create').onclick=()=>openNewManga({title:filters.q||''});
  $('[data-scan-here]',content).onclick=scanToVolume;
  const empty=`<div class="empty-state"><b>${data.total?'Nichts passt zu den Filtern':'Der Katalog ist noch leer'}</b><span>${data.total?'Ändere die Filter oder ':''}Leg den ersten Manga an – am schnellsten mit der ISBN.</span><button type="button" class="primary-button" data-empty-create>＋ Manga</button></div>`;
  if(data.groups)renderGroupGrid($('#catalog-grid'),'catalog',data.groups,{stats:editionGroupStats,empty,onOpen:name=>openGroup('catalog',filters,name,renderCatalog)});
  else renderGrid($('#catalog-grid'),items,{tile:volumes?volume=>volumeTile(volume):edition=>editionTile(edition),empty});
  $('[data-empty-create]',content)?.addEventListener('click',()=>openNewManga({title:filters.q||''}));
}

// The barcode straight to its volume: in the catalogue it opens, else the lookup takes over.
function scanToVolume(){
  openScanner({onIsbn:async code=>{
    try{const volume=await api(`/api/volumes/by-isbn/${code}`);openVolume(volume.id)}
    catch(error){if(error.status===404)openNewManga({isbn:code});else toast(error.message)}
  }});
}

// ---- Collection ---------------------------------------------------------------------------------

async function renderCollection(){
  const stale=renderGuard(),filters=state.collectionFilters,grouping=state.grouping.collection;
  syncOpenGroup(filters,grouping);
  const volumes=grouping.by==='volumes';
  if(volumes&&!COLLECTION_VOLUME_MODES.some(([key])=>key===filters.mode))filters.mode='all';
  if(!volumes&&!COLLECTION_MODES.some(([key])=>key===filters.mode))filters.mode='all';
  if(!$('#collection-grid'))content.innerHTML=loader('Sammlung wird geladen …');
  let data;
  try{data=await api(`/api/collection?${gridQuery(filters,grouping)}`)}catch(error){if(!stale())content.innerHTML=failed('Sammlung nicht erreichbar',error);return}
  if(stale())return;
  const items=(volumes?data.volumes:data.editions)||[];
  const stats=data.stats;
  const owned=volumes?stats.volumes:stats.editions;
  const conditionSelect=volumes?`<label class="fig-filter"><span>Zustand</span><select class="select-control" data-filter="condition"><option value="">Alle</option>${Object.entries(data.conditions).map(([key,label])=>`<option value="${key}" ${filters.condition===key?'selected':''}>${escapeHtml(label)}</option>`).join('')}</select></label>`:'';
  const summary=volumes
    ?[{label:'Bände',value:stats.volumes},{label:'Exemplare',value:stats.copies},{label:'Gelesen',value:stats.read},{label:'Wert',value:money(stats.value)}]
    :[{label:'Reihen',value:stats.series},{label:'Bände',value:stats.volumes},{label:'Ungelesen',value:stats.unread,className:stats.unread?'missing':''},{label:'Lücken',value:stats.gaps,className:stats.gaps?'missing':''},{label:'Wert',value:money(stats.value)},{label:'Ausgegeben',value:money(stats.spent)}];
  content.innerHTML=`${pageHead({eyebrow:'MEINE SAMMLUNG',title:'Sammlung',text:owned?'Was im Regal steht, was gelesen ist und was fehlt.':'',
      actions:'<button type="button" class="secondary-button" data-scan-here>Scannen</button><button type="button" class="secondary-button" id="collection-add">＋ Hinzufügen</button>'})}
    ${statPill(summary,{className:'fig-summary',columns:summary.length,mobileColumns:2})}
    ${owned||grouping.by?groupSwitch('collection'):''}
    ${grouping.open?groupHead('collection',{count:items.length}):''}
    ${filterBar({key:'collection',filters,facets:data.facets,modes:volumes?COLLECTION_VOLUME_MODES:COLLECTION_MODES,sorts:volumes?VOLUME_SORTS:EDITION_SORTS,extraFacets:volumes?['location']:[],extra:conditionSelect,grouping})}
    <p class="muted fig-count">${gridCount(data,grouping)}${volumes&&stats.unpriced?` · ${plural(stats.unpriced,'Exemplar hat','Exemplare haben')} keinen Kaufpreis – es zählt der Listenpreis.`:''}</p>
    <div id="collection-grid"></div>`;
  mountFilterPanel('collection',['.fig-filter-row']);
  wireFilterBar(content,filters,renderCollection,()=>resetFilters(filters,defaultCollectionFilters(),grouping));
  wireGroups(content,'collection',filters,renderCollection);
  $('#collection-add').onclick=()=>openNewManga();
  $('[data-scan-here]',content).onclick=scanToVolume;
  const empty=owned?'<div class="empty-state"><b>Nichts passt zu den Filtern</b><span>Ändere oder setze die Filter zurück.</span></div>'
    :'<div class="empty-state"><b>Deine Sammlung ist noch leer</b><span>Scanne die ISBN eines Bands oder such eine Reihe im Katalog.</span><button type="button" class="primary-button" data-first-manga>＋ Manga</button></div>';
  if(data.groups)renderGroupGrid($('#collection-grid'),'collection',data.groups,{stats:editionGroupStats,empty,onOpen:name=>openGroup('collection',filters,name,renderCollection)});
  else if(volumes)renderGrid($('#collection-grid'),items,{empty,tile:volume=>volumeTile(volume,{value:volume.value||null,
    note:[volume.conditions.map(conditionLabel).join(', '),volume.locations.length?`📍 ${volume.locations.join(', ')}`:''].filter(Boolean).map(escapeHtml).join(' · ')})});
  else renderGrid($('#collection-grid'),items,{empty,tile:edition=>editionTile(edition,{note:edition.gap_count?`<span class="mg-warn">Fehlt: ${escapeHtml(edition.gaps.slice(0,6).join(', '))}${edition.gaps.length>6?' …':''}</span>`:''})});
  $('[data-first-manga]',content)?.addEventListener('click',()=>openNewManga());
}

// ---- Reading ------------------------------------------------------------------------------------

async function renderReading(){
  const stale=renderGuard();
  if(!$('#reading-list'))content.innerHTML=loader('Lesestand wird geladen …');
  let data;
  try{data=await api('/api/reading')}catch(error){if(!stale())content.innerHTML=failed('Lesestand nicht erreichbar',error);return}
  if(stale())return;
  const filter=state.readingStatus;
  const rows=data.series.filter(item=>!filter||(item.status||'none')===filter);
  const tabs=[['','Alle',data.series.length],...Object.entries(data.statuses).map(([key,label])=>[key,label,data.counts[key]]),['none','Ohne Status',data.counts.none]].filter(([key,,count])=>!key||count);
  const groups=[];
  for(const row of rows){
    const label=row.status?readingLabel(row.status):'Ohne Lesestatus';
    if(!groups.length||groups.at(-1).label!==label)groups.push({label,rows:[]});
    groups.at(-1).rows.push(row);
  }
  content.innerHTML=`${pageHead({eyebrow:'LESEN',title:'Lesen',text:'Was du gerade liest, als Nächstes lesen willst und schon durch hast.'})}
    ${statPill([{label:'Lese ich',value:data.counts.reading},{label:'Geplant',value:data.counts.planned},{label:'Fertig',value:data.counts.finished},
      {label:'Ungelesen im Regal',value:data.series.reduce((sum,item)=>sum+item.unread_owned,0)}],{className:'fig-summary',columns:4,mobileColumns:2})}
    <div class="segmented fig-modes mg-reading-tabs" data-scroll-x>${tabs.map(([key,label,count])=>`<button type="button" data-reading-tab="${key}" class="${filter===key?'active':''}">${escapeHtml(label)} <small>${count}</small></button>`).join('')}</div>
    <div id="reading-list">${groups.length?groups.map(group=>`<section class="mg-reading-group"><h2>${escapeHtml(group.label)} <small>${group.rows.length}</small></h2>${group.rows.map(readingRow).join('')}</section>`).join('')
      :'<div class="empty-state"><b>Noch nichts gelesen</b><span>Markiere Bände als gelesen oder gib einer Reihe einen Lesestatus – im Dialog der Ausgabe.</span></div>'}</div>`;
  $$('[data-reading-tab]',content).forEach(button=>button.onclick=()=>{state.readingStatus=button.dataset.readingTab;renderReading()});
  $$('[data-open-edition]',content).forEach(element=>element.onclick=()=>openEdition(Number(element.dataset.openEdition)));
  $$('[data-read-next]',content).forEach(button=>button.onclick=()=>setRead(Number(button.dataset.readNext),true));
  $$('[data-open-volume]',content).forEach(button=>button.onclick=()=>openVolume(Number(button.dataset.openVolume)));
  $$('[data-reading-status]',content).forEach(select=>select.onchange=async()=>{
    try{await api(`/api/series/${select.dataset.readingStatus}/reading`,{method:'PUT',body:JSON.stringify({status:select.value})});toast('Lesestatus gespeichert');refreshCounts();renderReading()}
    catch(error){toast(error.message)}
  });
}

function readingRow(row){
  const edition=row.edition,total=edition.total||0;
  const statuses=Object.entries(state.boot.reading_statuses||{});
  return `<div class="mg-reading-row">
    <img class="mg-reading-cover" loading="lazy" src="${coverThumb(edition.cover,row.series_id)}" alt="" data-open-edition="${edition.id}">
    <div class="mg-reading-main">
      <b data-open-edition="${edition.id}">${escapeHtml(row.series_title)}</b>
      <small>${escapeHtml([edition.name!==row.series_title?edition.name:'',edition.publisher,languageLabel(edition.language)].filter(Boolean).join(' · '))}${row.editions>1?` · ${row.editions} Ausgaben`:''}</small>
      <span class="mg-reading-progress"><span class="mg-progress" role="img" aria-label="${edition.read_numbers} von ${total||'?'} gelesen"><i class="mg-progress-owned" style="--share:${share(edition.owned,total)}%"></i><i class="mg-progress-read" style="--share:${share(edition.read_numbers,total)}%"></i></span><small>${edition.read_numbers} von ${total||'?'} gelesen${row.unread_owned?` · ${row.unread_owned} ungelesen im Regal`:''}</small></span>
    </div>
    <div class="mg-reading-side">
      ${row.next?`<span class="mg-reading-next"><button type="button" class="link-button" data-open-volume="${row.next.id}">Als Nächstes: Band ${escapeHtml(row.next.number_label)}${row.next.owned?'':' <small>(nicht im Regal)</small>'}</button><button type="button" class="secondary-button" data-read-next="${row.next.id}" title="Band ${escapeHtml(row.next.number_label)} als gelesen markieren">✓ Gelesen</button></span>`:edition.status==='completed'&&edition.read_numbers>=total&&total?'<span class="mg-done">Alles gelesen</span>':'<span class="muted">Auf dem neuesten Stand</span>'}
      <select class="select-control" data-reading-status="${row.series_id}" aria-label="Lesestatus von ${escapeHtml(row.series_title)}"><option value="">Kein Status</option>${statuses.map(([key,label])=>`<option value="${key}" ${row.status===key?'selected':''}>${escapeHtml(label)}</option>`).join('')}</select>
    </div>
  </div>`;
}

// ---- Gaps ---------------------------------------------------------------------------------------

async function renderGaps(){
  const stale=renderGuard();
  if(!$('#gap-list'))content.innerHTML=loader('Lücken werden gesucht …');
  let data;
  try{data=await api('/api/gaps')}catch(error){if(!stale())content.innerHTML=failed('Lücken nicht erreichbar',error);return}
  if(stale())return;
  const stats=data.stats;
  content.innerHTML=`${pageHead({eyebrow:'PLANUNG',title:'Lücken',text:'Erschienene Bände der Ausgaben, die du sammelst, die dir noch fehlen.'})}
    ${statPill([{label:'Fehlende Bände',value:stats.gaps,className:stats.gaps?'missing':''},{label:'In Ausgaben',value:stats.editions},
      {label:'Nicht im Katalog',value:stats.uncatalogued},{label:'Zum Listenpreis',value:money(stats.estimate)}],{className:'fig-summary',columns:4,mobileColumns:2})}
    <div id="gap-list">${data.editions.length?data.editions.map(gapEdition).join('')
      :`<div class="empty-state"><b>${state.boot.counts.collecting?'Keine Lücken – alles da':'Noch sammelst du keine Ausgabe'}</b><span>${state.boot.counts.collecting?'Von jeder Ausgabe, die du sammelst, hast du alle erschienenen Bände.':'Öffne eine Ausgabe und tippe auf „Sammle ich“: Dann siehst du hier, welche Bände fehlen, und unter Neuerscheinungen, was kommt.'}</span></div>`}</div>`;
  $$('[data-open-edition]',content).forEach(element=>element.onclick=()=>openEdition(Number(element.dataset.openEdition)));
  $$('[data-gap-own]',content).forEach(button=>button.onclick=()=>quickAddVolume(Number(button.dataset.gapOwn)));
  $$('[data-gap-wish]',content).forEach(button=>button.onclick=()=>toggleVolumeWish(Number(button.dataset.gapWish),button));
  $$('[data-gap-run]',content).forEach(button=>button.onclick=async()=>{
    const [editionId,from,to]=button.dataset.gapRun.split(':').map(Number);
    try{const result=await post(`/api/editions/${editionId}/volumes`,{from,to});toast(`${plural(result.created.length,'Band','Bände')} im Katalog angelegt`);renderGaps()}
    catch(error){toast(error.message)}
  });
  $$('[data-gap-create]',content).forEach(button=>button.onclick=async()=>{
    const [editionId,number]=button.dataset.gapCreate.split(':');
    try{const edition=await api(`/api/editions/${editionId}`);openVolumeForm({edition_id:edition.id,number,list_price:edition.list_price,currency:edition.currency},{edition})}catch(error){toast(error.message)}
  });
}

// The gaps of an edition as rows: a catalogued volume with its buttons, and numbers the catalogue
// lacks in runs (6-34), which can be created at once.
function gapRows(gaps){
  const rows=[];
  for(const gap of gaps){
    const number=Number(gap.number_label),last=rows.at(-1);
    if(!gap.volume&&Number.isInteger(number)&&last?.run&&last.to===number-1)last.to=number;
    else rows.push(gap.volume?{gap}:{run:Number.isInteger(number),from:number,to:number,label:gap.number_label});
  }
  return rows;
}

function gapEdition(edition){
  const row=item=>{
    if(item.gap){
      const {gap}=item;
      return `<div class="mg-gap-volume"><img loading="lazy" src="${volumeThumb(gap.volume)}" alt=""><span><b>Band ${escapeHtml(gap.number_label)}</b><small>${escapeHtml([partialDate(gap.volume.release_date),gap.volume.list_price!=null?currencyMoney(gap.volume.list_price,gap.volume.currency):''].filter(Boolean).join(' · '))}</small></span>
        <span class="mg-gap-actions"><button type="button" class="icon-button${gap.volume.wished?' active':''}" data-gap-wish="${gap.volume.id}" title="Auf die Wunschliste" aria-label="Band ${escapeHtml(gap.number_label)} auf die Wunschliste">♡</button><button type="button" class="secondary-button" data-gap-own="${gap.volume.id}" title="Als gekauft eintragen">＋ Habe ich</button></span></div>`;
    }
    const many=item.run&&item.to>item.from,label=many?`${item.from}–${item.to}`:escapeHtml(item.label);
    return `<div class="mg-gap-volume mg-gap-uncatalogued"><span class="mg-gap-number">${many?'…':label}</span><span><b>${many?`Bände ${label}`:`Band ${label}`}</b><small>${many?`${item.to-item.from+1} Bände nicht im Katalog`:'nicht im Katalog'}</small></span>
      <span class="mg-gap-actions"><button type="button" class="secondary-button" ${many?`data-gap-run="${edition.id}:${item.from}:${item.to}"`:`data-gap-create="${edition.id}:${escapeHtml(item.label)}"`}>${many?'Alle anlegen':'Anlegen'}</button></span></div>`;
  };
  return `<section class="mg-gap-edition">
    <div class="mg-gap-head" data-open-edition="${edition.id}">
      <img loading="lazy" src="${coverThumb(edition.cover,edition.series_id)}" alt="">
      <span><b>${escapeHtml(edition.name)}</b><small>${escapeHtml([edition.publisher,languageLabel(edition.language)].filter(Boolean).join(' · '))} · ${edition.owned_numbers} von ${edition.total||edition.released_through||'?'} vorhanden</small></span>
      <span class="fig-mark mg-mark-gaps">${plural(edition.gap_count,'fehlt','fehlen')}</span>
    </div>
    <div class="mg-gap-volumes">${gapRows(edition.gaps).map(row).join('')}</div>
  </section>`;
}

// ---- Release calendar ---------------------------------------------------------------------------

async function renderCalendar(){
  const stale=renderGuard();
  if(!$('#calendar-list'))content.innerHTML=loader('Neuerscheinungen werden geladen …');
  let data;
  try{data=await api('/api/calendar?months=12')}catch(error){if(!stale())content.innerHTML=failed('Neuerscheinungen nicht erreichbar',error);return}
  if(stale())return;
  const upcoming=data.months.reduce((sum,month)=>sum+month.volumes.length,0);
  const month=thisMonth();
  content.innerHTML=`${pageHead({eyebrow:'PLANUNG',title:'Neuerscheinungen',text:'Die nächsten Bände der Ausgaben, die du sammelst, und von deinen Wunschlisten.'})}
    ${statPill([{label:'Kommen',value:upcoming},{label:'Diesen Monat',value:data.months.find(item=>item.month===month)?.volumes.length||0},
      {label:'Neu, noch nicht gekauft',value:data.recent.length,className:data.recent.length?'missing':''},{label:'Ohne Termin',value:data.undated}],{className:'fig-summary',columns:4,mobileColumns:2})}
    <div id="calendar-list">
      ${data.recent.length?`<section class="mg-calendar-month mg-calendar-recent"><h2>Gerade erschienen <small>${data.recent.length}</small></h2><div class="mg-calendar-rows">${data.recent.map(calendarRow).join('')}</div></section>`:''}
      ${data.months.map(item=>`<section class="mg-calendar-month"><h2>${item.month===month?'Diesen Monat · ':''}${escapeHtml(partialDate(item.month))} <small>${item.volumes.length}</small></h2><div class="mg-calendar-rows">${item.volumes.map(calendarRow).join('')}</div></section>`).join('')}
      ${!upcoming&&!data.recent.length?`<div class="empty-state"><b>Nichts angekündigt</b><span>${state.boot.counts.collecting?'Für deine gesammelten Ausgaben ist im Katalog kein neuer Band mit Termin eingetragen. Leg angekündigte Bände mit ihrem Erscheinungstermin an.':'Öffne eine Ausgabe und tippe auf „Sammle ich“ – dann erscheinen ihre kommenden Bände hier.'}</span></div>`:''}
    </div>`;
  $$('[data-open-volume]',content).forEach(element=>element.onclick=()=>openVolume(Number(element.dataset.openVolume)));
  $$('[data-calendar-own]',content).forEach(button=>button.onclick=()=>quickAddVolume(Number(button.dataset.calendarOwn)));
  $$('[data-calendar-preorder]',content).forEach(button=>button.onclick=async()=>{
    try{openPreorderDialog(await api(`/api/volumes/${button.dataset.calendarPreorder}`))}catch(error){toast(error.message)}
  });
}

function calendarRow(volume){
  const actions=volume.owned?'<span class="fig-mark owned">Im Regal</span>'
    :volume.preordered?'<span class="fig-mark preordered">Vorbestellt</span>'
    :volume.released?`<button type="button" class="secondary-button" data-calendar-own="${volume.id}">＋ Habe ich</button>`
    :`<button type="button" class="secondary-button" data-calendar-preorder="${volume.id}">Vorbestellen</button>`;
  return `<div class="mg-calendar-row">
    <span class="mg-calendar-date">${escapeHtml(volume.release_date.length>=10?`${volume.release_date.slice(8,10)}.${volume.release_date.slice(5,7)}.`:'–')}</span>
    <img loading="lazy" src="${volumeThumb(volume)}" alt="" data-open-volume="${volume.id}">
    <span class="mg-calendar-main" data-open-volume="${volume.id}"><b>${escapeHtml(volume.edition_name)} · ${escapeHtml(volumeLabel(volume))}</b><small>${escapeHtml([volume.variant,volume.publisher,volume.list_price!=null?currencyMoney(volume.list_price,volume.currency):'',volume.collecting?'':'Wunschliste'].filter(Boolean).join(' · '))}</small></span>
    <span class="mg-calendar-actions">${actions}</span>
  </div>`;
}

// ---- Wishlists ----------------------------------------------------------------------------------

async function renderWatchlist(listId){
  const stale=renderGuard(),filters=state.watchFilters,grouping=state.grouping.watch;
  const lists=state.boot.watchlists;
  if(listId)state.watchlistId=listId;
  if(!lists.some(list=>list.id===state.watchlistId))state.watchlistId=lists.find(list=>list.is_default)?.id||lists[0]?.id;
  syncOpenGroup(filters,grouping);
  const volumes=grouping.by==='volumes';
  if(!volumes&&!['wished',...EDITION_SORTS].includes(filters.sort))filters.sort='wished';
  if(!$('#watch-grid'))content.innerHTML=loader('Wunschliste wird geladen …');
  let data;
  try{data=await api(`/api/watchlists/${state.watchlistId}/entries?${gridQuery(filters,grouping)}`)}catch(error){if(!stale())content.innerHTML=failed('Liste nicht erreichbar',error);return}
  if(stale())return;
  const list=data.list,stats=data.list_stats,items=(volumes?data.volumes:data.editions)||[];
  const count=stats.editions+stats.volumes;
  content.innerHTML=`${pageHead({eyebrow:'WUNSCHLISTEN',title:escapeHtml(list.name),text:'Ganze Ausgaben, die du anfangen willst, und einzelne Bände, die du suchst – mit Zielpreis wird markiert, was gerade günstig ist.',
      actions:`<button type="button" class="secondary-button" id="watch-new">＋ Neue Liste</button>${list.is_default?'':'<button type="button" class="secondary-button" id="watch-rename">Umbenennen</button><button type="button" class="icon-button" id="watch-delete" title="Liste löschen" aria-label="Liste löschen">✕</button>'}`})}
    <div class="fig-list-tabs" data-scroll-x>${lists.map(item=>`<button type="button" class="fig-list-tab${item.id===list.id?' active':''}" data-list="${item.id}">${escapeHtml(item.name)} <small>${item.count}</small></button>`).join('')}</div>
    ${statPill([
      {label:'Ganze Ausgaben',value:stats.whole},{label:'Einzelne Bände',value:stats.volumes},
      {label:'Zielpreis erreicht',value:stats.target_reached,className:stats.target_reached?'complete':''},{label:'Geschätzt',value:money(stats.estimate)},
    ],{className:'fig-summary',columns:4,mobileColumns:2})}
    ${count?groupSwitch('watch'):''}
    ${grouping.open?groupHead('watch',{count:items.length}):''}
    ${filterBar({key:'watch',filters,facets:data.facets,modes:volumes?[['all','Alle'],['missing','Noch nicht in der Sammlung']]:null,sorts:volumes?['wished',...VOLUME_SORTS]:['wished',...EDITION_SORTS],grouping})}
    ${count?`<p class="muted fig-count">${gridCount(data,grouping)}</p>`:''}
    <div id="watch-grid"></div>`;
  mountFilterPanel('watch',['.fig-filter-row']);
  wireFilterBar(content,filters,()=>renderWatchlist(),()=>resetFilters(filters,defaultWatchFilters(),grouping));
  wireGroups(content,'watch',filters,()=>renderWatchlist());
  $$('[data-list]',content).forEach(button=>button.onclick=()=>renderWatchlist(Number(button.dataset.list)));
  $('#watch-new').onclick=async()=>{
    const name=prompt('Name der neuen Liste');if(!name)return;
    try{const created=await post('/api/watchlists',{name});await refreshCounts();renderWatchlist(created.id)}catch(error){toast(error.message)}
  };
  $('#watch-rename',content)?.addEventListener('click',async()=>{
    const name=prompt('Neuer Name der Liste',list.name);if(!name||name===list.name)return;
    try{await patch(`/api/watchlists/${list.id}`,{name});await refreshCounts();renderWatchlist(list.id)}catch(error){toast(error.message)}
  });
  $('#watch-delete',content)?.addEventListener('click',async()=>{
    if(!confirm(`Liste „${list.name}“ mit ${plural(count,'Eintrag','Einträgen')} löschen?`))return;
    try{await del(`/api/watchlists/${list.id}`);await refreshCounts();renderWatchlist(defaultListId())}catch(error){toast(error.message)}
  });
  const empty=count?'<div class="empty-state"><b>Nichts passt zu den Filtern</b><span>Ändere oder setze die Filter zurück.</span></div>'
    :'<div class="empty-state"><b>Die Liste ist leer</b><span>Das Herz auf einer Ausgabe wünscht sie ganz, das Herz auf einem Band nur diesen Band.</span><button type="button" class="primary-button" data-route-catalog>Zum Katalog</button></div>';
  if(data.groups)renderGroupGrid($('#watch-grid'),'watch',data.groups,{stats:editionGroupStats,empty,onOpen:name=>openGroup('watch',filters,name,()=>renderWatchlist())});
  else if(volumes)renderGrid($('#watch-grid'),items,{empty,tile:volume=>volumeTile(volume,{
    badge:volume.target_reached?'<span class="fig-mark reached" title="Marktwert am oder unter dem Zielpreis">Ziel ✓</span>':'',
    note:[volume.target_price!=null?`Ziel ${money(volume.target_price)}`:'',volume.note].filter(Boolean).map(escapeHtml).join(' · ')})});
  else renderGrid($('#watch-grid'),items,{empty,tile:edition=>editionTile(edition,{
    badge:edition.target_reached?'<span class="fig-mark reached" title="Am Zielpreis">Ziel ✓</span>':'',
    note:edition.whole?`Ganze Ausgabe${edition.note?` · ${escapeHtml(edition.note)}`:''}`:`Gewünscht: ${edition.wished_volumes.length>4?plural(edition.wished_volumes.length,'Band','Bände'):`Band ${escapeHtml(edition.wished_volumes.join(', '))}`}`})});
  $('[data-route-catalog]',content)?.addEventListener('click',()=>routeTo('catalog'));
}

// ---- Preorders ----------------------------------------------------------------------------------

const PREORDER_TABS=[['open','Offen'],['delivered','Angekommen'],['cancelled','Storniert'],['all','Alle']];

function preorderGroups(rows){
  const month=thisMonth(),groups=new Map();
  for(const row of rows){
    const open=['ordered','paid','shipped'].includes(row.status);
    let key,label;
    if(!open){key=`z-${row.status}`;label=statusLabel(row.status)}
    else if(!row.expected_release){key='y-none';label='Ohne Termin'}
    else if(row.expected_release.slice(0,7)<month){key='0-overdue';label='Überfällig'}
    else{key=`1-${row.expected_release.slice(0,7)}`;label=row.expected_release.slice(0,7)===month?`Diesen Monat · ${partialDate(row.expected_release.slice(0,7))}`:partialDate(row.expected_release.slice(0,7))}
    if(!groups.has(key))groups.set(key,{label,rows:[]});
    groups.get(key).rows.push(row);
  }
  return [...groups.entries()].sort(([a],[b])=>a.localeCompare(b)).map(([,group])=>group);
}

function preorderRow(row){
  const open=['ordered','paid','shipped'].includes(row.status);
  const amounts=[row.total!=null?money(row.total):'Preis offen',row.paid?`bezahlt ${money(row.paid)}`:'',row.outstanding?`<b class="fig-outstanding">offen ${money(row.outstanding)}</b>`:''].filter(Boolean).join(' · ');
  return `<div class="fig-preorder" data-preorder="${row.id}">
    <img class="fig-preorder-art" loading="lazy" src="${volumeThumb(row)}" alt="" data-open-volume="${row.volume_id}">
    <div class="fig-preorder-main">
      <b data-open-volume="${row.volume_id}">${escapeHtml(row.edition_name)} · ${escapeHtml(volumeLabel(row))}${row.variant?` <small>${escapeHtml(row.variant)}</small>`:''}</b>
      <small>${escapeHtml([row.shop,row.order_number&&`#${row.order_number}`,row.quantity>1&&`${row.quantity} Stück`,row.ordered_at&&`bestellt ${partialDate(row.ordered_at)}`].filter(Boolean).join(' · '))}</small>
      <small>${amounts}${row.delays?` · <span class="fig-delay">${row.delays}× verschoben</span>`:''}${row.tracking?` · Sendung ${escapeHtml(row.tracking)}`:''}${row.delivered_at?` · angekommen ${partialDate(row.delivered_at)}`:''}</small>
    </div>
    <div class="fig-preorder-side">
      <select class="select-control status-select status-${row.status}" data-status="${row.id}" aria-label="Status">${Object.entries(state.boot.statuses).map(([key,label])=>`<option value="${key}" ${row.status===key?'selected':''}>${escapeHtml(label)}</option>`).join('')}</select>
      ${open?`<span class="fig-expected">${escapeHtml(partialDate(row.expected_release)||'kein Termin')}</span>`:''}
      <button type="button" class="icon-button" data-edit-preorder="${row.id}" title="Bearbeiten" aria-label="Vorbestellung bearbeiten">✎</button>
    </div>
  </div>`;
}

async function renderPreorders(){
  const stale=renderGuard();
  if(!$('#preorder-list'))content.innerHTML=loader('Vorbestellungen werden geladen …');
  let data;
  try{data=await api(`/api/preorders?status=${state.preorderStatus}`)}catch(error){if(!stale())content.innerHTML=failed('Vorbestellungen nicht erreichbar',error);return}
  if(stale())return;
  const stats=data.stats;
  content.innerHTML=`${pageHead({eyebrow:'VORBESTELLUNGEN',title:'Vorbestellungen',text:'Was bestellt ist, was noch zu zahlen ist und wann es kommen soll.',
      actions:`<a class="secondary-button" href="${appUrl('/api/export/preorders.csv')}">CSV</a><button type="button" class="primary-button" id="preorder-new">＋ Vorbestellen</button>`})}
    ${statPill([
      {label:'Offen',value:stats.open},{label:'Noch zu zahlen',value:money(stats.outstanding),className:stats.outstanding?'missing':''},
      {label:'Diesen Monat',value:stats.due_this_month},{label:'Überfällig',value:stats.overdue,className:stats.overdue?'missing':''},
    ],{className:'fig-summary',columns:4,mobileColumns:2})}
    <div class="segmented fig-modes fig-preorder-tabs" data-scroll-x>${PREORDER_TABS.map(([key,label])=>`<button type="button" data-preorder-tab="${key}" class="${state.preorderStatus===key?'active':''}">${label}${key==='delivered'&&stats.delivered?` <small>${stats.delivered}</small>`:''}${key==='cancelled'&&stats.cancelled?` <small>${stats.cancelled}</small>`:''}</button>`).join('')}</div>
    <div id="preorder-list">${data.preorders.length?preorderGroups(data.preorders).map(group=>`<section class="fig-preorder-group"><h2>${escapeHtml(group.label)} <small>${group.rows.length}</small></h2>${group.rows.map(preorderRow).join('')}</section>`).join('')
      :`<div class="empty-state"><b>${state.preorderStatus==='open'?'Keine offenen Vorbestellungen':'Nichts in dieser Ansicht'}</b><span>Vorbestellen kannst du jeden Band aus seinem Dialog, aus den Neuerscheinungen oder über „＋ Vorbestellen“.</span></div>`}</div>`;
  $$('[data-preorder-tab]',content).forEach(button=>button.onclick=()=>{state.preorderStatus=button.dataset.preorderTab;renderPreorders()});
  $('#preorder-new').onclick=()=>pickVolume('Welchen Band möchtest du vorbestellen?',volume=>openPreorderDialog(volume));
  $$('[data-open-volume]',content).forEach(element=>element.onclick=()=>openVolume(Number(element.dataset.openVolume),'preorders'));
  $$('[data-edit-preorder]',content).forEach(button=>button.onclick=()=>{
    const row=data.preorders.find(item=>item.id===Number(button.dataset.editPreorder));
    openPreorderDialog({id:row.volume_id,edition_name:row.edition_name,number_label:row.number_label,title:row.volume_title,release_date:row.volume_release},row);
  });
  $$('[data-status]',content).forEach(select=>select.onchange=async()=>{
    try{
      await patch(`/api/preorders/${select.dataset.status}`,{status:select.value});
      toast(select.value==='delivered'?'Angekommen – in die Sammlung gebucht':`Status: ${statusLabel(select.value)}`);
      refreshCounts();renderPreorders();
    }catch(error){toast(error.message)}
  });
}

// A small search to pick a volume for something (a new preorder): the quick search's volumes, or
// an edition's next volume.
function pickVolume(title,onPick){
  const modal=openDialog({id:'pick-volume',eyebrow:'BAND WÄHLEN',title,body:`<input class="dl-control" id="pick-query" placeholder="Reihe und Band, z. B. „Frieren 12“, oder ISBN" autocomplete="off" aria-label="Band suchen"><div id="pick-results" class="fig-pick-results"><p class="muted">Tippe mindestens zwei Zeichen.</p></div>`});
  let timer,sequence=0;
  $('#pick-query',modal).oninput=event=>{clearTimeout(timer);timer=setTimeout(async()=>{
    const q=event.target.value.trim(),mine=++sequence,results=$('#pick-results',modal);
    if(q.length<2){results.innerHTML='<p class="muted">Tippe mindestens zwei Zeichen.</p>';return}
    const found=await api(`/api/search?q=${encodeURIComponent(q)}&limit=20`).catch(()=>({editions:[],volumes:[]}));
    if(mine!==sequence)return;
    results.innerHTML=[
      ...found.volumes.map(row=>`<button type="button" class="search-result" data-pick="${row.id}"><img class="search-thumb fig-search-thumb" src="${volumeThumb(row)}" alt=""><div><b>${escapeHtml(row.edition_name)} · ${escapeHtml(volumeLabel(row))}</b><small>${escapeHtml([row.variant,partialDate(row.release_date)].filter(Boolean).join(' · '))}</small></div></button>`),
      ...found.editions.map(row=>`<button type="button" class="search-result" data-pick-edition="${row.id}"><img class="search-thumb fig-search-thumb" src="${coverThumb(row.cover,row.series_id)}" alt=""><div><b>${escapeHtml(row.name)}</b><small>${row.next_release?`Nächster: Band ${escapeHtml(row.next_release.number_label)} · ${escapeHtml(partialDate(row.next_release.release_date))}`:'Ausgabe öffnen'}</small></div></button>`),
    ].join('')||'<p class="muted">Nichts gefunden.</p>';
    $$('[data-pick]',results).forEach(button=>button.onclick=()=>{const row=found.volumes.find(item=>item.id===Number(button.dataset.pick));closeDialog();onPick(row)});
    $$('[data-pick-edition]',results).forEach(button=>button.onclick=async()=>{
      const row=found.editions.find(item=>item.id===Number(button.dataset.pickEdition));closeDialog();
      if(row.next_release)onPick(await api(`/api/volumes/${row.next_release.id}`));else openEdition(row.id);
    });
  },220)};
}
