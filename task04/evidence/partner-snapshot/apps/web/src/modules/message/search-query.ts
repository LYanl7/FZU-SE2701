export type SearchParams = {
  q: string;
  type: string;
  category: string;
  days: string;
  sort: string;
  page: number;
};

/**
 * 拼搜索页要发给 /posts 的查询串。
 *
 * status 固定为 active:已找回 / 已认领的信息在首页、寻物、招领里都隐藏,
 * 搜索页必须保持一致,否则用户会搜出一堆已经结束的信息。
 */
export function buildSearchQuery(params: SearchParams): string {
  const query = new URLSearchParams({
    q: params.q,
    sort: params.sort,
    page: String(params.page),
    status: 'active',
  });
  if (params.type) query.set('type', params.type);
  if (params.category) query.set('category', params.category);
  if (params.days) query.set('days', params.days);
  return query.toString();
}
