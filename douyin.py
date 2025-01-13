import os
import time
import requests
import re

from datetime import datetime
from plugins import register, Plugin, Event, logger, Reply, ReplyType


@register
class Douyin(Plugin):
    name = 'douyin'
    latest_clear = 0

    def __init__(self, config: dict):
        super().__init__(config)


    def help(self, **kwargs):
        return '抖音视频数据及去水印。'

    @property
    def commands(self):
        cmds = self.config.get('command', ['douyin.com', '复制打开抖音', 'v.douyin'])
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
                logger.info(f"Matched command: {cmd}")
                event.reply = self.generate_reply(event)
                logger.info(f"视频信息已发送，停止处理")
                event.bypass()
                return
        logger.info("No command matched")   

    def generate_reply(self, event: Event) -> Reply:
        query = event.message.content
        text = query
        text_reply = None
        video_reply = None
        
        try:
            result = self.hybrid_parsing(query) or {}

        except Exception as exc:
            logger.error(f"Error in hybrid_parsing: {exc}")
            text_reply = Reply(ReplyType.TEXT, "视频解析失败，请稍后再试。")
            event.channel.send(text_reply, event.message)

        if not result:
            text_reply = Reply(ReplyType.TEXT, "未找到视频数据，请检查链接是否有效。")
            event.channel.send(text_reply, event.message)
            return
        
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
            
            size_tip = f'视频大小({video_size_mb}MB)超过管理员限制({self.limit_size}MB)，无法发送视频。' if video_size_mb >= self.limit_size else ''

            # 下载链接处理
            url_pattern = r'https?://(?:www\.)?douyin\.com/[^\s]+|https?://v\.douyin\.com/[^\s]+'
            short_match = re.search(url_pattern, text)
            if not short_match:
                logger.error("No Douyin URL found in message")
                text_reply = Reply(ReplyType.TEXT, "未找到有效的抖音链接，请检查输入")
                event.channel.send(text_reply, event.message)
                return
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
                    size_reply = Reply(ReplyType.TEXT, f'{size_tip}')
                    event.channel.send(size_reply, event.message)
                else:
                    video_reply = Reply(ReplyType.VIDEO, download_link)
                    event.channel.send(video_reply, event.message)
                    logger.info("视频已发送")
                    
                return Reply(ReplyType.TEXT, f"抖音视频信息：\n用户: {nickname}, 发布时间: {create_time}, 视频大小: {video_size_mb}MB\n点赞: {digg_count}, 评论: {comment_count}, 收藏: {collect_count}, 分享: {share_count}\n描述: {desc}\n无压缩无水印视频链接（有时效）：{short_video_link}")

    def hybrid_parsing(self, url):
        try:
            return self.get_douyin_video_data(url) or {}
        except Exception as exc:
            logger.error('Scraper Exception: %s', exc)
            return {}

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

    def get_douyin_video_data(self, url, retries=3, wait_time=5):
        for attempt in range(retries):
            try:
                response = requests.get(self.api_base_url, params={"url": url})
                if response.status_code == 200:
                    return response.json().get('data', {})
                else:
                    logger.debug(f"API 请求失败，状态码：{response.status}")
            except Exception as e:
                logger.debug(f"API 请求出错: {e}")
            time.sleep(wait_time)
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
