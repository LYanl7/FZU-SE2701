import assert from 'node:assert/strict';
import test from 'node:test';

import { isActiveTab } from '../src/components/nav-active.ts';

const TABS = ['/', '/nearby', '/publish', '/messages', '/me'];

// 返回当前页面上会亮起来的所有标签。用数组而不是单个布尔值,
// 因为「两个标签同时亮」才是这个 bug 的真面目。
const activeTabs = (path: string) => TABS.filter((href) => isActiveTab(path, href));

test('The home tab is active only on the root page', () => {
  assert.deepEqual(activeTabs('/'), ['/']);
});

test('The messages list activates the messages tab and nothing else', () => {
  assert.deepEqual(activeTabs('/messages'), ['/messages']);
});

test('A conversation page keeps the messages tab active', () => {
  assert.deepEqual(activeTabs('/messages/42'), ['/messages']);
});

test('The profile tab is active on its own page', () => {
  assert.deepEqual(activeTabs('/me'), ['/me']);
});

test('A profile sub page keeps the profile tab active', () => {
  assert.deepEqual(activeTabs('/me/settings'), ['/me']);
});

test('The my-posts page still counts as the profile tab', () => {
  assert.deepEqual(activeTabs('/my-posts'), ['/me']);
});

test('The publish tab is active on the publish page', () => {
  assert.deepEqual(activeTabs('/publish'), ['/publish']);
});

test('The nearby tab is active on the nearby page', () => {
  assert.deepEqual(activeTabs('/nearby'), ['/nearby']);
});

test('The messages list never activates the profile tab', () => {
  // 回归用例: "/messages".startsWith("/me") 正是当初那个 bug 的来源
  assert.equal(isActiveTab('/messages', '/me'), false);
});

test('The profile page never activates the messages tab', () => {
  assert.equal(isActiveTab('/me', '/messages'), false);
});

test('A longer path that merely starts with a tab name is not a match', () => {
  assert.equal(isActiveTab('/messages-old', '/messages'), false);
});

test('Every tab page activates exactly one tab', () => {
  for (const href of TABS) {
    assert.deepEqual(activeTabs(href), [href], `page ${href} should light up only ${href}`);
  }
});
