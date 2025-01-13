import os
import time
import asyncio
import requests
import time
import re

from datetime import datetime
from plugins import register, Plugin, Event, logger, Reply, ReplyType

'''
plugins:

  - name: douyin
    command: [复制打开抖音, v.douyin, douyin.com]
    limit_size: 50  # 限制视频大小，单位MB
    without_at:     # 无需@机器人也会解析，bool或dict
      wx_userid: true,     # 私聊
      xxxx@chatroom: true, # 群聊
      *: false
    keep_assets_days: 1

'''

@register
class App(Plugin):
    name = 'douyin'
    latest_clear = 0

    def __init__(self, config: dict):
        super().__init__(config)


    def help(self, **kwargs):
        return '抖音视频数据及去水印。'

    @property
    def commands(self):
        cmds = self.config.get('command', 'douyin.com')
        if not isinstance(cmds, list):
            cmds = [cmds]
        return cmds

    def config_for(self, event: Event, key, default=None):
        val = self.config.get(key, {})
        if isinstance(val, dict):
            msg = event.message
            dfl = val.get('*', default)
            val = val.get(msg.room_id or msg.sender_id, dfl)
        return val

    def did_receive_message(self, event: Event):
        # 初始化动态配置
        self.limit_size = self.config_for(event, 'limit_size', 50)
        api_base_url = self.config_for(event, 'api_base_url', '')
        self.api_base_url = f"{api_base_url.rstrip('/')}/api/hybrid/video_data"

        if self.config_for(event, 'without_at'):
            self.reply(event)

        self.clear_assets()

    def will_generate_reply(self, event: Event):
        if not self.config_for(event, 'without_at'):
            self.reply(event)

    def will_decorate_reply(self, event: Event):
        pass

    def will_send_reply(self, event: Event):
        pass

    def reply(self, event: Event):
        query = event.message.content
        for cmd in self.commands:
            if cmd in query:
                event.reply = self.generate_reply(event)
                event.bypass()
                return

    def generate_reply(self, event: Event) -> Reply:
        query = event.message.content
        text = query
        result = asyncio.run(self.hybrid_parsing(query)) or {}
        vdata = result
        if vdata:
            # 提取无水印视频链接和视频大小
            # 处理 bit_rate 列表，确保它存在且有元素
            bit_rate_list = vdata.get('video', {}).get('bit_rate', [])
            
            if bit_rate_list and isinstance(bit_rate_list, list):
                # 从列表中获取第一个元素
                play_addr = bit_rate_list[0].get('play_addr', {}).get('url_list', [])
            else:
                play_addr = []

            video_link = play_addr[0] if play_addr else None

            # 获取视频大小，使用 bit_rate 的第一个元素
            video_size = bit_rate_list[0].get('play_addr', {}).get('data_size', 0) if bit_rate_list else 0
            video_size_mb = round(video_size / (1024 * 1024))  # 保留0位小数，四舍五入

            nickname = vdata.get('author', {}).get('nickname', '未知用户')
            desc = vdata.get('desc', '无描述')
            create_time = datetime.fromtimestamp(vdata.get('create_time', 0)).strftime('%Y-%m-%d')

            statistics = vdata.get('statistics', {})
            digg_count = statistics.get('digg_count', 0)
            comment_count = statistics.get('comment_count', 0)
            collect_count = statistics.get('collect_count', 0)
            share_count = statistics.get('share_count', 0)
            
            size_tip = f'\n视频尺寸({video_size_mb}MB)过大，无法发送视频' if video_size_mb >= self.limit_size else ''

            # 下载链接处理
            url_pattern = r'https?://(?:www\.)?douyin\.com/[^\s]+|https?://v\.douyin\.com/[^\s]+'
            short_match = re.search(url_pattern, text)
            douyin_short_url = short_match.group(0)
            download_link = f"{self.config_for(event, 'api_base_url').rstrip('/')}/api/download?url={douyin_short_url}&prefix=true&with_watermark=false"
            logger.debug(f"[douyin] 下载视频，video_url={download_link}")

            if video_link:
                #清理过期文件
                self.clear_assets()

                # 转换视频链接为短链接
                short_video_link = self.shorten_link(video_link)
                if short_video_link:
                    # 拼接完整的短链接
                    short_video_link = f"https://d.zpika.com{short_video_link}"
                else:
                    short_video_link = video_link  # 如果短链接失败，仍然使用长链接

                # 发送视频信息和观看链接
                if size_tip:
                    reply = Reply(ReplyType.TEXT, f'{size_tip}')
                else:
                    reply = Reply(ReplyType.VIDEO, download_link)
                return Reply(ReplyType.TEXT, f"抖音视频信息：\n用户: {nickname}, 发布时间: {create_time}, 视频大小: {video_size_mb}MB\n点赞: {digg_count}, 评论: {comment_count}, 收藏: {collect_count}, 分享: {share_count}\n描述: {desc}\n无压缩无水印视频链接：{short_video_link}")

    async def hybrid_parsing(self, url):
        result = {}
        for n in range(1):
            try:
                return await self.get_douyin_video_data(url) or {}
            except Exception as exc:
                logger.error('Scraper Exception: %s', exc)
                result = {'message': f'{exc}'}
                await asyncio.sleep(0.1)
        return result

    def clear_assets(self):
        now = time.time()
        if now - self.latest_clear < 300:
            return
        days = self.config.get('keep_assets_days', 0)
        if not days:
            return
        try:
            current_dir = os.path.dirname(os.path.realpath(__file__))
            assets_dir = os.path.dirname(f'{current_dir}/../../assets/.')
            files = os.listdir(assets_dir)
            for file in files:
                path = os.path.join(assets_dir, file)
                if '.gitkeep' in path:
                    continue
                tim = os.path.getmtime(path)
                if now - tim > days * 86400:
                    os.remove(path)
                    logger.info('Clear assets file: %s', path)
            self.latest_clear = now
        except Exception as exc:
            logger.warning('Clear assets failed: %s', exc)

    def get_douyin_video_data(self, url, event: Event, retries=3, wait_time=5):
        """
        调用抖音API，获取无水印视频数据，包含重试机制
        retries: 最大重试次数
        wait_time: 每次重试的等待时间（秒）
        """

 
        for attempt in range(retries):
            try:
                response = requests.get(self.api_base_url, params={"url": url})
                if response.status_code == 200:
                    return response.json().get('data', {})
                else:
                    logger.debug(f"API 请求失败，状态码：{response.status_code}")
            except Exception as e:
                logger.debug(f"API 请求出错: {e}")
            
            # 如果请求失败，等待指定的时间后重试
            logger.debug(f"请求失败，等待 {wait_time} 秒后重试...（第 {attempt + 1} 次重试）")
            time.sleep(wait_time)
        
        # 所有重试都失败，返回 None
        logger.debug("所有重试都失败，无法获取抖音视频数据")
        return None


    def shorten_link(self, long_url):
        """
        调用短链接API将长链接转为短链接
        """
        shorten_api_url = "https://d.zpika.com/api"  # 你的短链接API URL
        payload = {"url": long_url}

        try:
            # 发送请求到短链接API
            response = requests.post(shorten_api_url, json=payload)
            if response.status_code == 200:
                result = response.json()
                # 检查 status 是否为 200，获取短链接路径
                if result.get("status") == 200:
                    return result.get("key")  # 返回短链接路径部分
                else:
                    logger.error(f"Failed to shorten the URL, status code: {result.get('status')}")
                    return None
            else:
                logger.error(f"Failed to shorten the URL: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error while shortening URL: {str(e)}")
            return None
