import time
import os
import base64
import re  # 🌟 新增：导入正则表达式模块，用于从字符串中提取数字
from seleniumbase import SB
import ddddocr

# ==========================================
# 1. 网站配置区域
# ==========================================
CONFIG = {
    "target_url": "https://panel.freecloud.ltd/index.php?rp=/login",  
    "username_selector": "#emailInp",             
    "password_selector": "#emailPwdInp",          
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

os.makedirs("screenshots", exist_ok=True)

def take_screenshot(sb, step_name, username="system"):
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
# (为了保持代码整洁，CF绕过部分保持原样)
def is_cloudflare_interstitial(sb) -> bool:
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
    print("    🛡️ 检测到 CF 5秒盾，准备破除...")
    for attempt in range(max_attempts):
        print(f"      ▶ 尝试绕过 ({attempt+1}/{max_attempts})...")
        try:
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
    try:
        cookie_btn = 'button[data-cky-tag="accept-button"]'
        if sb.is_element_visible(cookie_btn):
            sb.click(cookie_btn)
            time.sleep(1)
    except:
        pass

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

    if not has_turnstile:
        return True

    verified = False
    for attempt in range(1, 4):
        try:
            sb.uc_gui_click_captcha()
        except:
            pass
            
        for _ in range(10):
            if sb.is_element_present('input[name="cf-turnstile-response"]'):
                token = sb.get_attribute('input[name="cf-turnstile-response"]', 'value')
                if token and len(token) > 20:
                    verified = True
                    break
            time.sleep(1)
        if verified:
            break

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
# 3. 单个账号的处理流程
# ==========================================
def process_single_account(username, password):
    print(f"\n==========================================")
    print(f"➡️ 开始处理账号: {username}")
    print(f"==========================================")
    
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
            
            if sb.is_element_visible(CONFIG['user_center_indicator']) or "clientarea.php" in sb.get_current_url():
                print(">>> ✅ 登录成功，已进入用户中心面板！")
                take_screenshot(sb, "05_登录成功_用户中心面板", username)
            else:
                print(">>> ❌ 登录失败。")
                take_screenshot(sb, "Error_02_登录失败页面", username)
                return 

            # 第二步：获取当前积分并签到
            if sb.is_element_visible(CONFIG['points_selector']):
                current_points_text = sb.get_text(CONFIG['points_selector'])
                print(f">>> 💰 签到前积分显示为：{current_points_text}")
                take_screenshot(sb, "06_点击签到前", username)
            
            if sb.is_element_visible(CONFIG['checkin_btn']):
                sb.click(CONFIG['checkin_btn'])
                time.sleep(3) 
                sb.refresh_page() 
                time.sleep(3)
                print(">>> ✅ 已完成签到并刷新页面。")
                take_screenshot(sb, "07_签到刷新后", username)
            
            # 🌟 核心逻辑增加处：获取签到后最新的积分并提取纯数字
            latest_points_text = sb.get_text(CONFIG['points_selector'])
            # 使用正则表达式匹配出带有小数点的数字部分（例如从 "1.00积分" 中提取出 "1.00"）
            match = re.search(r"([\d\.]+)", latest_points_text)
            
            if match:
                # 将提取出的文字数字转换成带小数点的浮点数，方便对比大小
                points_value = float(match.group(1)) 
            else:
                points_value = 0.0
                
            print(f">>> 📊 当前解析到的实际可用积分数值为: {points_value}")

            # 第三步：判断积分是否达到续费要求
            if points_value >= 5.0:
                print(">>> 🟢 积分已满 5 分，允许进行续费操作！")
                
                # 开始检查并续费产品
                if sb.is_element_visible(CONFIG['services_panel']):
                    take_screenshot(sb, "08_积分达标_准备续费", username)
                    
                    sb.click(CONFIG['nav_services'])
                    time.sleep(1) 
                    take_screenshot(sb, "09_点击展开产品服务下拉菜单", username)
                    
                    sb.click(CONFIG['nav_renew'])
                    sb.wait_for_element(CONFIG['add_to_cart_btn'], timeout=10)
                    take_screenshot(sb, "10_进入续费服务列表页面", username)
                    
                    sb.click(CONFIG['add_to_cart_btn'])
                    time.sleep(3) 
                    take_screenshot(sb, "11_点击添加到购物车后", username)

                    # 进入购物车结账
                    sb.open("https://panel.freecloud.ltd/cart.php?a=view")
                    sb.wait_for_element(CONFIG['checkout_btn'], timeout=10)
                    take_screenshot(sb, "12_进入购物车结算页面", username)
                    
                    sb.execute_script('document.querySelector("input[data-tos-checkbox]").click();')
                    time.sleep(1)
                    take_screenshot(sb, "13_已勾选服务条款", username)
                    
                    sb.wait_for_element_not_disabled(CONFIG['checkout_btn'], timeout=5)
                    sb.click(CONFIG['checkout_btn'])
                    
                    time.sleep(5)
                    take_screenshot(sb, "14_点击结账后的最终页面", username)
                    print(">>> 🎉 续费及结账流程全部完成！")
                else:
                    print(">>> ⚠️ 当前账号积分达标，但没有需要续费的可用产品。")
            else:
                # 如果积分不足5分，则提示并跳过后续操作
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
    accounts_str = os.environ.get("acount")
    
    if not accounts_str:
        print("⚠️ 未获取到名为 'acount' 的环境变量，请检查配置！")
        return

    account_list = accounts_str.split(',')
    for item in account_list:
        item = item.strip()
        if ':' in item:
            parts = item.split(':', 1) 
            username = parts[0].strip()
            password = parts[1].strip()
            process_single_account(username, password)
            
    print("\n🏁 所有账号的任务执行完成！")

if __name__ == "__main__":
    main()
