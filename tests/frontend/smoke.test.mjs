// Drives the real app in a headless Chrome: every view renders, and the things people do most
// (a volume from its ISBN, a new series from a link, an edition's volumes owned and read in one go,
// wishing, preordering until arrival, settings, admin) work end to end without a single error in
// the console.
//
//   node --test tests/frontend/
//
// Needs Chrome (CHROME_BIN overrides the lookup) and the Python requirements; set OPHIR_PYTHON
// when "python" is not the interpreter that has them.
import assert from 'node:assert/strict';
import { after, before, describe, test } from 'node:test';
import { chromePath, startBrowser, startServer } from './harness.mjs';

const AOT_DE = 1, AOT_JA = 2, FRIEREN_DE = 3;
const FRIEREN_5 = '9783770430055', BLUE_LOCK_1 = '9783551800015';
const skip = !chromePath() && !process.env.CI ? 'Chrome not found' : false;

describe('app in the browser', { skip }, () => {
  let server, page;

  before(async () => {
    server = await startServer();
    page = await startBrowser();
    await page.login(server.base, 'demo', 'mangas-1234');
  });
  after(async () => { await page?.close(); server?.stop(); });

  const noProblems = () => assert.deepEqual(page.problems.splice(0), []);
  const text = selector => page.evaluate(`document.querySelector(${JSON.stringify(selector)})?.innerText`);
  const click = selector => page.evaluate(`(document.querySelector(${JSON.stringify(selector)}).click(),1)`);
  const fill = (selector, value) => page.evaluate(`(()=>{const field=document.querySelector(${JSON.stringify(selector)});field.value=${JSON.stringify(value)};field.dispatchEvent(new Event('input'));field.dispatchEvent(new Event('change'));return 1})()`);
  const choose = (selector, value) => page.evaluate(`(()=>{const field=document.querySelector(${JSON.stringify(selector)});field.value=${JSON.stringify(value)};field.dispatchEvent(new Event('change'));return 1})()`);
  // The account's counts as the server has them now: the page's own copy (state.boot.counts) is
  // refreshed in the background, and a refresh whose connection dropped leaves it behind.
  const counts = condition => `api('/api/bootstrap').then(({counts})=>${condition})`;
  const closeAll = () => page.evaluate(`(()=>{while(document.querySelector('.dl-modal-overlay'))closeDialog();document.querySelectorAll('.overlay:not(.hidden)').forEach(overlay=>closeOverlay(overlay.id));return 1})()`);
  // Something that saves: done says when it has. A write whose connection dropped (see
  // harness.mjs login) shows "Keine Verbindung zum Server" and changes nothing -- the app does not
  // repeat writes on its own -- so it is done once more.
  async function save(action, done, message) {
    await action();
    try {
      await page.waitFor(done, { message });
    } catch (error) {
      if (!await page.evaluate(`[...document.querySelectorAll('.toast')].some(toast=>/Keine Verbindung/.test(toast.innerText))`)) throw error;
      await action();
      await page.waitFor(done, { message });
    }
  }

  test('starts on the dashboard of the signed-in user', async () => {
    assert.equal(await text('#user-name'), 'Alex Morgan');
    assert.equal(await page.evaluate(`state.route`), 'dashboard');
    assert.equal(await page.evaluate(`document.querySelectorAll('.mg-quick-nav button').length`), 6);
    noProblems();
  });

  test('every view renders', async () => {
    for (const route of ['catalog', 'collection', 'reading', 'gaps', 'calendar', 'watchlist', 'preorders', 'settings', 'dashboard']) {
      await page.route(route);
      assert.equal(await page.evaluate(`document.body.dataset.route`), route);
      assert.ok(await page.evaluate(`document.querySelector('#content').innerText.trim().length>20`), `${route} is empty`);
      assert.deepEqual(page.problems.splice(0), [], route);
    }
  });

  test('the catalogue filters editions and opens one with its volumes in order', async () => {
    await page.route('catalog');
    assert.equal(await page.evaluate(`document.querySelectorAll('.mg-edition-tile').length`), 5);
    await choose('[data-filter="language"]', 'ja');
    await page.waitFor(`document.querySelectorAll('.mg-edition-tile').length===1`, { message: 'the language filter' });
    await page.evaluate(`(state.catalogFilters=defaultCatalogFilters(),1)`);
    await page.route('catalog');
    await click(`.mg-edition-tile[data-edition="${AOT_DE}"]`);
    await page.waitFor(`!document.querySelector('#edition-modal').classList.contains('hidden')&&document.querySelectorAll('#edition-dialog .mg-slot').length===34`, { message: 'the 34 numbers of a completed edition' });
    assert.equal(await page.evaluate(`document.querySelectorAll('#edition-dialog .mg-slot-variant').length`), 1, 'the Limited Edition beside volume 5');
    assert.equal(await page.evaluate(`document.querySelectorAll('#edition-dialog [data-slot-create]').length`), 29, 'numbers the catalogue lacks');
    await click('#edition-dialog .mg-slot-cover[data-volume="5"]');
    await page.waitFor(`!document.querySelector('#volume-modal').classList.contains('hidden')&&document.querySelector('#volume-dialog h2')?.innerText.startsWith('Band 5')`, { message: 'the volume dialog' });
    for (const tab of ['preorders', 'value', 'lists', 'info', 'copies']) {
      await click(`[data-volume-tab="${tab}"]`);
      await page.waitFor(`document.querySelector('[data-volume-tab="${tab}"]').classList.contains('active')`);
    }
    await click('[data-volume-goto]:not([disabled])');
    await page.waitFor(`state.modalVolume&&state.modalVolume.id!==5`, { message: 'the neighbouring volume' });
    await closeAll();
    noProblems();
  });

  test('the catalogue groups by series, switches to single volumes and remembers it', async () => {
    await page.route('catalog');
    await click('[data-group-by="series"]');
    await page.waitFor(`document.querySelectorAll('.fig-group-tile').length===3`, { message: 'the series groups' });
    assert.match(await text('.fig-count'), /3 Reihen · 5 Ausgaben/);
    await click('.fig-group-tile[data-group="Attack on Titan"]');
    await page.waitFor(`document.querySelectorAll('.mg-edition-tile').length===2&&document.querySelector('.fig-group-head h2')?.innerText==='Attack on Titan'`, { message: 'the open group' });
    await click('[data-group-back]');
    await page.waitFor(`document.querySelectorAll('.fig-group-tile').length===3`, { message: 'back to the groups' });
    await click('[data-group-by="language"]');
    await page.waitFor(`[...document.querySelectorAll('.fig-group-tile b')].some(name=>name.innerText==='Japanisch')`, { message: 'the languages by name' });
    await click('[data-group-by="volumes"]');
    await page.waitFor(`document.querySelectorAll('.mg-volume-tile').length===15`, { message: 'every volume' });
    await page.waitFor(`state.boot.settings.groupings?.catalog==='volumes'`, { message: 'the kind to be remembered' });
    await click('[data-group-by=""]');
    await page.waitFor(`document.querySelectorAll('.mg-edition-tile').length===5`, { message: 'the editions again' });
    noProblems();
  });

  test('an ISBN brings a new volume of an edition the catalogue has into the collection', async () => {
    await page.evaluate(`(openNewManga(),1)`);
    await page.waitFor(`document.querySelector('#new-isbn')`);
    await fill('#new-isbn', FRIEREN_5);
    await click('#new-isbn-go');
    await page.waitFor(`document.querySelector('#volume-form [data-field="number"]')?.value==='5'`, { message: 'the volume form filled from the lookup' });
    assert.match(await text('#volume-form .dl-modal-head'), /Ausgabe: Frieren/);
    assert.equal(await page.evaluate(`document.querySelector('#volume-form [data-field="isbn"]').value`), FRIEREN_5);
    assert.equal(await page.evaluate(`document.querySelector('#volume-after').value`), 'copy');
    assert.match(await page.evaluate(`document.querySelector('#volume-image-file').accept`), /image\/avif/);
    await save(() => click('#volume-form [data-save]'), `state.modalEdition?.id===${FRIEREN_DE}&&${counts('counts.volumes===1')}`, 'the volume in the collection and its edition open');
    assert.equal(await page.evaluate(`state.modalEdition.owned`), 1);
    await closeAll();
    noProblems();
  });

  test('a link to a shop page creates the series, its edition and the volume', async () => {
    await page.evaluate(`(openNewManga(),1)`);
    await fill('#new-url', 'https://shop.test/blue-lock-2');
    await click('#new-url-go');
    await page.waitFor(`document.querySelector('#series-form [data-field="title"]')?.value==='Blue Lock'`, { message: 'the series form with the title from the page' });
    await click('#anilist-search');
    await page.waitFor(`document.querySelector('[data-anilist]')`, { message: 'the AniList results' });
    await click('[data-anilist]');
    await page.waitFor(`document.querySelector('#series-form [data-field="original_title"]').value==='ブルーロック'`, { message: 'AniList filling the series' });
    assert.equal(await page.evaluate(`document.querySelector('#series-form [data-field="demographic"]').value`), 'shounen');
    await save(() => click('#series-form [data-save]'), `document.querySelector('#edition-form [data-field="publisher"]')`, 'the edition form next');
    assert.equal(await page.evaluate(`document.querySelector('#edition-form [data-field="publisher"]').value`), 'Carlsen');
    await save(() => click('#edition-form [data-save]'), `document.querySelector('#volume-form [data-field="number"]')`, 'the volume form next');
    assert.equal(await page.evaluate(`document.querySelector('#volume-form [data-field="number"]').value`), '2');
    await save(() => click('#volume-form [data-save]'), `state.modalEdition?.name==='Blue Lock'`, 'the new edition open');
    assert.equal(await page.evaluate(`state.modalEdition.volumes.length`), 1);
    await closeAll();
    noProblems();
  });

  test('the ISBN of another volume finds the edition just created, and a catalogued one opens its volume', async () => {
    await page.evaluate(`(openNewManga({isbn:'${BLUE_LOCK_1}'}),1)`);
    await page.waitFor(`document.querySelector('#volume-form [data-field="number"]')?.value==='1'`, { message: 'volume 1 straight into the Carlsen edition' });
    assert.match(await text('#volume-form .dl-modal-head'), /Ausgabe: Blue Lock/);
    await save(() => click('#volume-form [data-save]'), `state.modalEdition?.volumes.length===2`, 'volume 1 created');
    await closeAll();
    await page.evaluate(`(openNewManga({isbn:'${BLUE_LOCK_1}'}),1)`);
    await page.waitFor(`state.modalVolume?.isbn==='${BLUE_LOCK_1}'`, { message: 'the volume already in the catalogue' });
    await closeAll();
    noProblems();
  });

  test('an edition is collected, owned and read in one go, and gaps and reading follow', async () => {
    await page.evaluate(`(openEdition(${AOT_DE}),1)`);
    await page.waitFor(`state.modalEdition?.id===${AOT_DE}`);
    await save(() => click('[data-edition-action="collect"]'), `state.modalEdition?.collecting===true`, 'the edition collected');
    await click('[data-edition-action="own"]');
    await page.waitFor(`document.querySelector('#own-range [data-field="numbers"]')`);
    await fill('#own-range [data-field="numbers"]', '1-3, 7');
    await save(() => click('#own-range-save'), `state.modalEdition?.owned===4`, 'four volumes owned, 7 created on the way');
    await click('[data-edition-action="read"]');
    await fill('#read-through [data-field="through"]', '2');
    await save(() => click('#read-through-save'), `state.modalEdition?.read===2`, 'read through 2');
    assert.equal(await page.evaluate(`state.modalEdition.reading_status`), 'reading');
    await closeAll();
    await page.route('reading');
    assert.match(await text('#reading-list'), /Attack on Titan[\s\S]*Als Nächstes: Band 3/);
    await save(() => click('[data-read-next]'), `/Als Nächstes: Band 4/.test(document.querySelector('#reading-list')?.innerText)`, 'the next volume after reading 3');
    await page.route('gaps');
    assert.match(await text('#gap-list'), /Attack on Titan[\s\S]*Band 4[\s\S]*Band 5/);
    noProblems();
  });

  test('wishing, preordering and the arrival booked into the collection', async () => {
    await page.route('catalog');
    await save(() => click(`.mg-edition-tile[data-edition="${AOT_JA}"] [data-wish-edition]:not(.active)`), counts('counts.wished===1'), 'the wish to count');
    await page.evaluate(`(openVolume(11),1)`);
    await page.waitFor(`state.modalVolume?.id===11`);
    await click('[data-volume-action="wish"]');
    await page.waitFor(`document.querySelector('#wish-dialog')`);
    await save(() => click('#wish-save'), `state.modalVolume?.wished===true`, 'the volume wished');
    await click('[data-volume-action="preorder"]');
    await page.waitFor(`document.querySelector('#preorder-dialog')`);
    assert.equal(await page.evaluate(`document.querySelector('#preorder-dialog [data-field="price"]').value`), '7', 'the list price');
    await fill('#preorder-dialog [data-field="shop"]', 'Thalia');
    await save(() => click('#preorder-save'), `!document.querySelector('#preorder-dialog')&&state.modalVolume?.preorders?.length===1`, 'the preorder to be saved');
    assert.equal(await page.evaluate(`state.modalVolume.wished`), false, 'ordering took it off the wishlist');
    await closeAll();
    await page.route('preorders');
    const owned = await page.evaluate(counts('counts.volumes'));
    await save(() => choose('[data-status]', 'delivered'), counts(`counts.preorders===0&&counts.volumes===${owned + 1}`), 'the arrival to be booked');
    noProblems();
  });

  test('the scanner falls back to typing the ISBN', async () => {
    await click('[data-scan]');
    await page.waitFor(`document.querySelector('#scanner-dialog #scanner-typed')`, { message: 'the scanner dialog' });
    await fill('#scanner-typed', FRIEREN_5);
    await click('#scanner-use');
    await page.waitFor(`state.modalVolume?.isbn==='${FRIEREN_5}'`, { message: 'the scanned volume to open' });
    await closeAll();
    // Headless Chrome has no camera: whatever the dialog said about it is no console error.
    noProblems();
  });

  test('settings save the appearance and the public profile', async () => {
    await page.route('settings');
    await click('[data-mobile-appearance="light"]');
    await page.waitFor(`document.body.classList.contains('mobile-light')`);
    await page.waitFor(`document.querySelector('#public-slug')`);
    await fill('#public-slug', 'alex');
    await page.evaluate(`(document.querySelector('#public-enabled').checked=true,document.querySelector('#public-reading').checked=true,1)`);
    await save(() => click('#public-save'), `document.querySelector('#public-profile-body a[href$="/u/alex"]')`, 'the public link');
    await click('[data-mobile-appearance="dark"]');
    noProblems();
  });
});

describe('admin in the browser', { skip }, () => {
  let server, page;
  before(async () => { server = await startServer(); page = await startBrowser(); await page.login(server.base, 'admin', 'admin'); });
  after(async () => { await page?.close(); server?.stop(); });

  test('the admin view lists accounts and the catalogue', async () => {
    await page.route('admin');
    await page.waitFor(`document.querySelector('#admin-catalog-body')?.innerText.includes('Ausgaben im Katalog')`);
    assert.ok((await page.evaluate(`document.querySelector('#content').innerText`)).includes('demo'));
    assert.deepEqual(page.problems.splice(0), []);
  });
});

// The homelab serves the app under /mangas (Traefik strips it and names it in X-Forwarded-Prefix):
// every address the page asks for has to carry it, or the request lands outside the app.
describe('the app under a path prefix', { skip }, () => {
  let server, page;
  before(async () => {
    server = await startServer({ prefix: '/mangas' });
    page = await startBrowser();
    await page.login(server.base, 'demo', 'mangas-1234');
  });
  after(async () => { await page?.close(); server?.stop(); });

  test('views, dialogs, the lookup, the bookmarklet and a public profile stay under the prefix', async () => {
    for (const route of ['catalog', 'collection', 'reading', 'gaps', 'calendar', 'watchlist', 'preorders', 'settings', 'dashboard']) await page.route(route);
    await page.route('catalog');
    assert.equal(await page.evaluate(`document.querySelectorAll('.mg-edition-tile').length`), 5);
    await page.evaluate(`(document.querySelector('.mg-edition-tile[data-edition="${AOT_DE}"]').click(),1)`);
    await page.waitFor(`!document.querySelector('#edition-modal').classList.contains('hidden')&&document.querySelector('#edition-dialog .mg-slot')`, { message: 'the edition dialog' });
    await page.evaluate(`(document.querySelector('#edition-dialog .mg-slot-cover').click(),1)`);
    await page.waitFor(`!document.querySelector('#volume-modal').classList.contains('hidden')`, { message: 'the volume dialog' });
    await page.evaluate(`(closeOverlay('volume-modal'),closeOverlay('edition-modal'),1)`);
    await page.evaluate(`(openNewManga({isbn:'${FRIEREN_5}'}),1)`);
    await page.waitFor(`document.querySelector('#volume-form [data-field="number"]')?.value==='5'`, { message: 'the lookup under the prefix' });
    await page.evaluate(`(closeDialog(),1)`);
    assert.ok(decodeURIComponent(await page.evaluate(`bookmarkletHref()`)).includes(`${server.base}/#import=`), 'the bookmarklet opens the app under the prefix');

    await page.evaluate(`api('/api/collection',{method:'POST',body:JSON.stringify({volume_id:1})})`);
    await page.evaluate(`api('/api/account/public-profile',{method:'PUT',body:JSON.stringify({enabled:true,slug:'alex'})})`);
    await page.goto(`${server.base}/u/alex`);
    await page.waitFor(`document.querySelector('.public-head')&&document.querySelector('.mg-edition-tile')`, { message: 'the public profile to load' });
    await page.evaluate(`(document.querySelector('.mg-edition-tile').click(),1)`);
    await page.waitFor(`document.querySelector('#public-edition .mg-slot')`, { message: 'an edition on the public profile' });

    const origin = new URL(server.base).origin;
    assert.deepEqual(page.requests.filter(url => url.startsWith(origin) && !url.startsWith(`${server.base}/`)), []);
    assert.deepEqual(page.problems.splice(0), []);
  });
});
