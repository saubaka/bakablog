"""Administrative forms."""

from __future__ import annotations

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, MultipleFileField
from wtforms import (
    BooleanField,
    DateTimeLocalField,
    HiddenField,
    IntegerField,
    PasswordField,
    RadioField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Length,
    NumberRange,
    Optional,
    Regexp,
    ValidationError,
)

HEX_COLOR_VALIDATORS = [
    DataRequired(),
    Regexp(r"^#[0-9A-Fa-f]{6}$", message="请选择或填写六位十六进制颜色。"),
]


class LoginForm(FlaskForm):
    username = StringField("用户名", validators=[DataRequired(), Length(min=3, max=50)])
    password = PasswordField("密码", validators=[DataRequired(), Length(min=8, max=256)])
    remember = BooleanField("在这台设备上保持登录")
    submit = SubmitField("进入后台")


class GatewayConnectionForm(FlaskForm):
    issuer = StringField("发行者地址", validators=[DataRequired(), Length(max=500)])
    client_id = StringField("Client ID", validators=[DataRequired(), Length(max=200)])
    client_secret = PasswordField(
        "Client Secret", validators=[Optional(), Length(min=8, max=512)]
    )
    submit = SubmitField("保存并验证连接")


class MediaUploadForm(FlaskForm):
    image = FileField("选择图片", validators=[DataRequired()])
    alt_text = StringField("替代文字", validators=[Length(max=160)])
    submit = SubmitField("上传到媒体库")


class SiteLogoUploadForm(FlaskForm):
    logo = FileField("网站Logo", validators=[DataRequired()])
    submit = SubmitField("更新网站Logo")


class EmptyForm(FlaskForm):
    submit = SubmitField("确认")


class PostForm(FlaskForm):
    title = StringField("文章标题", validators=[DataRequired(), Length(min=2, max=180)])
    slug = StringField("永久链接", validators=[Optional(), Length(max=180)])
    summary = TextAreaField("摘要", validators=[Optional(), Length(max=360)])
    content_markdown = TextAreaField("Markdown正文", validators=[DataRequired(), Length(min=1)])
    category_id = SelectField("分类", coerce=int, choices=[])
    tags = StringField("标签", validators=[Optional(), Length(max=300)])
    status = SelectField(
        "状态",
        choices=[("draft", "草稿"), ("published", "立即发布"), ("scheduled", "定时发布")],
    )
    published_at = DateTimeLocalField("发布时间", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    is_pinned = BooleanField("置顶")
    is_featured = BooleanField("推荐")
    seo_title = StringField("SEO标题", validators=[Optional(), Length(max=180)])
    seo_description = TextAreaField("SEO描述", validators=[Optional(), Length(max=300)])
    submit = SubmitField("保存文章")

    def validate(self, extra_validators=None):  # type: ignore[no-untyped-def]
        valid = super().validate(extra_validators)
        if self.status.data == "scheduled" and self.published_at.data is None:
            self.published_at.errors.append("定时发布必须设置发布时间。")
            valid = False
        return valid


class TaxonomyForm(FlaskForm):
    taxonomy_type = SelectField("类型", choices=[("category", "分类"), ("tag", "标签")])
    name = StringField("名称", validators=[DataRequired(), Length(min=1, max=80)])
    slug = StringField("链接标识", validators=[Optional(), Length(max=100)])
    description = StringField("说明", validators=[Optional(), Length(max=255)])
    submit = SubmitField("保存")


class ProfileForm(FlaskForm):
    display_name = StringField("显示名称", validators=[DataRequired(), Length(max=80)])
    headline = StringField("身份简介", validators=[DataRequired(), Length(max=160)])
    location = StringField("所在地", validators=[Optional(), Length(max=120)])
    email = StringField("联系邮箱", validators=[Optional(), Length(max=160)])
    short_bio = TextAreaField("首页简介", validators=[Optional(), Length(max=360)])
    bio_markdown = TextAreaField("详细介绍", validators=[Optional()])
    resume_url = StringField("简历地址", validators=[Optional(), Length(max=255)])
    avatar_media_id = SelectField("头像", coerce=int, choices=[])
    submit = SubmitField("保存个人资料")


class ProfileItemForm(FlaskForm):
    item_type = SelectField(
        "内容类型",
        choices=[
            ("skill", "技能"),
            ("experience", "经历"),
            ("goal", "目标"),
            ("social", "社交链接"),
        ],
    )
    title = StringField("名称 / 标题", validators=[DataRequired(), Length(max=140)])
    subtitle = StringField("分组 / 机构 / 地址", validators=[Optional(), Length(max=500)])
    period = StringField("时间段", validators=[Optional(), Length(max=80)])
    description = TextAreaField("说明", validators=[Optional(), Length(max=500)])
    level = IntegerField("熟练度", validators=[Optional(), NumberRange(min=0, max=100)], default=80)
    sort_order = IntegerField("排序", validators=[Optional()], default=0)
    is_visible = BooleanField("前台显示", default=True)
    submit = SubmitField("添加内容")


class ProjectForm(FlaskForm):
    title = StringField("项目名称", validators=[DataRequired(), Length(max=180)])
    slug = StringField("永久链接", validators=[Optional(), Length(max=180)])
    summary = TextAreaField("项目摘要", validators=[Optional(), Length(max=360)])
    content_markdown = TextAreaField("项目详情", validators=[DataRequired()])
    tech_stack = StringField("技术栈", validators=[Optional(), Length(max=300)])
    project_url = StringField("项目地址", validators=[Optional(), Length(max=500)])
    repository_url = StringField("代码仓库", validators=[Optional(), Length(max=500)])
    cover_media_id = SelectField("封面图片", coerce=int, choices=[])
    status = SelectField("状态", choices=[("draft", "草稿"), ("published", "发布")])
    is_featured = BooleanField("精选项目")
    sort_order = IntegerField("排序", validators=[Optional()], default=0)
    submit = SubmitField("保存项目")


class MomentForm(FlaskForm):
    content_markdown = TextAreaField("动态内容", validators=[DataRequired(), Length(max=10000)])
    mood = StringField("心情", validators=[Optional(), Length(max=40)])
    location = StringField("地点", validators=[Optional(), Length(max=120)])
    status = SelectField("状态", choices=[("draft", "草稿"), ("published", "发布")])
    is_pinned = BooleanField("置顶")
    submit = SubmitField("保存动态")


class NavigationForm(FlaskForm):
    label = StringField("名称", validators=[DataRequired(), Length(max=80)])
    url = StringField("链接", validators=[DataRequired(), Length(max=500)])
    location = SelectField(
        "位置", choices=[("header", "顶部"), ("footer", "页脚"), ("both", "顶部和页脚")]
    )
    sort_order = IntegerField("排序", validators=[Optional()], default=0)
    is_visible = BooleanField("显示", default=True)
    open_new_tab = BooleanField("新窗口打开")
    submit = SubmitField("添加导航")


class SiteSettingsForm(FlaskForm):
    hero_title = StringField("首页标题", validators=[DataRequired(), Length(max=180)])
    hero_subtitle = TextAreaField("首页说明", validators=[Optional(), Length(max=500)])
    hero_tags = StringField("首屏短标签", validators=[Optional(), Length(max=240)])
    hero_status = StringField("此刻状态", validators=[Optional(), Length(max=160)])
    hero_primary_label = StringField("主按钮文字", validators=[Optional(), Length(max=40)])
    hero_primary_url = StringField("主按钮链接", validators=[Optional(), Length(max=500)])
    hero_secondary_label = StringField("次按钮文字", validators=[Optional(), Length(max=40)])
    hero_secondary_url = StringField("次按钮链接", validators=[Optional(), Length(max=500)])
    hero_explore_label = StringField("漫游按钮文字", validators=[Optional(), Length(max=40)])
    hero_explore_url = StringField("漫游按钮链接", validators=[Optional(), Length(max=500)])
    about_now = StringField("现在", validators=[Optional(), Length(max=120)])
    about_tools = StringField("使用中", validators=[Optional(), Length(max=120)])
    about_learning = StringField("正在学习", validators=[Optional(), Length(max=120)])
    cta_title = StringField("页尾邀请标题", validators=[Optional(), Length(max=120)])
    cta_text = TextAreaField("页尾邀请说明", validators=[Optional(), Length(max=360)])
    cta_button_label = StringField("页尾按钮文字", validators=[Optional(), Length(max=40)])
    cta_button_url = StringField("页尾按钮链接", validators=[Optional(), Length(max=500)])
    footer_text = StringField("页脚文字", validators=[Optional(), Length(max=255)])
    submit = SubmitField("保存站点文字")


class TransitionSettingsForm(FlaskForm):
    transition_style = RadioField("页面过渡方式", validators=[DataRequired()])
    transition_duration = IntegerField(
        "动画时间（毫秒）", validators=[DataRequired(), NumberRange(min=300, max=2400)]
    )
    transition_color_start = StringField("覆盖起始色", validators=HEX_COLOR_VALIDATORS)
    transition_color_middle = StringField("覆盖过渡色", validators=HEX_COLOR_VALIDATORS)
    transition_color_end = StringField("覆盖结束色", validators=HEX_COLOR_VALIDATORS)
    submit = SubmitField("保存动效设置")


class DialogAppearanceForm(FlaskForm):
    dialog_style = RadioField("弹窗样式", validators=[DataRequired()])
    dialog_color_start = StringField("弹窗起始色", validators=HEX_COLOR_VALIDATORS)
    dialog_color_end = StringField("弹窗结束色", validators=HEX_COLOR_VALIDATORS)
    dialog_accent = StringField("弹窗强调色", validators=HEX_COLOR_VALIDATORS)
    dialog_radius = IntegerField(
        "弹窗圆角", validators=[DataRequired(), NumberRange(min=14, max=42)]
    )
    dialog_width = IntegerField(
        "弹窗宽度", validators=[DataRequired(), NumberRange(min=360, max=720)]
    )
    dialog_backdrop_blur = IntegerField(
        "背景模糊", validators=[DataRequired(), NumberRange(min=0, max=30)]
    )
    dialog_shadow = RadioField("阴影强度", validators=[DataRequired()])
    submit = SubmitField("保存弹窗外观")


class InterfaceAppearanceForm(FlaskForm):
    font_style = RadioField("全局字体", validators=[DataRequired()])
    submit = SubmitField("保存界面风格")


class SeoSettingsForm(FlaskForm):
    site_title = StringField("搜索结果站点名称", validators=[DataRequired(), Length(max=100)])
    title_separator = StringField("标题分隔符", validators=[DataRequired(), Length(max=4)])
    default_description = TextAreaField(
        "默认搜索描述", validators=[DataRequired(), Length(max=300)]
    )
    default_keywords = StringField("默认关键词", validators=[Optional(), Length(max=500)])
    author_name = StringField("默认作者", validators=[Optional(), Length(max=100)])
    default_og_image = StringField("默认分享图片", validators=[Optional(), Length(max=500)])
    og_locale = StringField("Open Graph语言", validators=[DataRequired(), Length(max=20)])
    twitter_card = SelectField("社交卡片类型", choices=[])
    social_handle = StringField("社交账号", validators=[Optional(), Length(max=80)])
    index_site = BooleanField("允许搜索引擎收录公开页面")
    follow_links = BooleanField("允许搜索引擎跟随公开链接")
    index_archives = BooleanField("收录博客归档页")
    index_taxonomies = BooleanField("收录分类与标签页")
    enable_sitemap = BooleanField("启用XML站点地图")
    enable_feed = BooleanField("启用Atom订阅")
    enable_structured_data = BooleanField("输出JSON-LD结构化数据")
    schema_type = SelectField("站点主体类型", choices=[])
    robots_disallow = TextAreaField(
        "robots禁止路径", validators=[Optional(), Length(max=3000)]
    )
    submit = SubmitField("保存SEO设置")


class AccessSettingsForm(FlaskForm):
    allowed_hosts = TextAreaField(
        "允许访问的域名与 IP",
        validators=[Optional(), Length(max=4000)],
    )
    require_https = BooleanField("强制使用 HTTPS")
    confirm_https = BooleanField("我确认 HTTPS 已经可以正常访问")
    submit = SubmitField("保存域名与协议")

    def validate_allowed_hosts(self, field) -> None:  # type: ignore[no-untyped-def]
        from app.services.access import parse_allowed_hosts

        try:
            parse_allowed_hosts(field.data or "")
        except ValueError as error:
            raise ValidationError(str(error)) from error


class CustomPageForm(FlaskForm):
    title = StringField("页面标题", validators=[DataRequired(), Length(max=180)])
    slug = StringField("永久链接", validators=[Optional(), Length(max=180)])
    summary = TextAreaField("页面摘要", validators=[Optional(), Length(max=300)])
    content_markdown = TextAreaField("页面内容", validators=[DataRequired()])
    status = SelectField("状态", choices=[("draft", "草稿"), ("published", "发布")])
    show_in_navigation = BooleanField("显示在导航")
    sort_order = IntegerField("排序", validators=[Optional()], default=0)
    submit = SubmitField("保存页面")


class FriendApplicationForm(FlaskForm):
    name = StringField("网站名称", validators=[DataRequired(), Length(min=2, max=100)])
    url = StringField("网站地址", validators=[DataRequired(), Length(max=500)])
    description = TextAreaField("一句介绍", validators=[DataRequired(), Length(min=4, max=300)])
    avatar_url = StringField("头像地址", validators=[Optional(), Length(max=500)])
    applicant_email = StringField("联系邮箱", validators=[Optional(), Length(max=160)])
    website = StringField("请留空", validators=[Optional(), Length(max=0)])
    submit = SubmitField("提交友链申请")


class FriendAdminForm(FlaskForm):
    name = StringField("网站名称", validators=[DataRequired(), Length(max=100)])
    url = StringField("网站地址", validators=[DataRequired(), Length(max=500)])
    description = TextAreaField("介绍", validators=[DataRequired(), Length(max=300)])
    avatar_url = StringField("头像地址", validators=[Optional(), Length(max=500)])
    category_id = SelectField("分类", coerce=int, choices=[])
    status = SelectField(
        "状态",
        choices=[
            ("pending", "待审核"),
            ("approved", "已通过"),
            ("rejected", "已拒绝"),
            ("disabled", "已停用"),
        ],
    )
    sort_order = IntegerField("排序", validators=[Optional()], default=0)
    is_featured = BooleanField("精选友链")
    submit = SubmitField("保存友链")


class FriendCategoryForm(FlaskForm):
    name = StringField("分类名称", validators=[DataRequired(), Length(max=80)])
    slug = StringField("链接标识", validators=[Optional(), Length(max=100)])
    description = StringField("说明", validators=[Optional(), Length(max=255)])
    sort_order = IntegerField("排序", validators=[Optional()], default=0)
    submit = SubmitField("保存分类")


class AlbumForm(FlaskForm):
    title = StringField("相册名称", validators=[DataRequired(), Length(max=160)])
    slug = StringField("永久链接", validators=[Optional(), Length(max=180)])
    description = TextAreaField("相册说明", validators=[Optional(), Length(max=500)])
    status = SelectField("状态", choices=[("draft", "草稿"), ("published", "发布")])
    sort_order = IntegerField("排序", validators=[Optional()], default=0)
    submit = SubmitField("保存相册")


class PhotoBatchUploadForm(FlaskForm):
    images = MultipleFileField("批量选择图片", validators=[DataRequired()])
    submit = SubmitField("上传照片")


class CommentForm(FlaskForm):
    author_name = StringField("昵称", validators=[DataRequired(), Length(min=2, max=80)])
    email = StringField("邮箱", validators=[Optional(), Length(max=160)])
    website = StringField("个人网站", validators=[Optional(), Length(max=500)])
    content = TextAreaField("评论内容", validators=[DataRequired(), Length(min=2, max=3000)])
    parent_id = HiddenField("回复评论", validators=[Optional()])
    contact = StringField("请留空", validators=[Optional(), Length(max=0)])
    submit = SubmitField("提交评论")


class GuestbookForm(FlaskForm):
    author_name = StringField("昵称", validators=[DataRequired(), Length(min=2, max=80)])
    email = StringField("邮箱", validators=[Optional(), Length(max=160)])
    content = TextAreaField("留言内容", validators=[DataRequired(), Length(min=2, max=3000)])
    website = StringField("请留空", validators=[Optional(), Length(max=0)])
    submit = SubmitField("留下脚印")


class AdminReplyForm(FlaskForm):
    content = TextAreaField("回复内容", validators=[DataRequired(), Length(min=2, max=2000)])
    submit = SubmitField("发送回复")
