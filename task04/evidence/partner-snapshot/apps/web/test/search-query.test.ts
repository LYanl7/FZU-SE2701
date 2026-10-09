import assert from 'node:assert/strict';
import test from 'node:test';

import { buildSearchQuery } from '../src/modules/message/search-query.ts';

const base = { q: '', type: '', category: '', days: '', sort: 'newest', page: 1 };
const params = (overrides = {}) => new URLSearchParams(buildSearchQuery({ ...base, ...overrides }));

test('The search request always asks for active posts only', () => {
  assert.equal(params().get('status'), 'active');
});

test('Even with every filter set the status stays active', () => {
  const query = params({
    q: '雨伞',
    type: 'lost',
    category: 'umbrella',
    days: '7',
    sort: 'oldest',
    page: 2,
  });
  assert.equal(query.get('status'), 'active');
});

test('Empty filters are left out of the query string', () => {
  const query = params();
  assert.equal(query.has('type'), false);
  assert.equal(query.has('category'), false);
  assert.equal(query.has('days'), false);
});

test('Filled filters are carried through', () => {
  const query = params({ type: 'lost', category: 'umbrella', days: '7' });
  assert.equal(query.get('type'), 'lost');
  assert.equal(query.get('category'), 'umbrella');
  assert.equal(query.get('days'), '7');
});

test('Keywords with Chinese characters and spaces survive encoding', () => {
  assert.equal(params({ q: '蓝色 雨伞' }).get('q'), '蓝色 雨伞');
});

test('Sorting and paging are carried through', () => {
  const query = params({ sort: 'oldest', page: 3 });
  assert.equal(query.get('sort'), 'oldest');
  assert.equal(query.get('page'), '3');
});
