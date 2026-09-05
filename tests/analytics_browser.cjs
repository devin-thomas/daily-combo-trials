// Real browser, fully intercepted network. Provider stubs model the documented queue API.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const fixtures = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const root = process.argv[3];
const origin = 'https://daily-combo-trials.vercel.app';
const providerStub = `
  window.testBeforeSend = null;
  const consume = (command, payload) => {
    if (command === 'beforeSend') window.testBeforeSend = payload;
    window.recordAnalytics({command, payload: command === 'beforeSend' ? null : payload});
  };
  (window.vaq || []).forEach(args => consume(...args));
  window.va = consume;
  window.recordAnalytics({command: 'automatic_pageview'});
`;

async function run(browser, blocked = false) {
  const fixture = fixtures;
  const context = await browser.newContext({ serviceWorkers: 'block' });
  const calls = [];
  const errors = [];
  const submissions = [];
  let alternate = false;
  await context.exposeBinding('recordAnalytics', (_source, call) => calls.push(call));
  context.on('page', page => {
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => {
      if (message.type() === 'error' && !message.text().startsWith('Failed to load resource: net::ERR_FAILED')) {
        errors.push(message.text());
      }
    });
  });
  await context.addInitScript(() => {
    // Window bubble listeners run after the product's document listeners and
    // capture each queue before the normal browser navigation replaces it.
    for (const type of ['submit', 'click']) {
      window.addEventListener(type, () => window.recordAnalytics({
        command: 'queue_check',
        payload: (window.vaq || []).filter(args => args[0] === 'event').length,
      }));
    }
  });
  await context.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin === origin && url.pathname === '/_vercel/insights/script.js') {
      return blocked ? route.abort() : route.fulfill({ contentType: 'application/javascript', body: providerStub });
    }
    if (url.hostname === 'static.cloudflareinsights.com') {
      return blocked ? route.abort() : route.fulfill({ contentType: 'application/javascript', body: 'window.cloudflareStubLoaded = true;' });
    }
    // Never pass any request through to the internet, including images and new tabs.
    if (url.origin !== origin) {
      return request.resourceType() === 'document'
        ? route.fulfill({ contentType: 'text/html', body: '<p>Offline source fixture</p>' })
        : route.abort();
    }
    if (request.method() === 'POST') {
      assert.ok(['/randomize', '/daily'].includes(url.pathname));
      submissions.push(url.pathname);
      alternate = url.pathname === '/randomize';
      // Serve the post-redirect document directly: browser redirect chains can
      // bypass Playwright routing. The Python tests verify the real 303 response.
      return route.fulfill({ contentType: 'text/html', body: fixture[alternate ? 'alternate' : 'daily'] });
    }
    if (url.pathname.startsWith('/static/')) {
      if (request.resourceType() === 'image') return route.abort();
      const filename = path.join(root, url.pathname);
      assert.ok(filename.startsWith(path.join(root, 'static') + path.sep));
      return route.fulfill({ path: filename });
    }
    const body = url.pathname === '/' ? fixture[alternate ? 'alternate' : 'daily'] : fixture.pages[url.pathname];
    if (!body) return route.abort();
    return route.fulfill({ contentType: 'text/html', body });
  });
  const page = await context.newPage();
  const load = async (pathname = '/') => {
    await page.goto(origin + pathname);
    if (!blocked) await page.waitForFunction(() => window.testBeforeSend);
  };
  const events = () => calls.filter(call => call.command === 'event').map(call => call.payload);
  await load();
  if (!blocked) {
    assert.equal(await page.evaluate(() => window.cloudflareStubLoaded), true);
    assert.deepEqual(await page.evaluate(() => {
      const filter = window.testBeforeSend;
      return [location.href, '/setup', '/setup/', '/setup/private', 'https://unexpected.example/']
        .map(url => filter({ type: 'pageview', url }) !== null);
    }), [true, false, false, false, false]);
  }
  await page.locator('[data-art-image]').first().waitFor({ state: 'hidden' });
  await page.locator('#challenge-art-fallback').waitFor({ state: 'visible' });
  for (const endpoint of ['/randomize', '/daily']) {
    const button = page.locator(`form[action="${origin}${endpoint}"] button`);
    await button.focus();
    await Promise.all([page.waitForNavigation(), page.keyboard.press('Enter')]);
    if (!blocked) await page.waitForFunction(() => window.testBeforeSend);
    assert.equal(submissions.at(-1), endpoint);
  }
  assert.deepEqual(submissions, ['/randomize', '/daily']);
  for (const selector of ['.site-nav', '.home-links']) {
    await load();
    await Promise.all([
      page.waitForURL(origin + '/history'),
      page.locator(`${selector} a[href="${origin}/history"]`).click(),
    ]);
    if (!blocked) await page.waitForFunction(() => window.testBeforeSend);
  }
  await load(fixture.characterPath);
  const source = page.getByRole('link', { name: /Description and artwork source/ }).first();
  const destination = await source.getAttribute('href');
  const popupPromise = page.waitForEvent('popup');
  await source.click();
  const popup = await popupPromise;
  assert.equal(popup.url(), destination);
  await popup.close();
  await load('/games');
  assert.equal(events().length, 0);
  assert.equal(calls.filter(call => call.command === 'pageview').length, 0);
  if (!blocked) {
    const pageviews = calls.filter(call => call.command === 'automatic_pageview').length;
    assert.ok(pageviews >= 7);
    assert.equal(pageviews, calls.filter(call => call.command === 'beforeSend').length);
  }
  {
    assert.ok(calls.filter(call => call.command === 'queue_check').length >= 5);
    assert.ok(calls.filter(call => call.command === 'queue_check').every(call => call.payload === 0));
    assert.equal(await page.evaluate(() => (window.vaq || []).filter(args => args[0] === 'event').length), 0);
  }
  assert.deepEqual(errors, []);
  await context.close();
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    await run(browser);
    await run(browser, true);
    console.log('Offline Chromium analytics interactions, exclusions, and blocked-provider behavior passed.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
