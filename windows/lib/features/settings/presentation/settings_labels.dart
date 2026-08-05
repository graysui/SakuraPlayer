String settingsTargetLabel(String value) => switch (value) {
  'cloud115' => '115',
  'javdb' => 'JavDB',
  'dmm' => 'DMM',
  'gfriends' => 'GFriends',
  'actor_mapping' => '女优映射',
  'ai' => 'AI 翻译',
  'api' => '接口服务',
  'scheduler' => '调度服务',
  'worker' => '任务服务',
  'postgres' => '数据库',
  'avdb' => 'MGDB',
  _ => value,
};

String settingsStatusLabel(String value) => switch (value) {
  'never' => '尚未同步',
  'running' => '进行中',
  'succeeded' => '已完成',
  'failed' => '失败',
  'healthy' => '正常',
  'degraded' => '部分异常',
  'available' => '可用',
  'unavailable' => '不可用',
  'credentials_invalid' => '凭据无效',
  'not_configured' => '未配置',
  'unknown' => '未知',
  _ => '未知',
};

String cloud115BindingStatusLabel(String value) => switch (value) {
  'unbound' => '未绑定',
  'active' => '已绑定',
  'expired' => '凭据已失效',
  'unavailable' => '暂时不可用',
  'detached' => '缓存目录已失联',
  _ => '未知',
};

String qrStatusLabel(String value) => switch (value) {
  'waiting' => '等待扫码',
  'scanned' => '已扫码，等待确认',
  'confirmed' => '已确认',
  'expired' => '二维码已失效',
  'canceled' => '扫码已取消',
  _ => '未知',
};

String settingsErrorLabel(String? value) => switch (value) {
  null => '无错误',
  'service_unavailable' => '服务暂时不可用',
  'cloud115_unavailable' => '115 服务暂时不可用',
  'cloud115_credentials_expired' => '115 凭据已失效',
  'cloud115_qr_session_not_found' => '二维码已失效',
  'javdb_credentials_invalid' => 'JavDB 账号或密码无效',
  'javdb_upstream_error' => 'JavDB 暂时无法访问',
  'dmm_upstream_error' => 'DMM 暂时无法访问',
  'gfriends_upstream_error' => 'GFriends 暂时无法访问',
  'actor_mapping_upstream_error' => '女优映射暂时无法访问',
  'provider_snapshot_invalid' => '元数据快照无效',
  'provider_snapshot_unavailable' => '元数据快照尚未同步',
  'translation_credentials_invalid' => 'AI API key 无效',
  'translation_upstream_error' => 'AI 服务暂时无法访问',
  'translation_not_configured' => 'AI 尚未配置',
  'translation_guardrail_failed' => 'AI 返回内容未通过安全校验',
  'mgdb_source_not_configured' => '请先配置 MGDB 数据源',
  'metadata_timeout' => '元数据刮削超时',
  'validation_failed' => '输入内容不符合要求',
  'state_conflict' => '数据已变化，请刷新后重试',
  _ => '未知错误',
};

String metadataStageLabel(String? value) => switch (value) {
  null => '无阶段',
  'javdb_core' => 'JavDB 核心资料',
  'images' => '图片',
  'dmm' => 'DMM 简介',
  'actor_map' => '女优映射',
  'gfriends' => '女优写真',
  'translation' => '中文翻译',
  _ => '未知阶段',
};
