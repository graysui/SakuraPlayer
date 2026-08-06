/**
 * TASK-307 认证目录图片 URL 校验与缓存清理测试。
 * - 只接受 /api/v1/catalog/images/{uuid}（严格 UUID）；绝对 URL/穿越/非图片路径拒绝
 * - 缓存 clear 释放条目（退出登录清理路径由 AuthStore.logout 调用）
 */

import { describe, it, expect } from '@ohos/hypium';
import { CatalogImageUrl } from '../../../main/ets/core/images/CatalogImageCache';

export default function catalogImageTest() {
  describe('CatalogImageUrl', () => {
  it('accepts_catalog_image_path', 0, () => {
    const id = CatalogImageUrl.imageIdOf('/api/v1/catalog/images/123e4567-e89b-12d3-a456-426614174000');
    expect(id).assertEqual('123e4567-e89b-12d3-a456-426614174000');
  });

  it('rejects_absolute_urls', 0, () => {
    expect(CatalogImageUrl.imageIdOf('https://example.com/api/v1/catalog/images/123e4567-e89b-12d3-a456-426614174000')).assertNull();
    expect(CatalogImageUrl.imageIdOf('http://example.com/api/v1/catalog/images/123e4567-e89b-12d3-a456-426614174000')).assertNull();
  });

  it('rejects_traversal_and_non_catalog_paths', 0, () => {
    expect(CatalogImageUrl.imageIdOf('/api/v1/catalog/images/../../etc/passwd')).assertNull();
    expect(CatalogImageUrl.imageIdOf('/api/v1/catalog/images/a%2fb')).assertNull();
    expect(CatalogImageUrl.imageIdOf('/api/v1/actors/123e4567-e89b-12d3-a456-426614174000')).assertNull();
    expect(CatalogImageUrl.imageIdOf('/api/v1/catalog/images/123e4567-e89b-12d3-a456-426614174000/extra')).assertNull();
    expect(CatalogImageUrl.imageIdOf('/api/v1/catalog/images/123e4567-e89b-12d3-a456-426614174000?x=1')).assertNull();
  });

  it('rejects_malformed_uuids', 0, () => {
    // 非 8-4-4-4-12 分组
    expect(CatalogImageUrl.imageIdOf('/api/v1/catalog/images/123e4567e89b12d3a456426614174000')).assertNull();
    expect(CatalogImageUrl.imageIdOf('/api/v1/catalog/images/123e4567-e89b-12d3-a456-42661417400Z')).assertNull();
    expect(CatalogImageUrl.imageIdOf('/api/v1/catalog/images/not-a-uuid')).assertNull();
  });
});
}
