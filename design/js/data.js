/* Sample content for the prototype (the real site reads this from the API). Everything on the pages is placeholder copy. */
export const SITE = { name: 'saubakaの博客', en: 'Baka Blog', author: 'sau_baka', tagline: '不是笨蛋！！' };

export const POSTS = [
  { slug: 'sqlite-backup', href: 'post.html', title: 'SQLite 备份：我差点把自己的数据弄丢', sum: '直接复制数据库文件，到底会出什么事？以及我现在用的三种备份写法。', cat: '代码', tags: ['SQLite', '备份', 'Flask'], date: '2026-10-18', read: 8 },
  { slug: 'lighter-lines', href: '#', title: '把线条调浅了一点点，页面就安静了', sum: '一条 1px 的线，颜色深一档和浅一档，整页的气质完全不同。', cat: '设计', tags: ['CSS', '设计'], date: '2026-10-12', read: 5 },
  { slug: 'scroll-motion', href: '#', title: '跟着滚动走的入场动画，我是这样做的', sum: '不是“进入视野就播放”，而是进度跟着滚动位置走，倒着滚也能倒放。', cat: '代码', tags: ['Vue', '动效'], date: '2026-10-05', read: 9 },
  { slug: 'sunday-evening', href: '#', title: '周末的傍晚', sum: '今天的傍晚像一碗粉色的汤，我看了很久。', cat: '日常', tags: ['随手记'], date: '2026-09-28', read: 1 },
  { slug: 'no-comments', href: '#', title: '为什么我不给博客加评论区', sum: '想说什么可以发邮件。我想把这里做成一个安静的地方。', cat: '随笔', tags: ['博客'], date: '2026-09-20', read: 4 },
  { slug: 'flask-login-min', href: '#', title: 'Flask 里最小的后台登录', sum: '会话、限速、CSRF，一个人用的后台到底需要哪些。', cat: '代码', tags: ['Flask', '安全'], date: '2026-09-11', read: 7 },
  { slug: 'rainy-coffee', href: '#', title: '雨天的咖啡和 bug', sum: '下雨天更容易写出 bug，这不是玄学，是咖啡洒在了键盘上。', cat: '日常', tags: ['咖啡', '随手记'], date: '2026-08-30', read: 3 },
  { slug: 'readme-for-cat', href: '#', title: '给猫写的 README', sum: '如果猫是一个项目，它的安装说明大概是这样的。', cat: '日常', tags: ['猫'], date: '2026-08-14', read: 2 },
];

export const MOMENTS = [
  { href: 'moments.html#m1', text: '把博客的主色调浅了两档，终于不像在看监控大屏了。', mood: '元气' },
  { href: 'moments.html#m2', text: '夜宵是一碗很烫的汤圆。', mood: '开心' },
  { href: 'moments.html#m3', text: 'SQLite 官方文档里的 Backup API 一页，我看了三遍。', mood: '思考' },
  { href: 'moments.html#m4', text: '今天的傍晚像一碗粉色的汤。', mood: '平静' },
  { href: 'moments.html#m5', text: '写了三个小时的 CSS，最后只改了一个数字：1px。', mood: '犯困' },
];

export const PAGES = [
  { href: 'home.html#about', title: '关于我', sum: 'sau_baka 是谁，为什么叫 Baka Blog' },
  { href: 'archive.html', title: '归档', sum: '按年月看所有文章' },
];
