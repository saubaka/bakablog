# 阶段七数据模型

| 模型 | 用途 | 关键约束 |
| --- | --- | --- |
| `FriendCategory` / `FriendLink` | 友链分类、申请与健康状态 | URL唯一；申请编号唯一；状态检查约束 |
| `Album` / `Photo` | 相册与本地媒体关联 | slug唯一；照片按相册与顺序索引 |
| `Comment` | 文章评论和一层回复 | 只关联文章；访客/站长作者类型；公开状态索引 |
| `CommentReaction` / `CommentReport` | 点赞和举报 | 评论与访客哈希组合唯一，防止重复 |
| `GuestbookMessage` | 留言与站长回复 | 审核、置顶、时间复合索引 |
| `ModerationNotification` | 新互动和举报通知 | 已读状态与时间索引 |

访客标识使用站点密钥对IP和截断User-Agent计算HMAC-SHA256，数据库不保存原始IP。迁移文件为`c420a0b39922_stage_7_interactions_and_galleries.py`，升级和回滚都不会修改Stage 5的FTS5虚拟表。
