// The logic in static/js that needs no browser: formatting, escaping, tiles, filters, groups, the
// number ranges, the bookmarklet and the EAN-13 decoder of the scanner.
import assert from 'node:assert/strict';
import { describe, test } from 'node:test';
import vm from 'node:vm';
import { loadScripts } from './scripts.mjs';

const SCRIPTS = ['js/core.js', 'js/scanner.js', 'js/mangas-ui.js', 'js/views.js', 'js/dashboard.js'];
const { run } = loadScripts(SCRIPTS);
const set = (expression, value) => run(`${expression}=${JSON.stringify(value)}`);

set('state.boot', {
  user: { id: 7, display_name: 'Alex Morgan' }, settings: {},
  conditions: { new: 'Neu/OVP', very_good: 'Sehr gut', reading_marks: 'Mit Lesespuren', damaged: 'Beschädigt' },
  statuses: { ordered: 'Bestellt', paid: 'Bezahlt', shipped: 'Versendet', delivered: 'Angekommen', cancelled: 'Storniert' },
  reading_statuses: { reading: 'Lese ich', planned: 'Geplant', paused: 'Pausiert', finished: 'Fertig', dropped: 'Abgebrochen' },
  languages: { de: 'Deutsch', ja: 'Japanisch', en: 'Englisch' }, demographics: { shounen: 'Shōnen' }, series_statuses: { completed: 'Abgeschlossen' },
  watchlists: [{ id: 3, name: 'Wunschliste', is_default: 1, count: 0 }, { id: 4, name: 'Geburtstag', is_default: 0, count: 2 }],
});

describe('text and money', () => {
  test('escapeHtml neutralises markup', () => {
    assert.equal(run(`escapeHtml('<img src=x onerror="a&b">')`), '&lt;img src=x onerror=&quot;a&amp;b&quot;&gt;');
    assert.equal(run(`escapeHtml(null)`), '');
    assert.equal(run(`escapeHtml(0)`), '0');
  });

  test('amounts in euros and yen', () => {
    assert.match(run(`money(7.5)`), /^7,50\s€$/);
    assert.match(run(`currencyMoney(429,'JPY')`), /^429\s¥$/);
    assert.equal(run(`moneyOrDash(null)`), '–');
    assert.match(run(`currencyMoney(5,'XYZ')`), /5/, 'an unknown currency still shows the amount');
  });

  test('dates as precise as they are known', () => {
    assert.equal(run(`partialDate('2026')`), '2026');
    assert.equal(run(`partialDate('2026-03')`), 'März 2026');
    assert.equal(run(`partialDate('2026-03-14')`), '14.03.2026');
    assert.equal(run(`partialDate('')`), '');
  });

  test('labels for codes, and volumes by number or title', () => {
    assert.equal(run(`languageLabel('ja')`), 'Japanisch');
    assert.equal(run(`languageLabel('fr')`), 'FR', 'an unknown language by its code');
    assert.equal(run(`readingLabel('reading')`), 'Lese ich');
    assert.equal(run(`volumeLabel({number_label:'10.5'})`), 'Band 10.5');
    assert.equal(run(`volumeLabel({number_label:'',title:'Official Guide'})`), 'Official Guide');
  });
});

describe('search boxes', () => {
  const matches = (query, fields) => run(`searchMatcher(${JSON.stringify(query)})(${JSON.stringify(fields)})`);

  test('every word somewhere, a letter off allowed', () => {
    const frieren = ['Frieren – Nach dem Ende der Reise', 'Kanehito Yamada, Tsukasa Abe', 'Egmont Manga'];
    assert.equal(matches('frieren egmont', frieren), true);
    assert.equal(matches('Friren', frieren), true);
    assert.equal(matches('frieren carlsen', frieren), false);
  });

  test('regular expressions where their syntax is used', () => {
    assert.equal(matches('Naruto|Boruto', ['Boruto: Two Blue Vortex']), true);
    assert.equal(matches('^Spy', ['Official Spy Guide']), false);
    assert.equal(matches('(Guide', ['Spy x Family (Guide)']), true, 'no valid expression: taken literally');
  });
});

describe('tiles', () => {
  const edition = { id: 4, series_id: 3, name: '<b>Spy</b>', publisher: 'Kazé', language: 'de', format: 'Taschenbuch', owned: 3, owned_numbers: 2, total: 10,
    read_numbers: 1, collecting: true, gap_count: 2, preordered: 1, edition_wished: true, cover: { kind: 'volumes', id: 12, version: 'abc' },
    next_release: { id: 15, number_label: '3', release_date: '2099-02' } };

  test('an edition tile escapes the name and shows what the account has of it', () => {
    const html = run(`editionTile(${JSON.stringify(edition)})`);
    assert.ok(html.includes('&lt;b&gt;Spy&lt;/b&gt;') && !html.includes('<b>Spy</b>'));
    assert.ok(html.includes('2/10') && html.includes('★') && html.includes('2 fehlen') && html.includes('VB'));
    assert.ok(html.includes('fig-heart active') && html.includes('data-quick-next="4"'));
    assert.ok(html.includes('/images/volumes/12/thumb?v=abc'));
    assert.match(html, /--share:20%[\s\S]*--share:10%/, 'owned and read as shares of the edition');
    assert.match(html, /Nächster: Bd\. 3 · Februar 2099/);
  });

  test('an edition without any cover shows its series\' picture (or the placeholder)', () => {
    assert.ok(run(`editionTile(${JSON.stringify({ ...edition, cover: null })})`).includes('/images/series/3/thumb'));
  });

  test('a volume tile says number, variant, read and what is not out yet', () => {
    const html = run(`volumeTile({id:6,edition_name:'Attack on Titan',number_label:'5',variant:'Limited Edition',release_date:'2099-01-01',owned:1,read:true,released:false,wished:false,image_version:''})`);
    assert.ok(html.includes('Band 5 · Limited Edition · 01.01.2099'));
    assert.ok(html.includes('×1') && html.includes('mg-mark-read') && html.includes('bald'));
    assert.ok(html.includes('/images/volumes/6/thumb"'));
  });

  test('filters go to the server without the empty ones', () => {
    assert.equal(run(`filterQuery({q:'',mode:'all',language:'ja',genre:'',sort:'title',direction:''})`), 'mode=all&language=ja&sort=title');
  });

  test('the default list and the picture formats', () => {
    assert.equal(run(`defaultListId()`), 3);
    assert.deepEqual(run(`PICTURE_TYPES`).split(','), ['image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/avif']);
  });
});

describe('volume numbers', () => {
  test('ranges as people type them', () => {
    assert.deepEqual(run(`parseNumbers('1-3, 7; 10.5 12–14')`), [1, 2, 3, 7, 10.5, 12, 13, 14]);
    assert.deepEqual(run(`parseNumbers('5-3')`), [3, 4, 5]);
    assert.equal(run(`parseNumbers('1-3, sieben')`), null);
    assert.equal(run(`parseNumbers('1-900')`), null, 'no endless runs');
  });

  test('and back as short as possible', () => {
    assert.equal(run(`compactNumbers([1,2,3,5,7,8,10.5])`), '1-3, 5, 7-8, 10.5');
    assert.equal(run(`compactNumbers([])`), '');
  });
});

describe('preorders', () => {
  test('are grouped: overdue first, then by month, without a date, then closed ones', () => {
    const month = new Date().toISOString().slice(0, 7);
    const next = new Date(new Date().setMonth(new Date().getMonth() + 2)).toISOString().slice(0, 7);
    const rows = [
      { id: 1, status: 'ordered', expected_release: next }, { id: 2, status: 'paid', expected_release: '2020-01' },
      { id: 3, status: 'shipped', expected_release: '' }, { id: 4, status: 'delivered', expected_release: '2024-01' },
      { id: 5, status: 'ordered', expected_release: `${month}-20` },
    ];
    const groups = run(`preorderGroups(${JSON.stringify(rows)})`).map(group => [group.label.split(' ·')[0], group.rows.map(row => row.id)]);
    assert.deepEqual(groups.map(([, ids]) => ids), [[2], [5], [1], [3], [4]]);
    assert.deepEqual([groups[0][0], groups[1][0], groups[3][0], groups[4][0]], ['Überfällig', 'Diesen Monat', 'Ohne Termin', 'Angekommen']);
  });
});

describe('groups', () => {
  test('a grid asks for groups only while it shows them, and for volumes on that level', () => {
    assert.equal(run(`gridQuery({q:'Frieren',series:''},{by:'series',sort:'count',open:null})`), 'q=Frieren&group=series&group_sort=count');
    assert.equal(run(`gridQuery({series:'Attack on Titan'},{by:'series',sort:'name',open:{by:'series',name:'Attack on Titan'}})`), 'series=Attack+on+Titan');
    assert.equal(run(`gridQuery({q:'x'},{by:'volumes',sort:'name',open:null})`), 'q=x&level=volumes');
    assert.equal(run(`gridQuery({q:'x'},{by:'',sort:'name',open:null})`), 'q=x');
  });

  test('the filter of the grouped field moves between groups or back to them', () => {
    const sync = (value, open) => run(`(()=>{const grouping={by:'publisher',sort:'name',open:${JSON.stringify(open)}};syncOpenGroup({publisher:${JSON.stringify(value)}},grouping);return grouping.open})()`);
    assert.deepEqual(sync('Kazé', { by: 'publisher', name: 'Carlsen' }), { by: 'publisher', name: 'Kazé' });
    assert.deepEqual(sync('__none__', { by: 'publisher', name: 'Carlsen' }), { by: 'publisher', name: '' });
    assert.equal(sync('', { by: 'publisher', name: 'Carlsen' }), null, '"Alle" goes back to the groups');
  });

  test('a group tile names the group (a language by its name), shows covers and escapes what users typed', () => {
    const tile = run(`groupTile('publisher',{name:'<b>Kazé</b>',count:3,owned:1,volumes:4,gaps:0,read:2,samples:[{id:1,series_id:2,cover:{kind:'volumes',id:9,version:'abc'}},{id:2,series_id:3,cover:null}]},editionGroupStats)`);
    assert.match(tile, /data-group="&lt;b&gt;Kazé&lt;\/b&gt;"/);
    assert.match(tile, /data-count="2"/);
    assert.match(tile, /\/images\/volumes\/9\/thumb\?v=abc[\s\S]*\/images\/series\/3\/thumb/);
    assert.match(tile, /3 Ausgaben · 4 Bände vorhanden[\s\S]*2 gelesen[\s\S]*--share:33%/);
    assert.match(run(`groupTile('language',{name:'ja',count:1,owned:0,samples:[]},editionGroupStats)`), /Japanisch/);
    const none = run(`groupTile('publisher',{name:'',count:2,owned:0,samples:[]},editionGroupStats)`);
    assert.match(none, /Ohne Verlag/);
    assert.match(none, /data-count="1"><span><\/span>/, 'an empty mosaic still has its picture area');
  });

  test('the kind a grid was shown in comes back, nothing unknown', () => {
    run(`restoreGroupings({catalog:'volumes',collection:'price',watch:'author'})`);
    assert.deepEqual(run(`[state.grouping.catalog.by,state.grouping.collection.by,state.grouping.watch.by]`), ['volumes', '', 'author']);
    run(`state.grouping.catalog.by='';state.grouping.watch.by=''`);
  });
});

// ---- EAN-13 -------------------------------------------------------------------------------------

const L = ['0001101', '0011001', '0010011', '0111101', '0100011', '0110001', '0101111', '0111011', '0110111', '0001011'];
const R = L.map(code => [...code].map(bit => (bit === '1' ? '0' : '1')).join(''));
const G = R.map(code => [...code].reverse().join(''));
const PARITY = ['LLLLLL', 'LLGLGG', 'LLGGLG', 'LLGGGL', 'LGLLGG', 'LGGLLG', 'LGGGLL', 'LGLGLG', 'LGLGGL', 'LGGLGL'];

// The bars of a code as modules ('1' dark), with quiet zones.
function eanModules(code) {
  const digits = [...code].map(Number);
  const left = digits.slice(1, 7).map((digit, index) => (PARITY[digits[0]][index] === 'L' ? L : G)[digit]).join('');
  const right = digits.slice(7).map(digit => R[digit]).join('');
  return `${'0'.repeat(11)}101${left}01010${right}101${'0'.repeat(11)}`;
}

// A picture of the code like a canvas gives it: modules `module` pixels wide (any fraction),
// a little noise, and optionally turned sideways.
function eanPicture(code, { module = 3, height = 40, noise = 18, sideways = false } = {}) {
  const bits = eanModules(code);
  const length = Math.ceil(bits.length * module);
  const width = sideways ? height : length, rows = sideways ? length : height;
  const data = new Uint8ClampedArray(width * rows * 4);
  let seed = 7;
  const random = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  for (let y = 0; y < rows; y++) for (let x = 0; x < width; x++) {
    const along = sideways ? y : x;
    const dark = bits[Math.min(bits.length - 1, Math.floor(along / module))] === '1';
    const value = Math.max(0, Math.min(255, (dark ? 30 : 225) + (random() - 0.5) * noise));
    const index = (y * width + x) * 4;
    data[index] = data[index + 1] = data[index + 2] = value;
    data[index + 3] = 255;
  }
  return { data, width, height: rows };
}

describe('the scanner reads EAN-13 barcodes', () => {
  const decode = (code, options) => run(`decodeEan13(${JSON.stringify({ ...eanPicture(code, options), data: [...eanPicture(code, options).data] })})`);

  test('an ISBN barcode as it is printed', () => {
    assert.equal(decode('9783551799050'), '9783551799050');
    assert.equal(decode('9784063842760', { module: 2.6 }), '9784063842760', 'at a width that is no whole number of pixels');
  });

  test('turned sideways or upside down', () => {
    assert.equal(decode('9783770430055', { sideways: true, height: 30 }), '9783770430055');
    const picture = eanPicture('9781974710010');
    const flipped = { ...picture, data: [] };
    for (let y = 0; y < picture.height; y++) for (let x = picture.width - 1; x >= 0; x--) flipped.data.push(...picture.data.slice((y * picture.width + x) * 4, (y * picture.width + x) * 4 + 4));
    assert.equal(run(`decodeEan13(${JSON.stringify(flipped)})`), '9781974710010');
  });

  test('nothing where there is no barcode, and only valid codes count', () => {
    assert.equal(run(`decodeEan13({data:new Array(40*20*4).fill(200),width:40,height:20})`), null);
    assert.equal(run(`ean13Valid('9783551799050')`), true);
    assert.equal(run(`ean13Valid('9783551799051')`), false);
    assert.equal(run(`isIsbnBarcode('4006381333931')`), false, 'an EAN that is no ISBN');
  });
});

describe('the bookmarklet', () => {
  const href = run(`bookmarkletHref()`);
  const code = decodeURIComponent(href.slice('javascript:'.length));

  test('is a javascript: link with valid code for this app', () => {
    assert.ok(href.startsWith('javascript:'));
    assert.doesNotThrow(() => new vm.Script(code));
    assert.ok(code.includes("'http://ophirmangas.test/#import='"));
  });

  test('reads a page and opens the app with what it found', () => {
    // A shop page as the bookmarklet sees it, reduced to what it asks the DOM for.
    const el = (props = {}) => ({ innerText: '', getAttribute: name => props.attrs?.[name] ?? null, querySelector: () => null, querySelectorAll: () => [], ...props });
    const dd = el({ tagName: 'DD', innerText: 'Carlsen' });
    const cells = [el({ innerText: 'ISBN' }), el({ innerText: '978-3-551-79905-0' })];
    const page = {
      title: 'Attack on Titan 5 | Buchhandlung',
      querySelector: selector => (selector === 'h1' ? el({ innerText: 'Attack on Titan 5' }) : selector === 'link[rel=canonical]' ? el({ href: 'https://shop.test/aot-5' }) : null),
      querySelectorAll: selector => ({
        'meta[property],meta[name],meta[itemprop]': [el({ attrs: { property: 'og:title' }, content: 'Attack on Titan 5' })],
        'script[type="application/ld+json"]': [el({ textContent: '{"@type":"Book","name":"Attack on Titan 5"}' }), el({ textContent: 'kaputt' })],
        '.data-field': [],
        dt: [el({ innerText: 'Verlag:', nextElementSibling: dd })],
        tr: [el({ querySelectorAll: () => cells })],
      })[selector] || [],
    };
    let opened;
    const context = vm.createContext({ document: page, location: { href: 'https://shop.test/aot-5' }, window: { open: url => { opened = url; return {}; } }, JSON, encodeURIComponent });
    vm.runInContext(code, context);
    const snapshot = JSON.parse(decodeURIComponent(opened.split('#import=')[1]));
    assert.equal(snapshot.url, 'https://shop.test/aot-5');
    assert.equal(snapshot.meta['og:title'], 'Attack on Titan 5');
    assert.deepEqual(snapshot.jsonld, [{ '@type': 'Book', name: 'Attack on Titan 5' }], 'a broken JSON-LD block is skipped');
    assert.deepEqual(snapshot.fields, { Verlag: 'Carlsen', ISBN: '978-3-551-79905-0' });
  });
});

describe('under a path prefix', () => {
  const requested = [];
  const prefixed = loadScripts(['js/core.js', 'js/scanner.js', 'js/mangas-ui.js'], {
    fetch: async url => { requested.push(url); return { status: 200, ok: true, json: async () => ({}) }; },
  }, { root: '/mangas' });

  test('API calls, pictures and the bookmarklet carry the root the page names', async () => {
    await prefixed.run(`api('/api/dashboard')`);
    assert.deepEqual(requested, ['/mangas/api/dashboard']);
    assert.equal(prefixed.run(`volumeThumb({id:3})`), '/mangas/images/volumes/3/thumb');
    assert.equal(prefixed.run(`coverThumb(null,2)`), '/mangas/images/series/2/thumb');
    assert.equal(prefixed.run(`appUrl('https://shop.test/item')`), 'https://shop.test/item', 'other addresses stay as they are');
    assert.ok(decodeURIComponent(prefixed.run(`bookmarkletHref()`)).includes("'http://ophirmangas.test/mangas/#import='"));
  });

  test('at the root nothing is added', () => {
    assert.equal(run(`appUrl('/api/dashboard')`), '/api/dashboard');
  });
});

describe('accounts under the shared sign-in of the Ophir apps', () => {
  const answers = {
    '/api/admin/oauth': { source: 'database', enabled: true, provider_name: 'Authentik' },
    '/api/admin/users': [{ id: 7, username: 'kim', display_name: 'Kim', email: 'kim@example.org', role: 'admin', copies: 0, preorders: 0, oauth_linked: 0, password_set: 0, is_self: true }],
    '/api/admin/catalog': { series: [], editions: [], volumes: [], duplicates: { series: [], editions: [], volumes: [] }, unused: { series: [], editions: [] } },
  };
  const page = mode => {
    const { run } = loadScripts(['js/core.js', 'js/scanner.js', 'js/mangas-ui.js', 'js/settings.js', 'js/admin.js'], {
      fetch: async url => ({ status: 200, ok: true, json: async () => answers[url] }),
    });
    run(`state.boot=${JSON.stringify({
      user: { id: 7, username: 'kim', display_name: 'Kim', email: 'kim@example.org', role: 'admin', oauth_linked: false, password_set: false },
      settings: {}, oauth: { enabled: true, provider_name: 'Authentik' }, auth: { mode, base: mode === 'standalone' ? '' : '/auth' },
    })}`);
    return run;
  };

  test('a slave shows the account as the master\'s', () => {
    const run = page('slave');
    run('renderSettings()');
    const html = run('content.innerHTML');
    assert.match(html, /Gemeinsame Anmeldung/);
    for (const field of ['account-display-name', 'account-username', 'account-email']) assert.match(html, new RegExp(`id="${field}"[^>]*disabled`), field);
    assert.doesNotMatch(html, /account-password-open|account-save|oauth\/login/);
  });

  test('a slave\'s admin view has no account editing and no SSO settings', async () => {
    const run = page('slave');
    await run('renderAdmin()');
    const html = run('content.innerHTML');
    assert.match(html, /Die Konten kommen aus der Ophir-App/);
    assert.match(html, /Kim/);
    assert.doesNotMatch(html, /data-edit-user|data-delete-user|admin-create-user|oauth-admin-card/);
  });

  test('standalone keeps accounts editable', async () => {
    const run = page('standalone');
    run('renderSettings()');
    assert.match(run('content.innerHTML'), /account-password-open[\s\S]*Mit Authentik verbinden[\s\S]*account-save/);
    await run('renderAdmin()');
    assert.match(run('content.innerHTML'), /oauth-admin-card[\s\S]*data-edit-user="7"[\s\S]*admin-create-user/);
  });
});

describe('the API client on a dropped connection', () => {
  const calls = [];
  let failures = 0;
  const flaky = loadScripts(['js/core.js'], {
    setTimeout: (callback) => { callback(); return 0; },
    fetch: async (url, options) => {
      calls.push(`${options.method || 'GET'} ${url}`);
      if (failures > 0) { failures--; throw new TypeError('Failed to fetch'); }
      return { status: 200, ok: true, json: async () => ({ ok: 1 }) };
    },
  });

  test('a read is tried once more, a write is not', async () => {
    calls.length = 0; failures = 1;
    assert.deepEqual(await flaky.run(`api('/api/editions')`), { ok: 1 });
    assert.deepEqual(calls, ['GET /api/editions', 'GET /api/editions']);

    calls.length = 0; failures = 1;
    await assert.rejects(flaky.run(`post('/api/collection',{volume_id:1})`), /Keine Verbindung zum Server/);
    assert.deepEqual(calls, ['POST /api/collection'], 'a write may have reached the server');

    calls.length = 0; failures = 2;
    await assert.rejects(flaky.run(`api('/api/editions')`), /Keine Verbindung zum Server/);
    assert.equal(calls.length, 2, 'only once more');
  });
});

describe('gaps', () => {
  test('numbers the catalogue lacks are shown in runs, catalogued volumes one by one', () => {
    const gaps = [{ number_label: '2', volume: { id: 2 } }, { number_label: '6', volume: null }, { number_label: '7', volume: null },
      { number_label: '8', volume: null }, { number_label: '10', volume: null }, { number_label: '10.5', volume: null }];
    const rows = run(`gapRows(${JSON.stringify(gaps)})`).map(row => (row.gap ? `volume ${row.gap.number_label}` : `${row.from}-${row.to}`));
    assert.deepEqual(rows, ['volume 2', '6-8', '10-10', '10.5-10.5']);
  });
});
