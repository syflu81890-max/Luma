"""Stable user-facing reasons independent of an extractor's error wording."""
def classify_failure(text):
    lower=text.lower()
    if any(x in lower for x in ('磁盘空间不足','no space left')):return 'failed','disk_full','磁盘空间不足，已停止；下载和入库进度保留，请释放空间后重试。'
    if any(x in lower for x in ('tweets are protected','not authorized to see','authorization to see','blocked your account','follow request','protected account')):return 'needs_access','access_denied','当前采集身份无法访问此账号。请核对登录账号和关注是否获准；若软件内能看到媒体，可使用“浏览器补采”。'
    if any(x in lower for x in ('429','rate limit','ratelimit','too many requests')):return 'waiting','rate_limited','平台请求受限；已保留进度，将稍后重试。'
    if any(x in lower for x in ('login','could not authenticate','authrequired','401','cookie','authenticated cookies','authentication')):return 'needs_login','login_expired','登录会话需要重新验证；请打开 X 登录窗口，完成后重试。'
    if '403' in lower:return 'needs_access','access_denied','平台拒绝访问，请验证登录身份及关注权限；可以使用浏览器检查可见内容。'
    return 'waiting','engine_error','网络或平台响应异常，已有内容保留，将稍后重试。'

def describe_zero(counts,verified=False,boundary=False):
    if boundary or counts.get('old'):return '已检查到之前的采集范围，没有更新的媒体。'
    if counts.get('excluded'):return '本轮遇到的内容已被你删除并排除，没有重新下载。'
    if counts.get('known') or counts.get('duplicate'):return '本轮发现的媒体已经存在，没有重复入库。'
    if counts.get('filter'):return '本轮发现的媒体均不符合所选日期、类型或勾选范围。'
    if verified:return '账号可访问，本轮媒体页面未返回可下载内容。若页面实际有图片，可使用浏览器补采。'
    return '引擎没有返回媒体或可验证的账号结果，本次未确认采集完整；请检查登录或使用浏览器补采。'
