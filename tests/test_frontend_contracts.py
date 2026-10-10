from __future__ import annotations

import re
from pathlib import Path


def test_small_window_theme_is_the_final_visual_authority():
    template = Path("app/templates/layouts/base.html").read_text(encoding="utf-8")
    styles = Path("app/static/styles/small-window-theme.css").read_text(encoding="utf-8").lower()
    assert template.index("styles/app.css") < template.index("styles/small-window-theme.css")
    for token in ("#f7f9fc", "#edf4fc", "#f7e5ed", "#ebf3fa", "#d9e8f6", "#354052", "#526fa6"):
        assert token in styles
    assert "--radius-control: 13px" in styles
    assert "--radius-card: 20px" in styles
    assert "--radius-panel: 28px" in styles
    assert ".admin-body" in styles
    assert ".admin-topbar" in styles
    assert ".admin-table" in styles
    assert ".dashboard-widget" in styles
    assert "background-image: none !important" in styles
    assert "prefers-reduced-motion: reduce" in styles


def test_mobile_drawer_has_atomic_visibility_and_viewport_guards():
    script = Path("app/static/scripts/app.js").read_text(encoding="utf-8")
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    assert "mobileDrawerState" in script
    assert "setSiteInert(true)" in script
    assert "setSiteInert(false)" in script
    assert "window.innerWidth > 860" in script
    assert "100dvh" in styles
    assert "visibility:hidden" in styles
    assert "pointer-events:none" in styles
    assert "overflow-y:auto" in styles
    assert ".icon-button.mobile-menu-button { display: none; }" in styles
    assert ".icon-button.mobile-menu-button { display:inline-grid; }" not in styles
    assert ".site-nav__actions .icon-button:first-child { display:none; }" not in styles


def test_reading_progress_remeasures_dynamic_article_content():
    script = Path("app/static/scripts/app.js").read_text(encoding="utf-8")
    assert "ResizeObserver" in script
    assert "window.visualViewport" in script
    assert "article.scrollHeight" in script
    assert "data-reading-progress-fill" in script
    assert "data-reading-progress-value" in script


def test_home_motion_has_interruptible_and_reduced_motion_paths():
    script = Path("app/static/scripts/app.js").read_text(encoding="utf-8")
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    assert "pointercancel" in script
    assert "is-releasing" in script
    assert "IntersectionObserver" in script
    assert "data-tilt" in script
    assert "data-count" in script
    assert 'data-motion="reduce"' in styles
    assert 'data-performance="low"' in styles
    assert (
        'html.is-motion-ready[data-motion="reduce"] body .motion-line-target.is-outline-ready'
        in styles
    )
    assert (
        'html.is-motion-ready[data-performance="low"] body .motion-line-target.is-outline-ready'
        in styles
    )


def _home_branch_keys(template: str) -> set[str]:
    """Every module key the homepage actually branches on.

    Accepts both the single-key form (``module.module_key == 'hero'``) and the
    grouped form (``module.module_key in ('moments','gallery')``) introduced in
    v1.30.0 when moments and the filmstrip started sharing one row.
    """

    keys = set(re.findall(r"module\.module_key == '([a-z]+)'", template))
    for group in re.findall(r"module\.module_key in \(([^)]*)\)", template):
        keys.update(re.findall(r"'([a-z]+)'", group))
    return keys


def test_home_v3_exposes_editorial_modules_without_stats_strip():
    template = Path("app/templates/public/home.html").read_text(encoding="utf-8")
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    assert _home_branch_keys(template) == {
        "hero",
        "posts",
        "projects",
        "moments",
        "gallery",
        "about",
        "links",
        "cta",
    }
    assert "content-state--" in template
    assert "data-local-time" not in template
    assert "home-stats" not in template
    assert "home-v3" in template
    assert "home-intro__surface" in template
    assert "home-about-v3__intro" in template
    assert "home-about-v3__facts" in template
    assert "home-empty card" not in template
    assert ".home-v3" in styles
    assert "feature_is_brief" in template
    assert ".home-article-lead--brief" in styles


def test_home_moments_and_gallery_share_one_adaptive_editorial_region():
    template = Path("app/templates/public/home.html").read_text(encoding="utf-8")
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    # The pair is rendered once, by whichever module the admin ordered first.
    assert "ns.duo_rendered" in template
    assert template.count("home-daily__moments") == 1
    assert template.count("home-daily__gallery") == 1
    assert "{% if moments or gallery_items %}" in template
    assert "home-daily--solo" in template
    assert ".home-daily--solo" in styles


def test_home_admin_matches_real_modules_and_has_clear_editing_sections():
    template = Path("app/templates/admin/content/site_content.html").read_text(encoding="utf-8")
    service = Path("app/services/content.py").read_text(encoding="utf-8")
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    for section_id in (
        "home-copy",
        "home-actions",
        "home-about",
        "home-footer",
        "home-modules",
        "home-navigation",
    ):
        assert f'id="{section_id}"' in template
    for label in (
        "内容来源",
        "前台布局",
        "页面顺序",
        "保存此模块",
        "保存这条导航",
    ):
        assert label in template
    assert "stats_items" not in template + service
    assert "站点速览" not in template + service
    assert "按“文案" not in template
    assert "排序建议" not in template
    assert "HOME_MODULE_ADMIN_META" in service
    assert '"projects": {' in service
    assert '"layout": "主项目与项目索引"' in service
    assert '("showcase", "横向展柜")' not in service
    assert "home-module-card-v3" in styles
    assert "home-navigation-card__fields" in styles


def test_blue_highlights_are_soft_and_admin_navigation_has_no_blue_fill():
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8").lower()
    banned_deep_blue = (
        "#3f75aa",
        "#4276ac",
        "#356c9e",
        "#366d9f",
        "#568bc0",
        "#3971a8",
        "#6398cb",
        "#3c74aa",
        "rgba(63,117,170",
        "rgba(77,130,186",
    )
    assert all(color not in styles for color in banned_deep_blue)
    assert "background-image:none!important" in styles
    assert ".admin-nav-group.is-open{border-color:#eef3f6;background-color:#fbfdff}" in styles
    assert ".admin-nav { display:grid; gap:6px; padding:8px; border:0;" in styles
    assert "border-radius:22px; background:transparent; box-shadow:none;" in styles
    assert ".admin-nav a.is-current { border-color:#eaebef; background:#fff;" in styles


def test_blog_and_navigation_open_the_independent_global_search_page():
    blog = Path("app/templates/blog/list.html").read_text(encoding="utf-8")
    navigation = Path("app/templates/components/site_nav.html").read_text(encoding="utf-8")
    search = Path("app/templates/public/search.html").read_text(encoding="utf-8")
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    assert "url_for('public.search')" in blog
    assert "url_for('public.search')" in navigation
    assert "data-global-search" in search
    assert "data-search-mode" in search
    assert ".global-search-box" in styles
    assert ".global-search-panel" in styles
    assert "grid-template-columns: auto minmax(0, 1fr) auto;" in styles
    assert ".global-search-box .button" in styles
    assert "grid-column: auto;" in styles


def test_capsule_navigation_reacts_immediately_to_scroll_direction():
    template = Path("app/templates/components/site_nav.html").read_text(encoding="utf-8")
    mobile_template = Path("app/templates/components/mobile_nav.html").read_text(encoding="utf-8")
    script = Path("app/static/scripts/app.js").read_text(encoding="utf-8")
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    assert "data-capsule-nav" in template
    assert "data-mobile-capsule-nav" in mobile_template
    assert "pageCanScroll" in script
    assert "scrollDelta > 0" in script
    assert "scrollDelta < 0" in script
    assert "scrollDelta > 3" not in script
    assert "nearPageTop" not in script
    assert "capsuleNavigation.offsetHeight + 36" not in script
    assert "capsuleNavigation.contains(doc.activeElement)" not in script
    assert ".site-header.is-nav-hidden" in styles
    assert "@keyframes capsule-nav-arrive" in styles
    assert "(min-width: 621px)" in script
    assert "mobilePageCanScroll" in script
    assert ".mobile-bottom-nav.is-mobile-nav-hidden" in styles
    assert "@keyframes mobile-capsule-nav-arrive" in styles


def test_motion_outline_uses_one_interruptible_tiered_timeline():
    script = Path("app/static/scripts/app.js").read_text(encoding="utf-8")
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    home = Path("app/templates/public/home.html").read_text(encoding="utf-8")
    assert "motionCandidateSelector" in script
    assert "registerMotionTarget" in script
    assert "data-motion-surface" in home
    assert "data-motion-control" in home
    assert "data-motion-heading" in home
    assert "data-motion-shell" in home
    assert "createMotionOutline" in script
    assert "motion-outline__path" in script
    assert "path.getTotalLength()" in script
    assert "getRenderedPathLength" in script
    assert "getMotionRadii" in script
    assert "configureMotionOutline" in script
    assert "new ResizeObserver" in script
    assert "--motion-path-length" in styles
    assert "motion-outline" in styles
    assert "stroke-dashoffset" in styles
    assert "data-motion-content" in home
    assert ".motion-content" in styles
    assert "filter: blur(3px);" in styles
    assert ".motion-line {" not in styles
    assert ".motion-outline__path" in styles
    assert "body .home-v2 .home-about-collage" in styles
    assert "background: transparent !important" in styles
    assert script.count("motionObserver = new IntersectionObserver") == 1
    assert "const homeObserver = new IntersectionObserver" not in script
    assert "const cardObserver = new IntersectionObserver" not in script
    assert "homeShellItems" in script
    assert "motionShell" in script
    assert '[data-motion-shell="true"]' in styles
    assert "motionPersist" in script
    assert "visibleMotionRatio" in script
    assert "threshold: [0, .08, .12, .16, .28, .5]" in script
    assert "motionMutation" in script
    assert "if (doc.body)" in script
    assert "is-outline-ready" in script
    assert ".motion-line-target.is-outline-ready" in styles
    assert ".motion-line-target:not(.is-outline-ready) > .motion-outline" in styles
    assert "pageReadyEvent" in script
    assert "event.persisted" in script
    assert "restoredNavigation" not in script
    assert "const motionContentTimers = new WeakMap()" not in script
    assert "motion-copy-revealed" not in script
    assert "motion-copy-revealed" not in styles
    assert "const motionTimelines = new WeakMap()" in script
    assert "createMotionTimeline" in script
    assert "motionProfileFor" in script
    assert "componentMotionDuration" in script
    assert "motionSlotLimits = { surface: 8, light: 12 }" in script
    assert "motionQueueTimers" in script
    assert "}, 90)" in script
    assert "pendingMotionStates" in script
    assert "animation.playbackRate = playbackRate" in script
    assert "animation.currentTime = currentTime" in script
    assert "const motionStateTimers = new WeakMap()" not in script
    assert "@keyframes motion-content-reverse" not in styles
    assert "is-motion-active" in styles
    assert "componentMotionBlur" in script
    assert "soft: 3" in script
    assert "motion-outline__origin" not in script + styles
    assert "component-motion-duration" in script
    assert "duration * .66" in script
    assert "duration * .5" in script
    assert "duration * .45" in script
    assert "springSampleCache" in script
    assert "step = 1 / 120" in script
    assert "springParameters" in script
    assert "cardSurfaceProgress" in script
    assert "motionChildControls" in script
    assert "controlsOwnedBy" in script
    assert "setMotionSurfaceOwned" in script
    assert "motionSurfaceKeyframes" not in script
    assert "clipPath:" not in script
    assert "motion-outline__path--trace" not in script
    assert "motion-surface-layer" in script
    assert "syncAdminDrawerAccessibility" in script
    assert "adminSidebar.setAttribute('inert', '')" in script
    assert ".home-intro__portrait .hero-avatar { position:relative; inset:auto;" in styles
    assert ".friend-board::before { display:none; }" in styles
    assert "data-tilt" not in home
    assert "collectMotionContent" in script
    assert "previousMotionTops" in script
    assert (
        ".button,.icon-button,.card--interactive,.film-frame,.moment-note { will-change:transform; }"
        not in styles
    )
    assert 'data-motion-state="idle"' in styles
    assert "target.dataset.motionState = revealed ? 'drawing' : 'reversing'" in script
    assert 'data-motion-state="settled"' in styles


def test_mobile_drawer_identity_card_is_compact_without_connection_slogan():
    drawer = Path("app/templates/components/mobile_drawer.html").read_text(encoding="utf-8")
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    assert "CLOUDGATE CONNECTED" not in drawer
    assert "grid-template-columns: repeat(auto-fit, minmax(74px, 1fr));" in styles


def test_article_cards_are_full_links_with_soft_motion():
    home = Path("app/templates/public/home.html").read_text(encoding="utf-8")
    blog = Path("app/templates/blog/list.html").read_text(encoding="utf-8")
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    assert '<a class="home-article-lead article-card-link' in home
    assert '<a class="home-article-row article-card-link' in home
    assert '<a class="list-post article-card-link' in blog
    assert '<article class="list-post' not in blog
    assert "@keyframes article-card-release" in styles
    assert ".article-card-link:hover::before" in styles
    assert ".article-card-link:focus-visible" in styles


def test_interaction_forms_stack_and_friend_application_uses_dialog():
    guestbook = Path("app/templates/public/guestbook.html").read_text(encoding="utf-8")
    article = Path("app/templates/blog/article.html").read_text(encoding="utf-8")
    comments = Path("app/templates/components/comments.html").read_text(encoding="utf-8")
    links = Path("app/templates/public/links.html").read_text(encoding="utf-8")
    script = Path("app/static/scripts/app.js").read_text(encoding="utf-8")
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    assert '<section class="card guestbook-form">' in guestbook
    assert 'include "components/comments.html"' in article
    assert 'class="comment-form card"' in comments
    assert "data-human-check" in comments
    assert (
        ".guestbook-layout,.comments-layout { display:grid; grid-template-columns:minmax(0,1fr);"
        in styles
    )
    assert 'class="friend-board card"' in links
    assert 'data-open-dialog="friend-application-modal"' in links
    assert '<dialog class="modal friend-application-modal"' in links
    assert "application_code or form.errors" in links
    assert "dialog[data-open-on-load]" in script


def test_friend_editor_save_action_is_explicit_and_right_aligned():
    template = Path("app/templates/admin/interactions/friend_editor.html").read_text(
        encoding="utf-8"
    )
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    assert '<button class="button button--primary is-save-action" type="submit"' in template
    assert "data-save-action" in template
    assert ".admin-form>.is-save-action" in styles
    assert "margin-inline-start:auto!important" in styles


def test_admin_navigation_groups_every_editing_area_and_flattens_single_entries(
    logged_in_client,
):
    template = Path("app/templates/layouts/admin.html").read_text(encoding="utf-8")
    rendered = logged_in_client.get("/admin/").get_data(as_text=True)
    script = Path("app/static/scripts/app.js").read_text(encoding="utf-8")
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    for heading in (
        "仪表盘",
        "文章",
        "标签",
        "动态",
        "评论",
        "项目",
        "媒体",
        "相册",
        "页面",
        "菜单",
        "站点",
        "主题",
        "系统管理",
    ):
        assert f"<strong>{heading}</strong>" in template
    for editing_area in (
        "全部文章",
        "新建文章",
        "分类列表",
        "新建分类",
        "标签列表",
        "新建标签",
        "全部动态",
        "新建动态",
        "项目管理",
        "媒体",
        "相册目录",
        "新建相册",
        "前台页面",
        "主页管理",
        "菜单管理",
        "管理面板编辑",
        "标题与Logo",
        "页尾内容设置",
        "网站链接",
        "安全",
        "字体",
        "提示",
        "动画",
        "弹窗与通知",
        "预览",
        "系统状态",
        "操作日志",
        "关于",
    ):
        assert (
            f"<span>{editing_area}</span>" in rendered
            or f"<strong>{editing_area}</strong>" in rendered
        )
    for redundant_create_link in (
        "新建项目",
        "写生活动态",
        "新建友链",
        "添加账号",
    ):
        assert f"<span>{redundant_create_link}</span>" not in template
    assert template.count("data-admin-menu-group") == 13
    assert template.count("data-admin-menu-toggle") == 11
    assert template.count("data-admin-submenu") == 0
    assert "互动管理" not in template
    assert "举报" not in template
    assert 'data-motion-surface="feature" data-motion-controls="none"' in template
    assert "data-admin-drawer data-motion-skip" in template
    assert 'type="submit" data-motion-skip aria-label="退出登录"' in template
    assert "target.dataset.motionControls === 'none'" in script
    assert "{% macro admin_child" in template
    assert 'data-admin-child-key="{{ key }}"' in template
    assert "setAdminSubmenu" in script
    assert "adminSubmenus.forEach" in script
    assert "animateAdminAccordion" in script
    assert "panel.scrollHeight" in script
    assert "panel.style.height" in script
    assert "duration: 280" in script
    assert "duration: 300" in script
    assert "cloud-diary-admin-menu-open" in script
    assert "setAdminMenuGroup" in script
    assert "accordionReady" in script
    assert "grid-template-rows:0fr" in styles
    assert ".admin-subnav__items" in styles
    assert ".admin-nav-group.is-open .admin-nav-group__items" in styles
    assert 'data-height-accordion="true"' in styles
    assert "transition:height 280ms var(--spring),opacity 160ms var(--ease)" in styles
    assert "transition:height 300ms var(--spring),opacity 180ms var(--ease)" in styles
    assert "content-visibility:hidden" in styles


def test_media_library_has_uniform_three_preset_preview_sizes():
    template = Path("app/templates/admin/media.html").read_text(encoding="utf-8")
    script = Path("app/static/scripts/app.js").read_text(encoding="utf-8")
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    for size in ("compact", "standard", "large"):
        assert f'data-media-preview-size="{size}"' in template
        assert f'[data-preview-size="{size}"]' in styles
    assert "data-media-grid" in template
    assert "media-card__preview" in template
    assert "cloud-diary-media-preview-size" in script
    assert "height:var(--media-preview-height)" in styles


def test_visual_editor_is_local_complete_and_image_layout_is_persistent():
    post_template = Path("app/templates/admin/posts/editor.html").read_text(encoding="utf-8")
    page_template = Path("app/templates/admin/content/page_editor.html").read_text(encoding="utf-8")
    shared_editor = Path("app/templates/components/visual_editor.html").read_text(encoding="utf-8")
    template = post_template + page_template + shared_editor
    script = Path("app/static/scripts/editor.js").read_text(encoding="utf-8")
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    service = Path("app/services/blog.py").read_text(encoding="utf-8")
    assert "scripts/editor.js" in template
    for control in (
        "data-rich-editor",
        'data-editor-mode="source"',
        'data-editor-mode="preview"',
        "data-editor-font-size",
        "data-editor-color",
        "data-editor-highlight",
        "data-editor-fullscreen",
        "data-image-size",
        "data-image-align",
        "data-image-rotate",
        "data-image-ratio",
        "data-image-width",
        "data-image-move",
        "data-editor-outline",
        'data-open-dialog="editor-media-dialog"',
        "data-editor-media-item",
        "data-editor-widget-toggle",
    ):
        assert control in template
    assert "dragstart" in script and "dragover" in script and "drop" in script
    assert "article-media--custom" in script
    assert "sourceEditor.value = serializedHtml()" in script
    assert "data-image-settings" in script
    assert "positionImageInspector" in script
    assert "selectedFigure.getBoundingClientRect()" in script
    assert "imageInspector.dataset.side = side" in script
    assert "richEditor.dataset.inspectorSide = side" in script
    assert "ResizeObserver(queueInspectorPosition)" in script
    assert "figure.article-media.is-selected" in styles
    assert 'data-inspector-side="right"' in styles
    assert 'data-inspector-side="left"' in styles
    assert "requestAnimationFrame(() =>" in script
    assert ".visual-editor.is-fullscreen" in styles
    assert ".article-media__settings" in styles
    assert ".editor-sidebar-widget__body" in styles
    assert '"figure": ["class", "style"]' in service
    assert '"background-color", "color", "text-align", "width"' in service
    assert 'include "components/visual_editor.html"' in post_template
    assert 'include "components/visual_editor.html"' in page_template
    assert "data-content-editor-form" in post_template
    assert "data-content-editor-form" in page_template
    assert "data-editor-entity" in shared_editor
    assert "markdown-help" not in shared_editor
    assert "editor-help-card" not in post_template + page_template


def test_every_internal_navigation_path_has_transition_feedback():
    script = Path("app/static/scripts/app.js").read_text(encoding="utf-8")
    bootstrap = Path("app/static/scripts/transition-bootstrap.js").read_text(encoding="utf-8")
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    admin = Path("app/templates/layouts/admin.html").read_text(encoding="utf-8")
    settings = Path("app/templates/admin/content/transitions.html").read_text(encoding="utf-8")
    content_service = Path("app/services/content.py").read_text(encoding="utf-8")
    assert "target.origin !== window.location.origin" in script
    assert "link.closest('[contenteditable=\"true\"]')" in script
    assert "window.location.assign(target.href)" in script
    assert "is-page-leaving" in script
    assert "cloud-diary-route-transition" in script
    assert "is-page-entering" in bootstrap
    assert "isPublicRoute" in bootstrap
    assert "root.dataset.pageTransition === 'stretch'" in bootstrap
    assert "root.dataset.pageTransition = 'fade'" in bootstrap
    assert "routeTransitionDurations" in script
    assert "button, a[href], summary" in script
    assert '[role="button"]' in script
    for style in ("stretch", "fade", "zoom-blur", "none"):
        assert f'data-page-transition="{style}"' in styles
        assert f'("{style}",' in content_service
    assert "form.transition_style" in settings
    assert "'动画'" in admin
    assert "'弹窗与通知'" in admin
    assert "route-stretch-cover" in styles
    assert "route-content-focus" in styles
    assert "editor-page-arrive" in styles
    assert "pages\\/(?:new\\/|\\d+\\/edit\\/)" in script
    assert "data-transition-duration" in Path("app/templates/layouts/base.html").read_text(
        encoding="utf-8"
    )
    assert "configuredTransitionDuration" in script
    assert "data-transition-duration-range" in settings
    assert "transition_color_start" in settings
    assert "component_motion_duration" in settings
    assert "component_motion_style" in settings
    assert "component_motion_color" in settings
    assert "component_motion_accent" not in settings
    assert "component_motion_softness" in settings
    assert "data-component-motion-replay" in settings
    assert "data-component-motion-reverse" in settings
    assert "data-component-motion-reduced" in settings
    assert "data-component-motion-stage" in settings
    assert "data-component-motion-duration" in Path("app/templates/layouts/base.html").read_text(
        encoding="utf-8"
    )
    assert "motion-preparing" in bootstrap
    assert "springSamples" in script
    assert "window.__cloudtraceMotionDebug" in script
    assert "motion-outline__path--trace" not in script
    assert "cloudtrace:component-motion-settings" in script
    assert ".motion-surface-layer" in styles
    assert 'data-motion-state="idle"' in styles
    assert "var(--route-color-start" in styles
    assert (
        "@keyframes route-stretch-glint-out { from { opacity:0; transform:translateX(-160%); }"
        in styles
    )
    assert "from { opacity:.2; transform:translateX(calc(100vw - 30px)); }" not in styles


def test_notifications_use_top_droplet_capsules():
    base = Path("app/templates/layouts/base.html").read_text(encoding="utf-8")
    styles = Path("app/static/styles/notifications.css").read_text(encoding="utf-8")
    legacy = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    runtime = Path("app/static/scripts/notifications.js").read_text(encoding="utf-8")
    app_script = Path("app/static/scripts/app.js").read_text(encoding="utf-8")
    # One host at the top centre; the old lower-right region and toast rules are gone.
    assert 'id="toast-region"' in base and 'popover="manual"' in base
    assert "toast-region" not in legacy and ".toast {" not in legacy
    assert "data-dismiss-toast" not in base + app_script
    assert base.index("scripts/notifications.js") < base.index("scripts/app.js")
    assert "data-flash-source" in base and "flash-noscript" in base
    assert "top: max(16px, env(safe-area-inset-top));" in styles
    assert "border: 1px solid var(--notice-line);" in styles
    for keyframes in ("notification-drop-in", "notification-drop-out", "notification-word-out", "notification-word-in"):
        assert f"@keyframes {keyframes}" in styles
    # Stack, reading clock, dialog top-layer host and safe text handling.
    for contract in ("VISIBLE_LAYERS = 3", "QUEUE_LIMIT = 8", "createReadingTimer", "topModalDialog",
                     "showPopover", "'hover'", "'blur'", "'hidden'", "'background'", "textContent"):
        assert contract in runtime
    assert "innerHTML" not in runtime
    assert "DEFAULT_MOTION = { enter: 780, exit: 680, textOut: 160, textIn: 340, stack: 320 }" in runtime
    assert "window.CloudtraceNotifications?.notify" in app_script
    assert "progressNotice(" in app_script


def test_complete_appearance_gallery_exposes_every_real_theme_family():
    template = Path("app/templates/public/components.html").read_text(encoding="utf-8")
    script = Path("app/static/scripts/app.js").read_text(encoding="utf-8")
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    for heading in (
        "主题配色与表面",
        "全局字体",
        "按钮、图标与状态",
        "卡片与内容",
        "表单与选择",
        "菜单与导航",
        "页面过渡",
        "弹窗外观",
        "反馈、通知与进度",
        "媒体与加载",
        "编辑器与排版",
    ):
        assert heading in template
    assert 'data-component-motion="{{ value }}"' in template
    assert "component-shadow-card--{{ value }}" in template
    assert "dialog-style-choice--{{ value }}" not in template
    assert "font-choice--{{ value }}" in template
    for value in (
        "stretch",
        "fade",
        "zoom-blur",
        "none",
        "none",
        "light",
        "deep",
        "cloud-rounded",
        "candy-soft",
        "playful-yuan",
        "diary-serif",
        "starlight-kaiti",
        "neumorphic-clean",
    ):
        assert value in template or value in Path("app/services/content.py").read_text(
            encoding="utf-8"
        )
    assert "data-component-motion-stage" in template
    assert 'data-dialog-preview="confirm"' in template
    assert 'data-demo-tone="success"' in template
    assert ".component-page--complete" in styles
    assert "data-component-motion" in script


def test_identity_menu_has_a_downward_only_hover_bridge():
    script = Path("app/static/scripts/app.js").read_text(encoding="utf-8")
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    assert ".identity-menu::after" in styles
    assert "top: 100%" in styles
    assert "height: 14px" in styles
    assert "insideDownwardBridge" in script
    assert "event.clientY > triggerRect.bottom" in script
    assert "event.clientY < panelRect.top" in script
    assert "menu.addEventListener('mouseleave'" not in script


def test_dialog_preview_has_no_decorative_popup_copy():
    base = Path("app/templates/layouts/base.html").read_text(encoding="utf-8")
    app_script = Path("app/static/scripts/app.js").read_text(encoding="utf-8")
    editor_script = Path("app/static/scripts/editor.js").read_text(encoding="utf-8")
    dialogs = Path("app/templates/admin/content/dialogs.html").read_text(encoding="utf-8")
    combined = base + app_script + editor_script + dialogs
    for phrase in (
        "温柔确认",
        "温柔输入",
        "小小提示",
        "温柔提示",
        "温柔提醒",
        "一朵本地弹窗",
        "一朵轻轻浮起的弹窗",
        "LOCAL COMPONENT",
        "THEME PREVIEW",
        "LIVE DIALOG",
    ):
        assert phrase not in combined
    assert "data-app-dialog-eyebrow" not in combined
    assert "dialog-live-preview" not in dialogs


def test_default_controls_and_browser_dialogs_use_project_theme():
    base = Path("app/templates/layouts/base.html").read_text(encoding="utf-8")
    app_script = Path("app/static/scripts/app.js").read_text(encoding="utf-8")
    editor_script = Path("app/static/scripts/editor.js").read_text(encoding="utf-8")
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    assert "data-app-system-dialog" in base
    assert "requestSystemDialog" in app_script
    assert "themedConfirm" in app_script
    assert "themedPrompt" in app_script
    assert "window.confirm" not in app_script + editor_script
    assert "window.prompt" not in app_script + editor_script
    assert "window.alert" not in app_script + editor_script
    assert "button:not([class])" in styles
    assert "select:not([class])" in styles
    assert "::file-selector-button" in styles
    assert ".app-system-dialog" in styles
    dialogs = Path("app/templates/admin/content/dialogs.html").read_text(encoding="utf-8")
    admin = Path("app/templates/layouts/admin.html").read_text(encoding="utf-8")
    # Dialog presets with gradient surfaces were retired in 1.41.0; the
    # outline colour, radius, width, blur and shadow remain and really apply.
    assert "form.dialog_style" not in dialogs and "dialog_color_start" not in dialogs
    for name in ("dialog_accent", "dialog_radius", "dialog_width", "dialog_backdrop_blur", "dialog_shadow"):
        assert f"form.{name}" in dialogs
    assert "admin.dialog_appearance" in admin
    assert "--dialog-accent" in styles
    for mode in ("confirm", "prompt", "alert"):
        assert f'data-dialog-preview="{mode}"' in dialogs
    assert 'data-dialog-range="{{ key }}"' in dialogs
    for metric in ("radius", "width", "blur"):
        assert metric in dialogs
    assert "dialogMetricConfig" in app_script
    assert "dialog_shadow" in dialogs
    assert "--dialog-backdrop-blur" in styles
    assert "data-motion-toggle" not in base
    assert "cloud-diary-motion" not in app_script
    assert "setMotionPreference" not in app_script
    assert "toast_background" in dialogs
    assert "toast_duration" in dialogs
    assert "overlay-line-orbit" not in styles
    overlays = Path("app/static/styles/notifications.css").read_text(encoding="utf-8")
    assert "dialog.modal::before { content: none !important;" in overlays
    assert ".is-closing::backdrop" in overlays
    assert "dialogLifecycle" in app_script and "finishDialogClose" in app_script
    assert "IMAGE STUDIO" not in base
    assert "data-motion-skip" in base


def test_runtime_metrics_share_the_theme():
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    script = Path("app/static/scripts/app.js").read_text(encoding="utf-8")
    status = Path("app/templates/admin/system.html").read_text(encoding="utf-8")
    seo = Path("app/templates/admin/content/seo.html").read_text(encoding="utf-8")

    assert "link.offsetLeft" in script
    assert "link.offsetTop" in script
    assert "data-runtime-metrics" in status
    assert "data-runtime-progress" in status
    assert "refreshRuntimeMetrics" in script
    assert "setInterval(refreshRuntimeMetrics, 2_000)" in script
    assert ".runtime-progress i" in styles
    assert "google_verification" not in seo and "bing_verification" not in seo


def test_every_progress_fill_uses_the_shared_light_blue_token():
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")

    assert "--progress-fill: #cde8f7;" in styles
    for selector in (
        ".progress span",
        ".reading-progress span",
        ".toc-progress__track i",
        ".skill-list b",
        ".about-skills b",
        ".upload-progress i",
        ".dashboard-widget__progress i",
        ".component-progress i",
        ".component-progress--pink i",
        ".runtime-progress i",
        ".gateway-call-progress i",
    ):
        rule = styles.split(selector, 1)[1].split("}", 1)[0]
        assert "var(--progress-fill)" in rule
        assert "linear-gradient" not in rule

    assert "linear-gradient(90deg,var(--blue-300),var(--pink-400))" not in styles
    assert "linear-gradient(90deg,#a7d7c0,#dff6e9)" not in styles
    assert "linear-gradient(90deg,#f1c7d8,#fff0f6)" not in styles


def test_site_logo_uses_the_shared_crop_scale_and_animated_upload_experience():
    template = Path("app/templates/admin/content/site_logo.html").read_text(encoding="utf-8")
    admin = Path("app/templates/layouts/admin.html").read_text(encoding="utf-8")
    script = Path("app/static/scripts/ui-global.js").read_text(encoding="utf-8")
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    route = Path("app/blueprints/admin/content_routes.py").read_text(encoding="utf-8")

    assert "data_logo_crop" in template
    assert "data-animated-upload" in template
    assert "data-upload-progress" in template
    assert "site-logo-file-input" in template
    assert "hidden=true" in template
    assert "data-file-name" not in template
    assert "调整网站Logo" in script
    assert "is-logo-mode" in script
    assert "site-logo-cloudtrace" in script
    assert ".site-logo-workspace" in styles
    assert ".image-crop-dialog[open]" in styles
    assert 'original_filename=f"site-logo{extension}"' in route
    assert "form.logo.data.filename" not in route
    assert "<strong>站点</strong>" in admin
    assert "admin_child('site-identity', '标题与Logo'" in admin
    assert "admin_child('site-seo', '搜索与分享'" in admin
    assert "admin_child('site-external-links', '第三方链接'" in admin
    assert "admin_child('site-addresses', '网站链接'" in admin
    assert "admin_child('site-security', '安全'" in admin


def test_admin_visual_integrity_uses_themed_controls_and_readable_widget_type():
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    security = Path("app/templates/admin/site/site_security.html").read_text(encoding="utf-8")

    assert '.admin-main input[type="checkbox"]' in styles
    assert '.admin-main input[type="radio"]' in styles
    assert "appearance:none!important" in styles
    assert "border-radius:50%!important" in styles
    assert ".site-security-grid" in styles
    assert ".security-setting-card__switch" in styles
    assert "security-setting-card__switch" in security
    assert "font-size:max(10.5px" in styles
    assert "font-size:max(10px" in styles


def test_theme_setting_previews_have_live_smooth_motion_contracts():
    script = Path("app/static/scripts/app.js").read_text(encoding="utf-8")
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    interface = Path("app/templates/admin/content/interface.html").read_text(encoding="utf-8")

    assert "data-font-settings" in interface
    assert "data-hint-settings" in interface
    assert "replayThemePreview" in script
    assert "is-preview-playing" in script
    assert "root.dataset.pageTransition = input.value" in script
    assert "root.dataset.fontStyle = input.value" in script
    assert "@keyframes theme-choice-settle" in styles
    assert ".transition-choice__demo.is-preview-playing" in styles
    assert "dialog.modal," in styles


def test_public_footer_never_exposes_the_private_admin_entry():
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    footer = Path("app/templates/components/site_footer.html").read_text(encoding="utf-8")

    assert ".safe-media__fallback{position:absolute;inset:0" in styles
    assert "item.url != '/admin/'" in footer
    assert "gateway_is_admin" not in footer


def test_server_flashes_become_plain_capsule_sources(client):
    html = client.get("/demo/flash/error/").get_data(as_text=True)
    assert '<ul class="flash-source" data-flash-source data-no-linkify hidden>' in html
    assert '<li data-flash-tone="error">这是一条来自Flask服务端的状态通知。</li>' in html
    assert '<noscript><ul class="flash-noscript">' in html
    assert 'class="toast' not in html
    quiet = client.get("/").get_data(as_text=True)
    assert "data-flash-source" not in quiet


def test_phase6_long_titles_cannot_stretch_grid_cards():
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    tail = styles[styles.index("长标题保护"):]
    assert ".article-neighbors > a" in tail and "min-width:0" in tail
    assert "overflow-wrap:anywhere" in tail
    assert "minmax(0,1fr)" in tail


def test_phase6_themed_selects_release_observers_after_page_swaps():
    script = Path("app/static/scripts/ui-global.js").read_text(encoding="utf-8")
    assert "selectObservers" in script
    assert "releaseDetachedSelects" in script
    assert "observer.disconnect()" in script


def test_phase6_moment_detail_has_a_page_heading():
    template = Path("app/templates/public/moment_detail.html").read_text(encoding="utf-8")
    assert '<h1 class="sr-only">' in template


def test_light_blue_scheme_moves_lines_toward_white_but_keeps_text_readable():
    import colorsys

    css = Path("app/static/styles/small-window-theme.css").read_text(encoding="utf-8")

    def lightness(token):
        value = re.search(rf"--{token}:\s*#([0-9a-f]{{6}})", css).group(1)
        r, g, b = (int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))
        return colorsys.rgb_to_hls(r, g, b)[1]

    assert lightness("line-blue") > 0.94
    assert lightness("line-blue-strong") > 0.89
    assert lightness("line-blue") > lightness("line-blue-strong")
    assert lightness("accent-soft") > 0.65
    # Body text and the keyboard focus ring stay strong enough to read.
    assert lightness("graphite-blue") < 0.3
    assert lightness("sunny-blue") < 0.55
    assert "outline: 2px solid var(--sunny-blue)" in css


def test_legacy_default_colours_resolve_to_the_lighter_defaults(app):
    from app.services.content import (
        COMPONENT_MOTION_DEFAULTS,
        DIALOG_APPEARANCE_DEFAULTS,
        resolve_color_setting,
    )

    motion = COMPONENT_MOTION_DEFAULTS["component_motion_color"]
    accent = DIALOG_APPEARANCE_DEFAULTS["dialog_accent"]
    assert resolve_color_setting("component_motion_color", "#91bed8", motion) == motion
    assert resolve_color_setting("dialog_accent", "#526FA6", accent) == accent
    assert resolve_color_setting("dialog_accent", None, accent) == accent
    # A colour the owner chose is never replaced.
    assert resolve_color_setting("dialog_accent", "#88b9d8", accent) == "#88b9d8"
    assert resolve_color_setting("toast_background", "#91bed8", "#FFFFFF") == "#91bed8"


def test_setup_page_assets_keep_motion_safe_and_rules_in_sync():
    css = Path("app/static/styles/setup.css").read_text(encoding="utf-8")
    script = Path("app/static/scripts/setup.js").read_text(encoding="utf-8")
    forms = Path("app/forms.py").read_text(encoding="utf-8")

    # The client-side minimum must match the server rule it previews.
    server_min = re.search(r'"管理员密码", validators=\[DataRequired\(\), Length\(min=(\d+)', forms).group(1)
    assert f"const MIN_PASSWORD = {server_min};" in script
    # Reduced motion and low-performance modes stop every animation on the page.
    assert 'html[data-motion="reduce"] .setup *' in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    # No pressed-in or double-shadow (neumorphic) surfaces on the setup page: fields and
    # buttons come from the shared theme.
    assert not re.search(r"box-shadow:[^;]*inset", css) and "--su-press" not in css and "--su-raise" not in css
    assert "flat fields: no inner shadow at all" in css
    assert 'class="button button--primary setup-submit"' in Path("app/templates/admin/setup.html").read_text(encoding="utf-8")
    # The password peek button keeps a clearly visible keyboard outline.
    assert ".setup-peek:focus-visible { outline: 2px solid var(--sunny-blue" in css
    # Page module, not a bare listener, so it can be torn down.
    assert "CloudtracePage.define('setup-page'" in script
    # The setup page owns its stylesheet; the shared sheets no longer carry the retired guide.
    for name in ("small-window-theme.css", "app.css"):
        assert "setup-guide" not in Path(f"app/static/styles/{name}").read_text(encoding="utf-8")


def test_setup_page_has_no_right_card_and_everything_slides_in_and_out():
    css = Path("app/static/styles/setup.css").read_text(encoding="utf-8")
    script = Path("app/static/scripts/setup.js").read_text(encoding="utf-8")
    template = Path("app/templates/admin/setup.html").read_text(encoding="utf-8")
    # Direction-aware reveal for the heading, group titles, text boxes, captcha and button.
    assert '.setup-reveal[data-setup-reveal="out-down"]' in css and '.setup-reveal[data-setup-reveal="out-up"]' in css
    for selector in (".setup-card__head", ".setup-group > legend", ".setup-group > .setup-field",
                     ".setup-group > .setup-bundle", ".setup-group > .human-check", ".setup-submit-wrap"):
        assert selector in script
    assert "IntersectionObserver" in script and "'out-up' : 'out-down'" in script
    assert "@media (prefers-reduced-motion: reduce) { .setup-reveal" in css
    # The right-hand form sits directly on the page: no card background, border, shadow or outline.
    card = re.search(r"\.setup-card \{([^}]*)\}", css).group(1)
    assert "background" not in card and "border" not in card and "box-shadow" not in card
    assert "data-motion-surface" not in template
    # The left column is centred, the cloud has no card, and the flow list is the large element.
    intro = re.search(r"\.setup-intro \{([^}]*)\}", css).group(1)
    assert "text-align: center" in intro and "justify-items: center" in intro
    mascot = re.search(r"\.setup-mascot \{([^}]*)\}", css).group(1)
    assert "background" not in mascot and "border" not in mascot and "padding" not in mascot
    cloud = int(re.search(r"\.setup-mascot__cloud \{ width: min\(100%, (\d+)px\)", css).group(1))
    dot = int(re.search(r"\.setup-steps__dot \{[^}]*?width: (\d+)px", css).group(1))
    assert cloud <= 200 and dot >= 56
    assert "grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr)" in css


def test_setup_blocks_have_an_opening_entrance_before_the_scroll_reveal():
    css = Path("app/static/styles/setup.css").read_text(encoding="utf-8")
    block = re.search(r"opening entrance.*?@keyframes setup-enter", css, re.S).group(0)
    for selector in (".setup-card__head", ".setup-group > legend", ".setup-group > .setup-field",
                     ".setup-group > .setup-bundle", ".setup-group > .human-check", ".setup-submit-wrap"):
        assert selector in block
    # `backwards` only: a forwards/both fill would pin the end frame and defeat the scroll reveal.
    assert "animation: setup-enter 760ms var(--su-ease) backwards" in block
    assert "both" not in re.search(r"animation: setup-enter[^;]*;", block).group(0)
    # No-script safe: the entrance is CSS only and does not depend on the reveal class.
    assert ".setup-reveal" not in block
    # Reduced motion removes it together with every other animation on the page.
    assert 'html[data-motion="reduce"] .setup *' in css
