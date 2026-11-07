// Layout in both appearances, on a phone and on a wide screen: every view and the states people
// open by clicking (filter panel, dialogs, volume tabs, forms, the scanner) fit the screen without
// sideways scrolling, every text stands out from its background, and the console stays clean.
//
//   node --test tests/frontend/layout.test.mjs
//
// With OPHIR_SCREENSHOTS=<directory> every state is also saved there as a PNG, named
// <width>-<appearance>-<state>.png, for looking at the result.
import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { after, before, describe, test } from 'node:test';
import { chromePath, startBrowser, startServer } from './harness.mjs';

const AOT_DE = 1, FRIEREN_DE = 3, FRIEREN_5 = '9783770430055';
const skip = !chromePath() && !process.env.CI ? 'Chrome not found' : false;
const SCREENSHOTS = process.env.OPHIR_SCREENSHOTS || '';
if (SCREENSHOTS) mkdirSync(SCREENSHOTS, { recursive: true });

const SCREENS = [
  { name: 'phone', width: 390, height: 844, mobile: true },
  { name: 'desktop', width: 1440, height: 960, mobile: false },
];

// One app and one browser for both screens: the suite already starts more of them than the other
// browser tests, and fewer at once keep the machine calm.
describe('layout', { skip }, () => {
  let server, page;

  before(async () => {
    server = await startServer();
    page = await startBrowser(SCREENS[0]);
    await page.login(server.base, 'demo', 'mangas-1234');
    // Something in every list, so the views show their content and not only empty states.
    await page.evaluate(`(async()=>{
      await post('/api/collection',{volume_ids:[1,2,6,8,9],purchase_price:'7,50',location:'Regal 1'});
      await post('/api/editions/${AOT_DE}/read',{through:1});
      await api('/api/editions/${AOT_DE}/collecting',{method:'PUT',body:'{}'});
      await api('/api/editions/${FRIEREN_DE}/collecting',{method:'PUT',body:'{}'});
      await api('/api/series/3/reading',{method:'PUT',body:JSON.stringify({status:'planned'})});
      await post('/api/watchlists/'+defaultListId()+'/volumes',{volume_id:12,target_price:'5'});
      await post('/api/watchlists/'+defaultListId()+'/editions',{edition_id:5});
      await post('/api/preorders',{volume_id:11,price:'7',shop:'Thalia'});
      return 1})()`);
  });
  after(async () => { await page?.close(); server?.stop(); });

  for (const screen of SCREENS) describe(`on a ${screen.name}`, () => {
    // A fresh start in this size, as the demo account (the screen before ends as admin).
    before(async () => {
      await page.screen(screen);
      await page.login(server.base, 'demo', 'mangas-1234');
    });

    // The page may be as wide as the screen and no wider; so may every open dialog.
    async function fits(label) {
      const overflow = await page.evaluate(`(()=>{
        const width=document.documentElement.clientWidth;
        const wide=[...document.querySelectorAll('body *')].filter(element=>{
          const box=element.getBoundingClientRect();
          if(!box.width||getComputedStyle(element).position==='fixed'&&element.closest('.toast-stack'))return false;
          return box.right>width+1&&!element.closest('[data-scroll-x], .fig-filter-row, .segmented')&&getComputedStyle(element).visibility!=='hidden';
        }).slice(0,4).map(element=>(element.id?'#'+element.id:element.className||element.tagName)+' '+Math.round(element.getBoundingClientRect().right));
        return {scroll:document.documentElement.scrollWidth-width,wide};
      })()`);
      assert.ok(overflow.scroll <= 0, `${label}: the page scrolls sideways by ${overflow.scroll}px`);
      assert.deepEqual(overflow.wide, [], `${label}: elements reach past the right edge`);
    }

    // Every text on screen stands out from what it is drawn on: a contrast of at least 3:1 against
    // the nearest opaque background (a dark panel left in the light appearance shows up here).
    async function readable(label) {
      const poor = await page.evaluate(`(()=>{
        const canvas=document.createElement('canvas');canvas.width=canvas.height=1;
        const context=canvas.getContext('2d',{willReadFrequently:true});
        const rgba=color=>{context.clearRect(0,0,1,1);context.fillStyle='#000';context.fillStyle=color;context.fillRect(0,0,1,1);return [...context.getImageData(0,0,1,1).data]};
        const alpha=color=>{const match=/\\/\\s*([\\d.]+)\\s*\\)$|rgba\\([^)]*,\\s*([\\d.]+)\\)$/.exec(color);return match?Number(match[1]??match[2]):(color==='transparent'?0:1)};
        const luminance=([r,g,b])=>[r,g,b].map(v=>{v/=255;return v<=.03928?v/12.92:((v+.055)/1.055)**2.4}).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
        const background=element=>{for(let node=element;node;node=node.parentElement){const style=getComputedStyle(node);if(style.backgroundImage!=='none')return null;if(alpha(style.backgroundColor)>.6)return style.backgroundColor}return getComputedStyle(document.body).backgroundColor};
        const found=[];
        for(const element of document.querySelectorAll('h1,h2,h3,b,strong,p,label,small,span,dt,dd,button,a,td')){
          const text=[...element.childNodes].filter(node=>node.nodeType===3).map(node=>node.textContent).join('').trim();
          if(!text)continue;
          const box=element.getBoundingClientRect(),style=getComputedStyle(element);
          if(!box.width||!box.height||box.bottom<0||box.top>innerHeight||style.visibility==='hidden'||Number(style.opacity)<.5)continue;
          if(element.closest('[aria-hidden="true"],.hidden,.overlay.hidden,svg'))continue;
          const behind=document.elementFromPoint(Math.min(innerWidth-1,Math.max(0,box.left+Math.min(box.width/2,20))),Math.min(innerHeight-1,Math.max(0,box.top+box.height/2)));
          if(behind&&!element.contains(behind)&&!behind.contains(element))continue;   // covered by a dialog or the tab bar
          const ground=background(element);if(!ground)continue;
          const [light,dark]=[luminance(rgba(style.color)),luminance(rgba(ground))].sort((a,b)=>b-a);
          const ratio=(light+.05)/(dark+.05);
          if(ratio<3)found.push(text.slice(0,30)+' '+ratio.toFixed(2));
        }
        return found.slice(0,6);
      })()`);
      assert.deepEqual(poor, [], `${label}: text that hardly stands out`);
    }

    async function shot(appearance, label) {
      // Measured and pictured as it ends up, not halfway through a fade or a slide.
      await page.evaluate(`(document.getAnimations().forEach(animation=>{try{animation.finish()}catch{}}),1)`);
      await fits(`${appearance} ${label}`);
      await readable(`${appearance} ${label}`);
      assert.deepEqual(page.problems.splice(0), [], `${appearance} ${label}`);
      if (!SCREENSHOTS) return;
      await page.evaluate(`new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
      const { result } = await page.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
      writeFileSync(path.join(SCREENSHOTS, `${screen.width}-${appearance}-${label}.png`), Buffer.from(result.data, 'base64'));
    }

    const click = selector => page.evaluate(`(document.querySelector(${JSON.stringify(selector)}).click(),1)`);
    // A request from the page that can be repeated (it sets a state), so a dropped connection
    // (see harness.mjs login) is tried once more.
    const request = (method, url, body) => page.evaluate(`(()=>{const send=()=>fetch(${JSON.stringify(server.base + url)},{method:${JSON.stringify(method)},headers:{'Content-Type':'application/json'}${body ? `,body:${JSON.stringify(JSON.stringify(body))}` : ''}});return send().catch(()=>new Promise(resolve=>setTimeout(resolve,500)).then(send)).then(response=>response.status)})()`);
    const closeAll = () => page.evaluate(`(()=>{while(document.querySelector('.dl-modal-overlay'))closeDialog();document.querySelectorAll('.overlay:not(.hidden)').forEach(overlay=>closeOverlay(overlay.id));return 1})()`);

    for (const appearance of ['light', 'dark']) {
      test(`${appearance}: every view and what opens on it`, async () => {
        await page.evaluate(`(state.boot.settings.mobileThemeAppearance=${JSON.stringify(appearance)},applyAppearance(),1)`);
        assert.equal(await page.evaluate(`document.body.classList.contains('mobile-light')`), appearance === 'light');

        for (const route of ['dashboard', 'catalog', 'collection', 'reading', 'gaps', 'calendar', 'watchlist', 'preorders', 'settings']) {
          await page.route(route);
          await shot(appearance, route);
        }

        // The grids in groups (the overview and an open group) and as single volumes.
        for (const [route, view, by] of [['catalog', 'catalog', 'series'], ['collection', 'collection', 'publisher'], ['watchlist', 'watch', 'language']]) {
          await page.evaluate(`(Object.assign(state.grouping.${view},{by:'${by}',open:null}),1)`);
          await page.route(route);
          await page.waitFor(`document.querySelector('.fig-group-tile')`, { message: `the ${route} groups` });
          await shot(appearance, `${route}-groups-${by}`);
          await click('.fig-group-tile');
          await page.waitFor(`document.querySelector('.fig-group-head')&&document.querySelector('.fig-tile')`, { message: `an open ${route} group` });
          await shot(appearance, `${route}-group-open-${by}`);
          await click('[data-group-back]');
          await page.waitFor(`!document.querySelector('.fig-group-head')`);
          await page.evaluate(`(Object.assign(state.grouping.${view},{by:'',open:null}),1)`);
        }
        for (const [route, view] of [['catalog', 'catalog'], ['collection', 'collection']]) {
          await page.evaluate(`(Object.assign(state.grouping.${view},{by:'volumes',open:null}),1)`);
          await page.route(route);
          await page.waitFor(`document.querySelector('.mg-volume-tile')`, { message: `the ${route} volumes` });
          await shot(appearance, `${route}-volumes`);
          await page.evaluate(`(Object.assign(state.grouping.${view},{by:'',open:null}),1)`);
        }

        await page.route('catalog');
        if (screen.mobile) {
          await click('ophir-filter-panel [data-mobile-filter-toggle]');
          await page.waitFor(`document.querySelector('ophir-filter-panel')?.hasAttribute('open')`, { message: 'the filter panel to open' });
          await shot(appearance, 'catalog-filters');
        }

        // The edition dialog with its volumes, with the quick buttons of the slots showing.
        await page.evaluate(`(setEditMode(true),openEdition(${AOT_DE}),1)`);
        await page.waitFor(`state.modalEdition?.id===${AOT_DE}&&!document.querySelector('#edition-modal').classList.contains('hidden')`);
        await shot(appearance, 'edition');
        await page.evaluate(`(document.querySelector('#edition-dialog .mg-slots').scrollIntoView({block:'start'}),1)`);
        await shot(appearance, 'edition-slots');
        await page.evaluate(`(setEditMode(false),1)`);
        await click('[data-edition-action="own"]');
        await page.waitFor(`document.querySelector('#own-range')`);
        await shot(appearance, 'own-range');
        await closeAll();

        await page.evaluate(`(openVolume(6,'copies'),1)`);
        await page.waitFor(`state.modalVolume?.id===6&&!document.querySelector('#volume-modal').classList.contains('hidden')`);
        for (const tab of ['copies', 'preorders', 'value', 'lists', 'info']) {
          await click(`[data-volume-tab="${tab}"]`);
          await page.waitFor(`document.querySelector('[data-volume-tab="${tab}"]').classList.contains('active')`);
          await shot(appearance, `volume-${tab}`);
        }
        await click('[data-volume-action="copy"]');
        await page.waitFor(`document.querySelector('#entry-dialog')`);
        await shot(appearance, 'entry-dialog');
        await closeAll();

        await page.evaluate(`(openSeriesDialog(1),1)`);
        await page.waitFor(`document.querySelector('#series-dialog .mg-other-edition')`, { message: 'the series dialog' });
        await shot(appearance, 'series-dialog');
        await closeAll();

        // Adding a manga: the entry point, a lookup into the volume form, the series form with
        // AniList's answer, the edition form and the scanner.
        await page.evaluate(`(openNewManga(),1)`);
        await page.waitFor(`document.querySelector('#new-isbn')`);
        await shot(appearance, 'new-manga');
        await page.evaluate(`(document.querySelector('#new-isbn').value='${FRIEREN_5}',document.querySelector('#new-isbn-go').click(),1)`);
        await page.waitFor(`document.querySelector('#volume-form [data-field="number"]')?.value==='5'`, { message: 'the volume form after the lookup' });
        await shot(appearance, 'volume-form');
        await closeAll();
        await page.evaluate(`(openSeriesForm({title:'Blue Lock'}),1)`);
        await page.waitFor(`document.querySelector('#anilist-search')`);
        await click('#anilist-search');
        await page.waitFor(`document.querySelector('[data-anilist]')`, { message: 'the AniList results' });
        await shot(appearance, 'series-form');
        await closeAll();
        await page.evaluate(`api('/api/series/2').then(series=>openEditionForm({series_id:2},{series}))`);
        await page.waitFor(`document.querySelector('#edition-form [data-field="publisher"]')`);
        await shot(appearance, 'edition-form');
        await closeAll();
        await page.evaluate(`(openScanner(),1)`);
        await page.waitFor(`document.querySelector('#scanner-dialog')&&!/gestartet/.test(document.querySelector('#scanner-status').innerText)`, { message: 'the scanner to say what it can do' });
        await shot(appearance, 'scanner');
        await closeAll();

        await page.evaluate(`(document.querySelector('#global-search-open').click(),1)`);
        await page.evaluate(`(document.querySelector('#global-search-input').value='Frieren',doSearch('Frieren'))`);
        await page.waitFor(`document.querySelectorAll('#search-results .search-result').length>0`);
        await shot(appearance, 'search');
        await closeAll();

        await page.route('preorders');
        await click('[data-edit-preorder]');
        await page.waitFor(`document.querySelector('#preorder-dialog')`);
        await shot(appearance, 'preorder-dialog');
        await closeAll();

        await page.evaluate(`(document.querySelector('#importexport-open').click(),1)`);
        await shot(appearance, 'import-export');
        await closeAll();
      });
    }

    test('the public profile, the sign-in page and the admin view in both appearances', async () => {
      for (const appearance of ['light', 'dark']) {
        await request('PUT', '/api/account/public-profile', { enabled: true, slug: 'alex', show_wishlist: true, show_reading: true, theme: appearance });
        // Chrome on Windows now and then drops a connection to the test server (see harness.mjs
        // login): a page that did not get its data is loaded once more.
        for (let attempt = 1; ; attempt++) {
          await page.goto(`${server.base}/u/alex`);
          try {
            await page.waitFor(`document.querySelector('.public-head')&&document.querySelector('.mg-edition-tile')`, { message: 'the public profile', timeout: attempt === 1 ? 6000 : 15000 });
            break;
          } catch (error) {
            if (attempt === 2) throw new Error(`${error.message}\n  page: ${await page.evaluate(`document.querySelector('#content')?.innerText`)}`);
            page.problems.splice(0);
          }
        }
        await shot(appearance, 'public-profile');
        await page.evaluate(`(document.querySelector('.mg-edition-tile').click(),1)`);
        await page.waitFor(`document.querySelector('#public-edition .mg-slot')`, { message: 'an edition on the public profile' });
        await shot(appearance, 'public-edition');
        await page.evaluate(`(document.querySelector('#public-edition .close-button').click(),1)`);
      }
      // The sign-in page takes the appearance from the cookie the app keeps. Signed out from a
      // page without the app, which would otherwise go to the sign-in page itself mid-request.
      await page.goto(`${server.base}/health`);
      await request('POST', '/logout');
      for (const appearance of ['light', 'dark']) {
        await page.evaluate(`(document.cookie='ophir_mangas_theme=${appearance};path=/',1)`);
        await page.goto(`${server.base}/login`);
        await page.waitFor(`document.querySelector('[name=username]')`, { message: 'the sign-in page' });
        await shot(appearance, 'login');
      }
      await page.login(server.base, 'admin', 'admin');
      for (const appearance of ['light', 'dark']) {
        await page.evaluate(`(state.boot.settings.mobileThemeAppearance=${JSON.stringify(appearance)},applyAppearance(),1)`);
        await page.route('admin');
        await page.waitFor(`document.querySelector('#admin-catalog-body')?.innerText.includes('Ausgaben im Katalog')`, { message: 'the admin view' });
        await shot(appearance, 'admin');
      }
    });
  });
});
