### 安装

添加以下配置到插件源配置文件`plugins/source.json`:
```yaml
  "douyin": {
    "repo": "https://github.com/spacex-3/dy-wcf.git",
    "desc": "抖音视频去水印"
  }
```

### 配置

添加以下配置到配置文件`config.json`:
```yaml
plugins:

  - name: douyin
    command: 
      - 复制打开抖音
      - v.douyin
      - douyin.com
    without_at:           # 无需@机器人也会解析，bool或dict
      wx_userid: true     # 私聊
      xxxx@chatroom: true # 群聊
      "*": true
    limit_size: 50  # 限制视频大小，单位MB
    keep_assets_days: 1
```