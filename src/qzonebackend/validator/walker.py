import logging
from selenium.webdriver import Edge, Chrome, Firefox, ChromeOptions, FirefoxOptions
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

from .jigsaw import findDarkArea, contourMatch

logger = logging.getLogger("Selenium Walker")

class Walker:
    crackMethod = contourMatch

    def __init__(self, browser='Chrome', driver={}, option=[], refresh_time=10):
        self.refresh_time = refresh_time

        # chrome_options = Options()
        # if self.headless: chrome_options.add_argument('--headless')
        # chrome_options.add_argument("log-level=%d" % self.log_level)
        if option:
            op = {'Firefox': FirefoxOptions, 'Chrome': ChromeOptions}[browser]()
            for i in option: op.add_argument('--' + i)
            driver[browser.lower() + '_options'] = op

        self.driver = {
            'Chrome': Chrome, 
            'Firefox': Firefox, 
            'Edge': Edge
        }[browser](**driver)

    def qrLogin(self, uin, QRFetched=None):
        raise NotImplementedError('QR code not supported now.')
        self.driver.find_element_by_id('switcher_qlogin').click()
        qurl = self.driver.find_element_by_id('qrlogin_img').get_attribute('src')
        for i in range(3):
            cur_url = self.driver.current_url
            QRFetched(qurl)
            try: 
                WebDriverWait(self.driver, 90).until(
                    lambda dr: False # TODO: test what will happen after qr is scanned
                )
                if self._waitForJump(cur_url, uin): return True
            except TimeoutException: pass
            logger.info('QR login failed #%d' % (i + 1))
        return False

    def login(self, uin, pwd=None, qrcode='forbid', QRFetched=None):
        '''
        qrcode: forbid, allow, prefer, force
        '''

        logger.info("等待登陆界面加载")
        self.driver.get('https://qzone.qq.com/')
        logger.info("登陆界面加载完成")
        self.driver.switch_to.frame('login_frame')

        if qrcode == 'force': self.qrLogin(QRFetched)
        elif qrcode == 'prefer': 
            if not self.qrLogin(QRFetched):
                self.driver.refresh()
                self.pwdLogin(uin, pwd)
        elif qrcode == 'allow': 
            if not self.pwdLogin(uin, pwd):
                self.driver.refresh()
                self.qrLogin(QRFetched)
        elif qrcode == 'forbid': self.pwdLogin(uin, pwd)
        else: 
            self.driver.close(); self.driver.quit()
            raise ValueError(qrcode)
        cookie = self._getCookie()
        self.driver.close(); self.driver.quit()
        return cookie

    def pwdLogin(self, uin, pwd):
        self._switchFrame(uin, pwd)
        for i in range(self.refresh_time):
            if i > 0: logger.info('第%d次尝试登陆' % (i + 1))
            if self._crackValidate(uin): return True
        return False        

    def _switchFrame(self, uin, pwd):          
        self.driver.find_element_by_id('switcher_plogin').click()
        self.driver.find_element_by_id('u').clear()
        self.driver.find_element_by_id('u').send_keys(uin)
        self.driver.find_element_by_id('p').clear()
        self.driver.find_element_by_id('p').send_keys(pwd)
        self.driver.find_element_by_id('login_button').click()

        try: WebDriverWait(self.driver, 3).until(
            EC.frame_to_be_available_and_switch_to_it((By.ID, 'tcaptcha_iframe'))
        )
        except TimeoutException:
            # TODO 可能是要输入验证码?
            raise RuntimeError('限制登陆.')
        
    def _waitForJump(self, cur_url, uin, timeout=5):
        try: WebDriverWait(self.driver, 5, 0.5).until(
            lambda dr: cur_url != self.driver.current_url
        )
        except NoSuchElementException: return False     # 网页没变, 重来
        else: 
            if ("user.qzone.qq.com/%d" % uin) in self.driver.current_url: return True
            else: raise RuntimeError('穿越到未知的地界... ' + self.driver.current_url)

    def _getCookie(self):
        cookie = self.driver.get_cookies()
        qzonetoken = self.driver.execute_script('return window.g_qzonetoken')
        cookie = {i["name"]: i["value"] for i in cookie}
        cookie["qzonetoken"] = qzonetoken
        return cookie

    def _crackValidate(self, uin):
        try:
            WebDriverWait(self.driver, 5).until(lambda dr: dr.find_element_by_id('slideBg').get_attribute('src'))
        except TimeoutException: 
            logger.error('未找到captcha.')
            return False

        bg = self.driver.find_element_by_id('slideBg')
        jigsaw = self.driver.find_element_by_id("slideBlock")
        refresh = self.driver.find_element_by_id('e_reload')
        thumb = self.driver.find_element_by_id('tcaptcha_drag_thumb')
        guide = self.driver.find_element_by_id('guideText')

        back_url = bg.get_attribute('src')
        fore_url = jigsaw.get_attribute('src')

        WebDriverWait(self.driver, 3).until(lambda dr: jigsaw.rect['x'] > 0)
        back_rect = bg.rect
        fore_rect = jigsaw.rect

        print(fore_rect, back_rect, sep='\n')   # collecting test data
        w, D = contourMatch(fore_url, back_url, fore_rect, back_rect)
        if w <= 0:
            refresh.click()
            return False
        
        for i, xoff in enumerate([w, w + D, w - D]):
            ac = ActionChains(self.driver)
            ac.click_and_hold(thumb)
            ac.move_by_offset(xoffset=xoff, yoffset=0)
            ac.release(thumb)
            ac.perform()
            
            cur_url = self.driver.current_url

            logger.info('又' * i + "等待跳转至Qzone")
            try: WebDriverWait(self.driver, 2).until(lambda dr: "请控制拼图块对齐缺口" in guide.text)   # 找错误提示
            except (TimeoutException, StaleElementReferenceException): pass               # 没找到说明有可能过了
            else: continue

            if self._waitForJump(cur_url, uin): break
            else: continue

        else: return False

        logger.info('跳转成功 (成功混过验证')
        return True