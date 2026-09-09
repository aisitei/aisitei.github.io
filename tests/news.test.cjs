const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.existsSync('assets/news.js') ? fs.readFileSync('assets/news.js', 'utf8') : '';
const sandbox = {module: {exports: {}}, URLSearchParams};
vm.runInNewContext(source, sandbox);
const reader = sandbox.module.exports;
test('combined search, category and month can find an article beyond the first page', () => {
  assert.equal(typeof reader.filterArticles, 'function');
  const items = Array.from({length: 70}, (_, i) => ({title_ko: `기사 ${i}`, title_en: `Camera ${i}`, category: i === 60 ? 'camera' : 'phone', month:'2026-09'}));
  const result = reader.filterArticles(items, {lang:'en', query:'CAMERA 60', category:'camera', month:'2026-09'});
  assert.equal(result.length, 1);
  assert.equal(result[0].title_en, 'Camera 60');
});
test('pagination clamps invalid pages and returns disjoint windows', () => {
  assert.equal(typeof reader.paginate, 'function');
  const items = Array.from({length: 61}, (_, i) => i);
  assert.equal(reader.paginate(items, 2).items[0], 24);
  assert.equal(reader.paginate(items, 99).page, 3);
  assert.equal(reader.paginate(items, -2).page, 1);
  assert.equal(reader.paginate([], NaN).pages, 1);
});
test('URL state preserves filters and normalizes invalid language', () => {
  assert.equal(typeof reader.readState, 'function');
  const state = reader.readState('?cat=camera&month=2026-09&search=Sony&page=3&lang=bad', 'ko');
  assert.equal(state.page, 3);
  assert.equal(state.lang, 'ko');
  assert.equal(state.query, 'Sony');
});
test('unfiltered pagination retains real static URLs when the index cannot load', () => {
  assert.equal(typeof reader.pageLink, 'function');
  assert.equal(reader.pageLink({lang:'en',query:'',category:'',month:''},2,'news'), 'news/page-2.html?lang=en');
  assert.equal(reader.pageLink({lang:'ko',query:'',category:'',month:''},2,'reports'), 'report-pages/page-2.html?lang=ko');
  assert.ok(reader.pageLink({lang:'ko',query:'Sony',category:'camera',month:''},2,'news').startsWith('index.html?'));
});
