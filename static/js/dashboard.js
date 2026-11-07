// Dashboard: totals, what to read next, what comes out next, gaps, the latest additions.

const QUICK_NAV=[
  ['catalog','Katalog','catalog','<path d="M8 4h11v16H8z"/><path d="M5 7v13h11"/>'],
  ['collection','Sammlung','collection','<path d="M5 4h3v16H5zM10 4h3v16h-3z"/><path d="m15.5 5.2 2.9-.8 3.6 14.9-2.9.8z"/>'],
  ['reading','Lesen','reading','<path d="M12 6.5C9.6 4.8 6.4 4.2 3 4.5v14c3.4-.3 6.6.3 9 2 2.4-1.7 5.6-2.3 9-2v-14c-3.4-.3-6.6.3-9 2z"/><path d="M12 6.5v14"/>'],
  ['gaps','Lücken','gaps','<path d="M4 5h3v14H4zM9 5h3v14H9z"/><path d="M14 5h3v14h-3z" stroke-dasharray="2.2 2.2"/>'],
  ['calendar','Neuerscheinungen','upcoming','<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M8 3v4M16 3v4M4 10h16"/>'],
  ['watchlist','Wunschliste','wished','<path d="M12 20.5s-7.5-4.6-9.8-9A5.4 5.4 0 0 1 12 6a5.4 5.4 0 0 1 9.8 5.5c-2.3 4.4-9.8 9-9.8 9Z"/>'],
];

async function renderDashboard(){
  const stale=renderGuard();
  const user=state.boot.user,first=escapeHtml(user.display_name.split(' ')[0]);
  content.innerHTML=`<div class="dashboard-shell"><section class="dashboard-hero"><div class="hero-top"><div class="hero-copy"><h1>Willkommen zurück, ${first}.</h1><p>Dein Regal auf einen Blick.</p></div></div></section>${loader('Übersicht wird geladen …')}</div>`;
  let data;
  try{data=await api('/api/dashboard')}catch(error){if(!stale())content.innerHTML=failed('Übersicht nicht erreichbar',error);return}
  if(stale())return;
  const {collection,preorders,planning,reading,counts}=data;
  const numbers={...counts,gaps:planning.gaps,upcoming:planning.upcoming.length};
  const intro=collection.volumes
    ?`${plural(collection.volumes,'Band','Bände')} aus ${plural(collection.editions,'Ausgabe','Ausgaben')} in deiner Sammlung${collection.unread?`, ${collection.unread} davon noch ungelesen`:''}.`
    :'Deine Sammlung wartet auf den ersten Band – scanne einfach die ISBN.';
  content.innerHTML=`<div class="dashboard-shell">
    <section class="dashboard-hero">
      <div class="hero-top">
        <div class="hero-copy"><h1>Willkommen zurück, ${first}.</h1><p>${intro}</p></div>
        ${statPill([
          {label:'Sammlungswert',value:money(collection.value)},{label:'Ausgegeben',value:money(collection.spent)},
          {label:'Ungelesen im Regal',value:collection.unread,className:collection.unread?'missing':''},
        ],{className:'dashboard-summary',columns:3,mobileColumns:3})}
      </div>
      <nav class="dashboard-quick-nav mg-quick-nav" aria-label="Schnellzugriff">${QUICK_NAV.map(([route,label,count,icon])=>`<button type="button" data-dashboard-route="${route}"><svg viewBox="0 0 24 24">${icon}</svg><span>${label}</span><strong>${numbers[count]??0}</strong></button>`).join('')}</nav>
    </section>
    <div class="fig-dashboard-grid">
      <section class="settings-section fig-dashboard-card">
        <div class="fig-card-head"><h2>Weiterlesen</h2><button type="button" class="link-button" data-dashboard-route="reading">Alles zum Lesen</button></div>
        ${reading.length?`<div class="fig-upcoming">${reading.map(row=>`<button type="button" class="fig-upcoming-row" ${row.next?`data-open-volume="${row.next.id}"`:`data-open-edition="${row.edition.id}"`}>
          <img loading="lazy" src="${row.next?volumeThumb(row.next):coverThumb(row.edition.cover,row.series_id)}" alt=""><span><b>${escapeHtml(row.series_title)}</b><small>${row.next?`Als Nächstes: Band ${escapeHtml(row.next.number_label)}${row.next.owned?'':' · nicht im Regal'}`:'Auf dem neuesten Stand'}</small></span>
          <span class="fig-upcoming-when">${row.edition.read_numbers}/${row.edition.total||'?'}<small>gelesen</small></span></button>`).join('')}</div>`
          :'<p class="muted">Keine Reihe mit dem Status „Lese ich“. Markier einen Band als gelesen – dann steht die Reihe hier.</p>'}
      </section>
      <section class="settings-section fig-dashboard-card">
        <div class="fig-card-head"><h2>Demnächst</h2><button type="button" class="link-button" data-dashboard-route="calendar">Alle Neuerscheinungen</button></div>
        ${planning.upcoming.length?`<div class="fig-upcoming">${planning.upcoming.map(volume=>`<button type="button" class="fig-upcoming-row" data-open-volume="${volume.id}">
          <img loading="lazy" src="${volumeThumb(volume)}" alt=""><span><b>${escapeHtml(volume.edition_name)} · ${escapeHtml(volumeLabel(volume))}</b><small>${escapeHtml([volume.publisher,volume.preordered?'vorbestellt':volume.collecting?'sammle ich':'Wunschliste'].filter(Boolean).join(' · '))}</small></span>
          <span class="fig-upcoming-when">${escapeHtml(partialDate(volume.release_date))}</span></button>`).join('')}</div>`
          :`<p class="muted">${counts.collecting?'Für deine gesammelten Ausgaben ist nichts angekündigt.':'Tippe bei einer Ausgabe auf „Sammle ich“, dann siehst du hier ihre nächsten Bände.'}</p>`}
        ${preorders.stats.open?`<p class="muted mg-dashboard-note">${plural(preorders.stats.open,'Vorbestellung','Vorbestellungen')} offen${preorders.stats.outstanding?`, noch ${money(preorders.stats.outstanding)} zu zahlen`:''}. <button type="button" class="link-button" data-dashboard-route="preorders">Zu den Vorbestellungen</button></p>`:''}
      </section>
    </div>
    ${planning.gaps||planning.recent.length?`<div class="fig-dashboard-grid">
      <section class="settings-section fig-dashboard-card">
        <div class="fig-card-head"><h2>Lücken</h2><button type="button" class="link-button" data-dashboard-route="gaps">Alle Lücken</button></div>
        <p class="mg-dashboard-big"><b>${planning.gaps}</b><span>${planning.gaps===1?'Band fehlt':'Bände fehlen'} in ${plural(planning.gap_editions,'Ausgabe','Ausgaben')}, die du sammelst.</span></p>
      </section>
      <section class="settings-section fig-dashboard-card">
        <div class="fig-card-head"><h2>Gerade erschienen</h2></div>
        ${planning.recent.length?`<div class="fig-upcoming">${planning.recent.map(volume=>`<button type="button" class="fig-upcoming-row" data-open-volume="${volume.id}">
          <img loading="lazy" src="${volumeThumb(volume)}" alt=""><span><b>${escapeHtml(volume.edition_name)} · ${escapeHtml(volumeLabel(volume))}</b><small>noch nicht in deiner Sammlung</small></span>
          <span class="fig-upcoming-when">${escapeHtml(partialDate(volume.release_date))}</span></button>`).join('')}</div>`:'<p class="muted">Alles Neue hast du schon.</p>'}
      </section>
    </div>`:''}
    <section class="fig-dashboard-recent">
      <div class="fig-card-head"><h2>Zuletzt hinzugefügt</h2><button type="button" class="link-button" data-dashboard-route="collection">Zur Sammlung</button></div>
      <div id="dashboard-recent"></div>
    </section>
  </div>`;
  $$('[data-dashboard-route]',content).forEach(element=>element.onclick=()=>routeTo(element.dataset.dashboardRoute));
  $$('[data-open-volume]',content).forEach(element=>element.onclick=()=>openVolume(Number(element.dataset.openVolume)));
  $$('[data-open-edition]',content).forEach(element=>element.onclick=()=>openEdition(Number(element.dataset.openEdition)));
  renderGrid($('#dashboard-recent'),collection.recent,{tile:volume=>volumeTile(volume),
    empty:'<div class="empty-state"><b>Noch nichts hinzugefügt</b><span>Leg deinen ersten Band an – am schnellsten mit der ISBN von der Rückseite.</span><button type="button" class="primary-button" data-first-manga>＋ Manga</button></div>'});
  $('[data-first-manga]',content)?.addEventListener('click',()=>openNewManga());
}
