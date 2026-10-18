from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from blog.models import Post, SiteConfig, Tag

class Command(BaseCommand):
    help = '导入可重复运行的演示文章；生产环境禁止运行。'

    def handle(self, *args, **options):
        if settings.PRODUCTION:
            raise CommandError('生产环境不允许导入演示内容。')
        SiteConfig.objects.get_or_create(pk=1)
        entries = [
            ('weekend-walk', '在公园里，把周末过慢一点', '散步', '没有目的地，也没有待办清单。只沿着树荫走，听风翻动叶子的声音。',
             '## 把时间还给自己\n\n周末醒得很早，索性出门走走。公园里的树似乎又长高了一点，阳光从叶子的缝隙里落下来。\n\n> 有些日子，什么也不赶，就是最好的安排。\n\n绕着湖走了一圈，坐在长椅上看了很久的水。\n\n## 今日的小小收获\n\n- 看见一只不怕人的小鸟\n- 找到一条安静的小路\n- 把手机收起来，认真发了会儿呆\n\n回家路上买了面包。这一天，好像也没有发生什么，却很想记下来。'),
            ('afternoon-reading', '一杯热茶，和没读完的那本书', '阅读', '把窗户打开一点，让风进来。那些平时读不进去的句子，在下午忽然有了回声。',
             '## 一个留给阅读的下午\n\n水烧开的时候，桌上的书还停在上次折角的那一页。今天没有急着往后翻，先把前面的几段又读了一遍。\n\n原来同一句话，在不同的日子里，会有不同的意思。\n\n> 慢一点，也能走到想去的地方。\n\n茶凉了，再添一点热水。窗外的影子慢慢移动，下午就这样过去了。'),
            ('rainy-day', '下雨的时候，城市也安静下来', '日常', '雨落在窗台上，像一封没有署名的信。今天适合待在家里，把生活整理一下。',
             '## 雨天的声音\n\n早晨是被雨声叫醒的。拉开窗帘，远处的楼都变得柔和了。\n\n做了简单的早饭，整理了书桌，又给植物浇了一点水。\n\n不必每一天都有大事发生。把眼前的小事做好，也是一种满足。'),
            ('kitchen-notes', '第一次认真做一顿晚饭', '厨房', '切菜、热锅、等待香气冒出来。原来照顾好自己，可以从一碗热乎乎的饭开始。',
             '## 厨房里的小实验\n\n照着记下来的步骤，给自己做了一顿晚饭。火候还不太熟练，但端上桌的时候，还是很开心。\n\n1. 认真洗好食材\n2. 不慌不忙地准备\n3. 坐下来，好好吃饭\n\n下次想试试新的汤。先把这个念头记在这里。'),
        ]
        for slug, title, tag_name, summary, body in entries:
            tag, _ = Tag.objects.get_or_create(name=tag_name, defaults={'slug': tag_name})
            post, created = Post.objects.get_or_create(slug=slug, defaults={
                'title': title, 'summary': summary, 'body': body, 'status': Post.Status.PUBLISHED,
            })
            if created:
                post.tags.add(tag)
        self.stdout.write(self.style.SUCCESS('演示内容已准备好（不会覆盖已有文章）。'))
