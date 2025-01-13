配置：

  "plugins": [
    {
      "name": "douyin",
      "command": ["复制打开抖音", "v.douyin", "douyin.com", "tiktok.com", "kuaishou.com"],
      "limit_size": 50,      # 限制视频大小，单位MB
      "without_at": {        # 无需@机器人也会解析，bool或dict
        "wx_userid": true,     # 私聊
        "xxxx@chatroom": true, # 群聊
        "*": false
      },
      "keep_assets_days": 3              # 清理N天前的视频缓存
    }
  ]
