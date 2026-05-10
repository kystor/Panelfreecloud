import time
import os
import base64
import re  
import datetime  # 导入日期与时间处理模块，用于计算上海时区时间
from seleniumbase import SB
import ddddocr

# ==========================================
# 1. 网站配置区域 (核心元素的定位器)
# ==========================================
CONFIG = {
    "target_url": "https://panel.freecloud.ltd/index.php?rp=/login",  
    
    # 邮箱和密码输入框的定位器
    "username_selector": "#inputEmail",       
    "password_selector": "#inputPassword",    
    
    "captcha_img_selector": "#allow_login_email_captcha",          
    "captcha_input_selector": "#captcha_allow_login_email_captcha", 
    "login_btn_selector": 'button[type="submit"]',
    
    "user_center_indicator": "li.active:contains('用户中心')", 
    "points_selector": "p:contains('您的账户余额为：') strong",   
    "checkin_btn": "a[href*='action=dailycheckin']",          
    "services_panel": "#servicesPanel",                       
    "nav_services": "#Primary_Navbar-Services > a",            
    "nav_renew": "#Primary_Navbar-Services-Renew_Services > a", 
    "add_to_cart_btn": "button.btn-add-renewal-to-cart",      
    "view_cart_btn": "a#Secondary_Sidebar-Actions-View_Cart", 
    "tos_checkbox": "input[data-tos-checkbox]",                
    "checkout_btn": "button#checkout"                          
}

# 提前创建一个文件夹，用来专门存放截图，方便后续排错
os.makedirs("screenshots", exist_ok=True)

# 截图辅助函数：自动给图片加上账号名和步骤编号
def take_screenshot(sb, step_name, username="system"):
    # 替换掉邮箱里不适合作为文件名的特殊符号
    safe_name = username.replace("@", "_").replace(".", "_")
    filepath = f"screenshots/{safe_name}_{step_name}.png"
    try:
        sb.save_screenshot(filepath)
        print(f"    📸 已截图保存: {filepath}")
    except Exception as e:
        print(f"    ⚠️ 截图失败 ({filepath}): {e}")

# ==========================================
# 2. Cloudflare 绕过辅助函数 
# ==========================================
def is_cloudflare_interstitial(sb) -> bool:
    """检测当前页面是否处于 Cloudflare 5秒盾拦截状态"""
    try:
        page_source = sb.get_page_source()
        title = sb.get_title().lower() if sb.get_title() else ""
        indicators = ["Just a moment", "Verify you are human", "Checking your browser", "Checking if the site connection is secure"]
        for ind in indicators:
            if ind in page_source:
                return True
        if "just a moment" in title or "attention required" in title:
            return True
        body_len = sb.execute_script('(function() { return document.body ? document.body.innerText.length : 0; })();')
        if body_len is not None and body_len < 200 and "challenges.cloudflare.com" in page_source:
            return True
        return False
    except:
        return False

def bypass_cloudflare_interstitial(sb, max_attempts=4) -> bool:
    """尝试通过点击绕过 Cloudflare 拦截"""
    print("    🛡️ 检测到 CF 5秒盾，准备破除...")
    for attempt in range(max_attempts):
        print(f"      ▶ 尝试绕过 ({attempt+1}/{max_attempts})...")
        try:
            # 模拟物理鼠标点击验证码框
            sb.uc_gui_click_captcha()
            time.sleep(6)
            if not is_cloudflare_interstitial(sb):
                print("      ✅ CF 5秒盾已通过！")
                return True
        except Exception as e:
            pass
        time.sleep(3)
    return False

def handle_turnstile_verification(sb) -> bool:
    """处理页面内嵌的 Cloudflare Turnstile 人机验证控件"""
    try:
        # 清除可能遮挡点击的 Cookie 弹窗
        cookie_btn = 'button[data-cky-tag="accept-button"]'
        if sb.is_element_visible(cookie_btn):
            sb.click(cookie_btn)
            time.sleep(1)
    except:
        pass

    # 将验证码滚动到屏幕中央
    sb.execute_script('''
        try {
            var t = document.querySelector('.cf-turnstile') || 
                    document.querySelector('iframe[src*="challenges.cloudflare"]') || 
                    document.querySelector('iframe[src*="turnstile"]');
            if (t) t.scrollIntoView({behavior:'smooth', block:'center'});
        } catch(e) {}
    ''')
    time.sleep(2)

    has_turnstile = False
    for _ in range(15):
        if (sb.is_element_present('iframe[src*="challenges.cloudflare"]') or 
            sb.is_element_present('iframe[src*="turnstile"]') or 
            sb.is_element_present('.cf-turnstile') or 
            sb.is_element_present('input[name="cf-turnstile-response"]')):
            has_turnstile = True
            break
        time.sleep(1)

    # 如果没找到验证码，说明无感通过了
    if not has_turnstile:
        return True

    verified = False
    for attempt in range(1, 4):
        try:
            sb.uc_gui_click_captcha()
        except:
            pass
            
        for _ in range(10):
            # 检查是否成功获得了放行 token
            if sb.is_element_present('input[name="cf-turnstile-response"]'):
                token = sb.get_attribute('input[name="cf-turnstile-response"]', 'value')
                if token and len(token) > 20:
                    verified = True
                    break
            time.sleep(1)
        if verified:
            break

    # 等待网站自动计算验证码
    if not verified:
        for _ in range(30):
            if sb.is_element_present('input[name="cf-turnstile-response"]'):
                token = sb.get_attribute('input[name="cf-turnstile-response"]', 'value')
                if token and len(token) > 20:
                    verified = True
                    break
            time.sleep(1)

    if not verified:
        return False
    return True

# ==========================================
# 3. 单个账号的处理流程核心代码
# ==========================================
def process_single_account(username, password):
    print(f"\n==========================================")
    print(f"➡️ 开始处理账号: {username}")
    print(f"==========================================")
    
    # 尝试读取系统的 HTTP 代理（如果有的话）
    env_proxy = os.environ.get("HTTP_PROXY")
    
    with SB(
        uc=True,            
        test=True,          
        locale="en",        
        headless=False,      
        proxy=env_proxy,    
        chromium_arg="--disable-blink-features=AutomationControlled,--window-size=1920,1080"
    ) as sb:
        print(f"🌐 正在访问目标网站: {CONFIG['target_url']}")
        sb.uc_open_with_reconnect(CONFIG['target_url'], reconnect_time=8)
        time.sleep(4)
        
        take_screenshot(sb, "01_初始访问页面", username)

        if is_cloudflare_interstitial(sb):
            if not bypass_cloudflare_interstitial(sb):
                print(f"❌ 无法绕过 CF 整页拦截，跳过此账号。")
                take_screenshot(sb, "Error_01_卡在CF盾", username)
                return 
            time.sleep(3) 
            
        handle_turnstile_verification(sb)
        time.sleep(3)
        take_screenshot(sb, "02_CF验证通过_准备输入表单", username)

        try:
            print(">>> 正在输入账号和密码...")
            sb.type(CONFIG['username_selector'], username)
            sb.type(CONFIG['password_selector'], password)
            time.sleep(1)
            take_screenshot(sb, "03_账号密码已输入", username)

            # 检查是否有图片验证码，如果有就用 ddddocr 识别
            if sb.is_element_visible(CONFIG['captcha_img_selector']):
                img_src = sb.get_attribute(CONFIG['captcha_img_selector'], "src")
                if "base64," in img_src:
                    base64_data = img_src.split(',')[1]
                    img_bytes = base64.b64decode(base64_data)
                    ocr = ddddocr.DdddOcr(show_ad=False)
                    captcha_text = ocr.classification(img_bytes)
                    print(f">>> 🤖 识别出的验证码为: {captcha_text}")
                    sb.type(CONFIG['captcha_input_selector'], captcha_text)
                    time.sleep(1)
                    take_screenshot(sb, "04_验证码已输入", username)

            print(">>> 点击登录！")
            sb.click(CONFIG['login_btn_selector'])
            time.sleep(5) 
            
            # 第一步：验证是否成功登录
            if sb.is_element_visible(CONFIG['user_center_indicator']) or "clientarea.php" in sb.get_current_url():
                print(">>> ✅ 登录成功，已进入用户中心面板！")
                take_screenshot(sb, "05_登录成功_用户中心面板", username)
            else:
                print(">>> ❌ 登录失败。请检查账号密码或网站是否要求了其他验证。")
                take_screenshot(sb, "Error_02_登录失败页面", username)
                return 

            # 第二步：获取当前积分并检查签到状态
            if sb.is_element_visible(CONFIG['points_selector']):
                current_points_text = sb.get_text(CONFIG['points_selector'])
                print(f">>> 💰 当前积分显示为：{current_points_text}")
                take_screenshot(sb, "06_积分与签到状态检查", username)
            
            # 🌟 智能判断：如果网页提示已经签到，则跳过点击签到按钮的步骤
            if sb.is_element_visible("p:contains('您今天已经签到过了！')"):
                print(">>> 📌 【状态确认】系统提示今天已经签到过了，无需重复操作。")
            elif sb.is_element_visible(CONFIG['checkin_btn']):
                print(">>> 🖱️ 发现签到按钮，准备执行自动签到...")
                sb.click(CONFIG['checkin_btn'])
                time.sleep(3) 
                sb.refresh_page() 
                time.sleep(3)
                print(">>> ✅ 已完成签到并刷新页面！")
                take_screenshot(sb, "07_签到刷新后", username)
            else:
                print(">>> ⚠️ 未发现签到按钮，也没有已签到提示，请排查截图查看当前页面状态。")
            
            # 提取最新的纯数字积分
            latest_points_text = sb.get_text(CONFIG['points_selector'])
            match = re.search(r"([\d\.]+)", latest_points_text)
            
            if match:
                points_value = float(match.group(1)) 
            else:
                points_value = 0.0
                
            print(f">>> 📊 当前解析到的实际可用积分数值为: {points_value}")

            # 第三步：判断积分是否满足续费条件（>= 5.0分）
            if points_value >= 5.0:
                print(">>> 🟢 积分已满 5 分，允许进行续费操作！")
                
                # 检查有没有可以续费的产品面板
                if sb.is_element_visible(CONFIG['services_panel']):
                    print(">>> 🔍 找到可用产品，准备进入续费页面...")
                    take_screenshot(sb, "08_积分达标_准备续费", username)
                    
                    print(">>> 🖱️ 正在点击上方导航栏的【产品服务】...")
                    sb.click(CONFIG['nav_services'])
                    time.sleep(1) 
                    take_screenshot(sb, "09_点击展开产品服务下拉菜单", username)
                    
                    print(">>> 🖱️ 正在点击下拉菜单中的【续费服务】...")
                    sb.click(CONFIG['nav_renew'])
                    sb.wait_for_element(CONFIG['add_to_cart_btn'], timeout=10)
                    take_screenshot(sb, "10_进入续费服务列表页面", username)
                    
                    # ===================================================================
                    # 🌟 高级进阶：精准基于【上海时区】解析并计算到期时间
                    # ===================================================================
                    try:
                        print(">>> 🔎 正在提取当前产品的到期时间信息...")
                        renewal_text = sb.get_text(".domain-renewal-content")
                        
                        # 使用正则提取类似 "2026/07/04" 或者 "2026-07-04" 的日期
                        date_match = re.search(r"下次逾期日期:\s*(\d{4}[/-]\d{2}[/-]\d{2})", renewal_text)
                        
                        if date_match:
                            expire_date_str = date_match.group(1)
                            
                            # 1. 把网页上的字符串格式化为 Python 认识的日期对象 
                            expire_date_obj = datetime.datetime.strptime(expire_date_str.replace('-', '/'), "%Y/%m/%d").date()
                            
                            # 2. 构建上海时区 (UTC+8小时)
                            shanghai_tz = datetime.timezone(datetime.timedelta(hours=8))
                            
                            # 3. 获取带有上海时区的“今天”的日期对象
                            today_shanghai_date = datetime.datetime.now(shanghai_tz).date()
                            
                            # 4. 精准相减得到天数
                            days_left = (expire_date_obj - today_shanghai_date).days
                            
                            print(f">>> 📅 【服务状态】下次逾期日期为: {expire_date_str} (基于上海时间计算)")
                            
                            if days_left > 0:
                                print(f">>> ⏳ 距离到期还有 {days_left} 天。")
                                if days_left > 30:
                                    print(">>> 💡 【系统预判】距离到期时间较长(>30天)，系统大概率会拦截提前续费。将继续尝试验证...")
                                else:
                                    print(">>> 🟢 【系统预判】产品已进入可续费周期，准备执行续费！")
                            else:
                                print(f">>> 🚨 【服务状态】服务已逾期 {abs(days_left)} 天，急需续费！")
                        else:
                            print(">>> ⚠️ 未能在页面上找到符合格式的逾期日期。")
                    except Exception as e:
                        print(f">>> ⚠️ 日期解析模块遇到小问题 (不影响后续流程): {e}")
                    # ===================================================================

                    print(">>> 🛒 正在尝试将产品【添加到购物车】...")
                    sb.click(CONFIG['add_to_cart_btn'])
                    time.sleep(3) 
                    take_screenshot(sb, "11_点击添加到购物车后", username)

                    print(">>> 🏃‍♂️ 正在前往购物车结算页面验证结果...")
                    sb.open("https://panel.freecloud.ltd/cart.php?a=view")
                    time.sleep(3)
                    
                    # 🌟 终极改进逻辑：利用专属 HTML 元素，精准判断购物车是否被拦截
                    if sb.is_element_visible("h6.message-title:contains('您的购物车是空的')") or sb.is_element_visible(".message-no-data"):
                        print(">>> ⏸️ 【拦截成功】检测到“您的购物车是空的”。系统已拒绝提前续费，自动跳过结账。")
                        take_screenshot(sb, "12_购物车为空_未到续费期", username)
                        
                    elif sb.is_element_visible(CONFIG['checkout_btn']):
                        print(">>> 📝 确认购物车内有商品，准备结账...")
                        take_screenshot(sb, "12_进入购物车结算页面_准备结账", username)
                        
                        print(">>> ☑️ 正在自动勾选【服务条款】...")
                        # 强制勾选隐藏的复选框
                        sb.execute_script('document.querySelector("input[data-tos-checkbox]").click();')
                        time.sleep(1)
                        take_screenshot(sb, "13_已勾选服务条款", username)
                        
                        print(">>> 💳 正在点击最后的【结账】按钮...")
                        sb.wait_for_element_clickable(CONFIG['checkout_btn'], timeout=5)
                        sb.click(CONFIG['checkout_btn'])
                        
                        time.sleep(5)
                        take_screenshot(sb, "14_点击结账后的最终页面", username)
                        print(">>> 🎉 恭喜！续费及结账流程全部完成！")
                        
                    else:
                        # 兜底方案，防止网页出现其他未知错误
                        print(">>> ⚠️ 购物车状态未知，未找到结账按钮也未发现空车提示，请查看截图排查。")
                        take_screenshot(sb, "Error_12_购物车页面状态异常", username)
                        
                else:
                    print(">>> ⚠️ 当前账号积分达标，但没有需要续费的可用产品。")
            else:
                print(f">>> ⏸️ 积分不足 5 分 (差 {5.0 - points_value:.2f} 分)，直接跳过续费流程。")
                take_screenshot(sb, "08_积分不足_跳过续费", username)

        except Exception as e:
            print(f"❌ 账号 {username} 处理过程中出现异常或错误: {e}")
            take_screenshot(sb, "Error_99_流程异常中断", username)

# ==========================================
# 4. 主程序入口
# ==========================================
def main():
    print("🚀 自动化任务启动...")
    # 从 GitHub Secrets 环境变量中获取账号配置
    accounts_str = os.environ.get("acount")
    
    if not accounts_str:
        print("⚠️ 未获取到名为 'acount' 的环境变量，请检查配置！")
        return

    # 支持多个账号循环执行
    account_list = accounts_str.split(',')
    for item in account_list:
        item = item.strip()
        if ':' in item:
            parts = item.split(':', 1) 
            username = parts[0].strip()
            password = parts[1].strip()
            # 执行核心逻辑
            process_single_account(username, password)
            
    print("\n🏁 所有账号的任务执行完成！")

if __name__ == "__main__":
    main()
