import assert from 'node:assert/strict';
import {existsSync, readFileSync, readdirSync} from 'node:fs';
import {join, resolve} from 'node:path';

const folder = resolve(process.argv[2] ?? 'dist');
const base = new URL('https://example.org/AXON/');
const read = path => readFileSync(join(folder, path), 'utf8');

function localFile(resource, from = base) {
  const url = new URL(resource, from);
  assert.equal(url.origin, base.origin, resource);
  assert.ok(url.pathname.startsWith(base.pathname), resource);
  const relative = decodeURIComponent(url.pathname.slice(base.pathname.length)) || 'index.html';
  assert.ok(existsSync(join(folder, relative)), "Falta " + relative);
  return relative;
}

function verifyHtml(path, from = base) {
  const html = read(path);
  const refs = [...html.matchAll(/\b(?:href|src)="([^"]+)"/g)].map(match => match[1]);
  refs.filter(resource => !resource.startsWith('#')).forEach(resource => localFile(resource, from));
  return {html, refs};
}

const {html, refs} = verifyHtml('index.html');
assert.ok(html.includes('Content-Security-Policy'));
assert.ok(refs.includes('/AXON/manifest.webmanifest'));
assert.ok(refs.includes('/AXON/icon.svg'));
assert.ok(refs.some(url => /\/assets\/[^/]+\.js$/.test(url)));
for (const page of ['offline.html', 'kiosk.html']) verifyHtml(page, new URL(page, base));

const manifestUrl = new URL('manifest.webmanifest', base);
const manifest = JSON.parse(read('manifest.webmanifest'));
const start = new URL(manifest.start_url, manifestUrl);
assert.equal(start.href, base.href);
assert.equal(new URL(manifest.scope, manifestUrl).href, base.href);
const id = new URL(manifest.id || start.href, start.origin);
id.hash = '';
assert.equal(id.href, base.href);
assert.equal(manifest.display, 'standalone');
assert.ok(manifest.icons.some(icon => icon.purpose === 'maskable' && icon.sizes === '512x512'));
for (const icon of manifest.icons) {
  const png = readFileSync(join(folder, localFile(icon.src, manifestUrl)));
  assert.equal(png.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
  assert.equal(`${png.readUInt32BE(16)}x${png.readUInt32BE(20)}`, icon.sizes);
}

const worker = read('sw.js');
assert.ok(worker.includes('self.registration.scope'));
assert.ok(worker.includes("path.startsWith('api/')"));
assert.ok(worker.includes("credentials: 'omit'"));
const bundles = readdirSync(join(folder, 'assets')).filter(file => file.endsWith('.js'));
const scripts = bundles.map(file => read('assets/' + file)).join('\n');
assert.ok(scripts.includes('/api/public/connection'));
assert.ok(scripts.includes('?static=1'));
assert.ok(!scripts.includes('/auth/login'), 'El portal estático contiene el formulario privado');
for (const file of readdirSync(join(folder, 'assets')).filter(file => file.endsWith('.css'))) {
  const css = read('assets/' + file);
  for (const [, resource] of css.matchAll(/url\(["']?([^)"']+)["']?\)/g)) {
    if (!resource.startsWith('data:')) localFile(resource, new URL('assets/' + file, base));
  }
}
console.log('Pages: rutas, logotipo, manifiesto, iconos, página sin conexión y alcance del Service Worker comprobados.');
