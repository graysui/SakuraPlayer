/**
 * TASK-307 来源展示文案与标签/大小规则测试：
 * - 网站/状态/标签中文映射、标签固定顺序（subtitle/cracked/4k/censored）
 * - raw vs ready 大小命名（ready→视频文件大小，其他→资源大小；空值→未知）
 * - MiB 整数、字节二进制单位最多一位小数
 * - 选择只产生 source_id（rejected 不输出）由 MovieDetailStore 测试覆盖
 */

import { describe, it, expect } from '@ohos/hypium';
import { MovieSource } from '../../../main/ets/core/api/ApiModels';
import { SourceDisplay } from '../../../main/ets/features/movies/SourceSheet';

function source(availability: string, sizeMb: number | null, sizeBytes: number | null): MovieSource {
  return new MovieSource('s1', 'sehuatang', 1001, '标题', '2026-01-01',
    '中文字幕', ['subtitle'], sizeMb, sizeBytes, availability);
}

export default function sourceSheetTest() {
  describe('SourceDisplay', () => {
  it('maps_website_labels', 0, () => {
    expect(SourceDisplay.websiteLabel('sehuatang')).assertEqual('色花堂');
    expect(SourceDisplay.websiteLabel('x1080x')).assertEqual('X1080X');
    expect(SourceDisplay.websiteLabel('other')).assertEqual('other');
  });

  it('maps_all_six_availability_labels', 0, () => {
    expect(SourceDisplay.availabilityLabel('available')).assertEqual('可缓存');
    expect(SourceDisplay.availabilityLabel('queued')).assertEqual('排队中');
    expect(SourceDisplay.availabilityLabel('running')).assertEqual('处理中');
    expect(SourceDisplay.availabilityLabel('ready')).assertEqual('可播放');
    expect(SourceDisplay.availabilityLabel('failed')).assertEqual('上次失败');
    expect(SourceDisplay.availabilityLabel('rejected')).assertEqual('不可用');
  });

  it('orders_labels_fixed_and_maps_chinese', 0, () => {
    const ordered = SourceDisplay.orderedLabels(['4k', 'subtitle', 'censored', 'cracked']);
    expect(ordered.length).assertEqual(4);
    expect(ordered[0]).assertEqual('字幕');
    expect(ordered[1]).assertEqual('破解');
    expect(ordered[2]).assertEqual('4K');
    expect(ordered[3]).assertEqual('有码');
    // 只显示服务端标签，不推导
    const partial = SourceDisplay.orderedLabels(['subtitle']);
    expect(partial.length).assertEqual(1);
    expect(partial[0]).assertEqual('字幕');
  });

  it('ready_uses_video_file_size_label', 0, () => {
    expect(SourceDisplay.sizeLabel(source('ready', 2048, 3221225472))).assertEqual('视频文件大小 3 GiB');
    expect(SourceDisplay.sizeLabel(source('ready', 2048, null))).assertEqual('视频文件大小未知');
  });

  it('non_ready_uses_resource_size_label', 0, () => {
    expect(SourceDisplay.sizeLabel(source('available', 2048, 3221225472))).assertEqual('资源大小 2048 MiB');
    expect(SourceDisplay.sizeLabel(source('failed', null, 3221225472))).assertEqual('资源大小未知');
    // 不显示真实视频大小（回退禁止）
    expect(SourceDisplay.sizeLabel(source('queued', null, 3221225472))).assertEqual('资源大小未知');
  });

  it('formats_bytes_with_binary_units', 0, () => {
    expect(SourceDisplay.formatBytes(1073741824)).assertEqual('1 GiB');
    expect(SourceDisplay.formatBytes(1610612736)).assertEqual('1.5 GiB');
    expect(SourceDisplay.formatBytes(5242880)).assertEqual('5 MiB');
    expect(SourceDisplay.formatBytes(7340032)).assertEqual('7 MiB');
    expect(SourceDisplay.formatBytes(500)).assertEqual('500 B');
  });

  it('size_label_uses_integer_mib', 0, () => {
    const rounded = SourceDisplay.sizeLabel(source('available', 2048.4, null));
    expect(rounded).assertEqual('资源大小 2048 MiB');
  });
});
}
