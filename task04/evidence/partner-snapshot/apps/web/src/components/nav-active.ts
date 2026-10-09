/**
 * 判断底部导航的某个标签在当前路径下是否应该高亮。
 *
 * 这里刻意按「路径段」比较,而不是用 path.startsWith(href):
 * "/messages".startsWith("/me") 是 true,会让「我的」和「消息」同时亮起来。
 */
export function isActiveTab(path: string, href: string): boolean {
  // 首页只有精确匹配才亮,否则前缀比较会让它在所有页面上都亮
  if (href === '/') return path === '/';

  // 「我的」还包含「我的发布」这个独立路由
  if (href === '/me') {
    return path === '/me' || path.startsWith('/me/') || path === '/my-posts';
  }

  return path === href || path.startsWith(href + '/');
}
